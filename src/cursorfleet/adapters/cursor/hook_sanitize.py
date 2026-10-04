"""Command and path sanitizers for the hook hot path. Stdlib only (no typing/dataclasses).

Policy: ADR 0003 ("Commands" and "Paths") and docs/privacy.md. A raw command line is
reduced to ``argv0``, ``subcommand``, a redacted and truncated single-line ``display``
and a keyed ``command_hash``; the raw string never leaves this module. Redaction is
BEST EFFORT: a novel secret format can slip through (threat model, residual risks).
Users can switch the display off (``[privacy] store_command_display = false``).

Paths become workspace-relative POSIX strings after symlink resolution; anything outside
every workspace root, or not representable, becomes ``<external>``.
"""

from __future__ import annotations

import math
import os
import re

EXTERNAL = "<external>"
REDACTED = "<redacted>"
EMAIL = "<email>"
DEFAULT_DISPLAY_MAX = 200
_MAX_RAW_COMMAND = 64 * 1024  # bound parsing work on pathological inputs
# Redaction regexes are quadratic on adversarial input (a 64 KiB command took 5-10 s: security
# review SR-01), so they only ever see this many characters. Only the first ``display_max``
# (at most 200) characters can be stored, and the window leaves ample context after them,
# so a secret that starts inside the stored part is still redacted before truncation.
_REDACT_WINDOW = 1024
_MAX_TOKENS = 256

# ---------------------------------------------------------------- regexes (lazy)

_SENSITIVE_NAMES = (
    "token|secret|passw(?:or)?d|passwd|apikey|api[_-]key|credential|private[_-]?key|"
    "access[_-]?key|auth|bearer|session[_-]?id|cookie|signature|sig"
)

_cache: dict[str, re.Pattern[str]] = {}


def _rx(name: str) -> re.Pattern[str]:
    pattern = _cache.get(name)
    if pattern is None:
        pattern = re.compile(_PATTERNS[name][0], _PATTERNS[name][1])
        _cache[name] = pattern
    return pattern


_PATTERNS: dict[str, tuple[str, int]] = {
    "pem": (
        r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|PRIVATE KEY BLOCK)-----.*?(?:-----END [A-Z0-9 ]*"
        r"(?:PRIVATE KEY|PRIVATE KEY BLOCK)-----|\Z)",
        re.DOTALL,
    ),
    "header": (
        r"(?i)\b(authorization|proxy-authorization|x-api-key|x-auth-token|x-access-token|"
        r"x-amz-security-token|cookie|set-cookie)(\s*[:=]\s*)[^\"'\r\n]*",
        0,
    ),
    "json_secret": (
        r"(?i)(\"[A-Za-z0-9_.\-]*(?:" + _SENSITIVE_NAMES + r")[A-Za-z0-9_.\-]*\"\s*:\s*)"
        r"(\"(?:[^\"\\]|\\.)*\"|[^\s,}\]]+)",
        0,
    ),
    "url_userinfo": (r"([A-Za-z][A-Za-z0-9+.\-]*://)[^/\s@\"']+@", 0),
    "url_query": (
        r"(?i)([?&;])([A-Za-z0-9_.\-]*(?:" + _SENSITIVE_NAMES + r")[A-Za-z0-9_.\-]*)=([^&\s\"']*)",
        0,
    ),
    "literal": (
        r"(?:sk-[A-Za-z0-9_\-]{16,}|(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{10,}"
        r"|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
        r"|glpat-[A-Za-z0-9_\-]{12,}|xox[abprs]-[A-Za-z0-9\-]{10,}"
        r"|(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[A-Z0-9]{16}|AIza[0-9A-Za-z_\-]{30,}"
        r"|eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"
        r"|npm_[A-Za-z0-9]{30,}|pypi-[A-Za-z0-9_\-]{30,}"
        r"|SG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}|hf_[A-Za-z0-9]{30,}"
        r"|ya29\.[A-Za-z0-9_\-]{20,}|dop_v1_[a-f0-9]{40,}|shp(?:at|ss|ca|pa)_[a-fA-F0-9]{32}"
        r"|key-[a-f0-9]{32})",
        0,
    ),
    "secret_flag": (
        r"(?i)^-{1,2}[a-z0-9_\-]*(?:token|passw(?:or)?d|passwd|secret|api-?key|credential|"
        r"auth|bearer|cookie|private-?key|access-?key|key)$",
        0,
    ),
    "email": (r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}", 0),
    "assign": (r"^(-{0,2}[A-Za-z_][A-Za-z0-9_.\-]*)=(.*)$", re.DOTALL),
    "ident": (r"^[A-Za-z_][A-Za-z0-9_]*=", 0),
    "argv0_ok": (r"^[A-Za-z0-9_][A-Za-z0-9._+\-]{0,63}$", 0),
    "sub_ok": (r"^[a-z][a-z0-9:_\-]{0,63}$", 0),
}

_SCHEME_WORDS = frozenset({"bearer"})
_USER_FLAG_TOOLS = frozenset({"curl", "wget", "http", "https", "xh"})
_ATTACHED_PASSWORD_TOOLS = frozenset({"mysql", "mysqldump", "mysqladmin", "mariadb"})

# ---------------------------------------------------------------- tokens and redaction


def _strip_quotes(token: str) -> tuple[str, str, str]:
    """Split ``token`` into (leading quotes/parens, core, trailing quotes/punct)."""
    start = 0
    while start < len(token) and token[start] in "\"'`(":
        start += 1
    end = len(token)
    while end > start and token[end - 1] in "\"'`),;":
        end -= 1
    return token[:start], token[start:end], token[end:]


def _entropy(value: str) -> float:
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    total = len(value)
    return -sum(c / total * math.log2(c / total) for c in counts.values())


def _is_blob(core: str) -> bool:
    """Heuristic for opaque secrets: long base64/url-safe/hex strings."""
    for segment in core.split("/"):
        n = len(segment)
        if n < 20:
            continue
        body = segment.rstrip("=")
        if not body or any(not (c.isascii() and (c.isalnum() or c in "+_-")) for c in body):
            continue
        if all(c in "0123456789abcdefABCDEF" for c in body):
            if n >= 32 and n not in (40, 64):
                return True
            continue
        has_digit = any(c.isdigit() for c in body)
        has_alpha = any(c.isalpha() for c in body)
        if has_digit and has_alpha and _entropy(body) >= 3.6:
            return True
    return False


def _redact_blobs(core: str) -> str:
    return "/".join(REDACTED if _is_blob(part) else part for part in core.split("/"))


def redact_text(text: str) -> str:
    """Whole-string redaction passes (multi-token and literal patterns), bounded in size."""
    text = _rx("pem").sub(REDACTED, text[:_REDACT_WINDOW])
    text = _rx("header").sub(lambda m: m.group(1) + m.group(2) + REDACTED, text)
    text = _rx("json_secret").sub(lambda m: m.group(1) + '"' + REDACTED + '"', text)
    text = _rx("url_userinfo").sub(lambda m: m.group(1) + REDACTED + "@", text)
    text = _rx("url_query").sub(lambda m: m.group(1) + m.group(2) + "=" + REDACTED, text)
    text = _rx("literal").sub(REDACTED, text)
    return _rx("email").sub(
        lambda m: m.group(0) if m.group(0).startswith("git@") else EMAIL,
        text,
    )


def _to_printable_line(text: str) -> str:
    cleaned = "".join(ch if ch.isprintable() else " " for ch in text)
    return " ".join(cleaned.split())


def redact_command(raw: str, argv0: str | None = None) -> str:
    """Return a single-line, redacted rendering of ``raw`` (untruncated)."""
    text = _to_printable_line(raw[:_REDACT_WINDOW])
    text = redact_text(text)
    out: list[str] = []
    redact_next = 0
    prev_core = ""
    tokens = text.split(" ")[:_MAX_TOKENS]
    words = {_basename(t) for t in tokens}
    attached_pw = bool(words & _ATTACHED_PASSWORD_TOOLS)  # mysql -pSECRET
    sshpass = "sshpass" in words  # sshpass -p SECRET
    for token in tokens:
        lead, core, trail = _strip_quotes(token)
        lowered = core.lower()
        if redact_next > 0:
            redact_next -= 1
            out.append(lead + REDACTED + trail)
            prev_core = lowered
            continue
        rendered = token
        assign = _rx("assign").match(core)
        if assign is not None:
            name = assign.group(1)
            if not name.startswith("-") or _rx("secret_flag").match(name):
                rendered = lead + name + "=" + REDACTED + trail
        elif attached_pw and len(core) > 2 and core.startswith("-p") and core[2] != "-":
            rendered = lead + "-p" + REDACTED + trail
        elif _rx("secret_flag").match(core) or (
            (core in {"-u", "--user"} and argv0 in _USER_FLAG_TOOLS) or (sshpass and core == "-p")
        ):
            redact_next = 1
        elif prev_core in _SCHEME_WORDS:
            rendered = lead + REDACTED + trail
        else:
            clean = _redact_blobs(core)
            if clean != core:
                rendered = lead + clean + trail
        out.append(rendered)
        prev_core = lowered
    return " ".join(part for part in out if part)


def truncate_display(text: str, max_chars: int) -> tuple[str, bool]:
    """Truncate to ``max_chars`` at a token boundary where possible. Returns (text, cut)."""
    if len(text) <= max_chars:
        return text, False
    budget = max(max_chars - 3, 1)
    cut = text[:budget]
    boundary = cut.rfind(" ")
    if boundary >= budget // 2:
        cut = cut[:boundary]
    return cut.rstrip() + "...", True


# ---------------------------------------------------------------- command facts

_MULTI_COMMAND_TOOLS = frozenset(
    {
        "git", "npm", "pnpm", "yarn", "uv", "pip", "pip3", "cargo", "go", "docker", "kubectl",
        "gh", "make", "poetry", "pipx", "dotnet", "mvn", "gradle", "brew", "apt", "apt-get",
        "systemctl", "terraform", "helm", "bun", "deno", "rustup", "conda", "hatch", "just",
    }
)  # fmt: skip
_VALUE_FLAGS = {"git": frozenset({"-C", "-c", "--git-dir", "--work-tree"})}
_SEGMENT_BREAKS = frozenset({"&&", "||", ";", "|", "&", "|&"})
_WRAPPERS = frozenset({"sudo", "env", "time", "nice", "nohup", "command", "exec", "xargs"})
_VERIFY_ARGV0 = frozenset(
    {
        "pytest", "py.test", "tox", "nox", "ruff", "mypy", "pyright", "flake8", "pylint",
        "eslint", "jest", "vitest", "mocha", "tsc", "rspec", "phpunit", "golangci-lint",
        "shellcheck", "hadolint", "bandit", "unittest", "ctest", "clippy-driver",
    }
)  # fmt: skip
_VERIFY_SUBCOMMANDS = {
    "npm": {"test", "t", "lint", "check", "typecheck", "verify"},
    "pnpm": {"test", "lint", "check", "typecheck"},
    "yarn": {"test", "lint", "check", "typecheck"},
    "bun": {"test"},
    "cargo": {"test", "clippy", "check", "nextest"},
    "go": {"test", "vet"},
    "make": {"test", "lint", "check", "verify"},
    "just": {"test", "lint", "check"},
    "dotnet": {"test"},
    "mvn": {"test", "verify"},
    "gradle": {"test", "check"},
    "deno": {"test", "lint", "check"},
}
_SCRIPT_RUNNERS = frozenset({"npm", "pnpm", "yarn", "bun"})


def _split_segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SEGMENT_BREAKS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


def _basename(word: str) -> str:
    core = word.strip("\"'`")
    return core.replace("\\", "/").rsplit("/", 1)[-1]


def _drop_prefixes(words: list[str]) -> list[str]:
    """Drop leading ``NAME=value`` assignments and simple wrappers (sudo, env, time...)."""
    index = 0
    while index < len(words):
        word = words[index]
        if _rx("ident").match(word):
            index += 1
            continue
        if _basename(word) in _WRAPPERS:
            index += 1
            while index < len(words) and words[index].startswith("-"):
                index += 1  # skip the wrapper's own flags (sudo -n, env -i, ...)
            continue
        break
    return words[index:]


def parse_command(raw: str) -> tuple[str | None, str | None, list[list[str]]]:
    """Return ``(argv0, subcommand, segments)`` from a raw command line. Never raises.

    A tolerant whitespace tokenizer (quotes are stripped from words, not interpreted);
    good enough for classification and display, not a shell parser.
    """
    tokens = raw[:_MAX_RAW_COMMAND].split()[:_MAX_TOKENS]
    segments = [_drop_prefixes(seg) for seg in _split_segments(tokens)]
    segments = [s for s in segments if s]
    if not segments:
        return None, None, []
    first = segments[0]
    name = _basename(first[0])
    argv0 = name if _rx("argv0_ok").match(name) else None
    sub = _subcommand(argv0, first[1:]) if argv0 is not None else None
    return argv0, sub, segments


def _subcommand(argv0: str, args: list[str]) -> str | None:
    if argv0 not in _MULTI_COMMAND_TOOLS:
        return None
    skip = _VALUE_FLAGS.get(argv0, frozenset())
    index = 0
    while index < len(args):
        word = args[index].strip("\"'`")
        if word in skip:
            index += 2
            continue
        if word.startswith("-"):
            index += 1
            continue
        return word if _rx("sub_ok").match(word) else None
    return None


def is_verify_command(argv0: str | None, subcommand: str | None, display: str | None) -> bool:
    """True if a command looks like a test, lint or type-check run (heuristic)."""
    if argv0 is not None and argv0 in _VERIFY_ARGV0:
        return True
    if argv0 is not None and subcommand in _VERIFY_SUBCOMMANDS.get(argv0, ()):
        return True
    if display:
        _a, _s, segments = parse_command(display)
        return any(_segment_verifies(words) for words in segments)
    return False


def _segment_verifies(words: list[str]) -> bool:
    cleaned = [_basename(w) for w in words]
    if not cleaned:
        return False
    head, rest = cleaned[0], cleaned[1:]
    if head in _VERIFY_ARGV0:
        return True
    if head in {"uv", "poetry", "pipx", "hatch", "pdm", "npx", "pnpx", "bunx"}:
        inner = [w for w in rest if w not in {"run", "exec", "--"} and not w.startswith("-")]
        return bool(inner) and inner[0] in _VERIFY_ARGV0
    if head in {"python", "python3", "py"} and len(rest) >= 2 and rest[0] == "-m":
        return rest[1] in _VERIFY_ARGV0 or rest[1] == "pytest"
    sub = next((w for w in rest if not w.startswith("-")), None)
    if sub is not None and sub in _VERIFY_SUBCOMMANDS.get(head, ()):
        return True
    if head in _SCRIPT_RUNNERS and len(rest) >= 2 and rest[0] == "run":
        script = rest[1].lower()
        return any(word in script for word in ("test", "lint", "check", "typecheck", "verify"))
    return False


def sanitize_command(
    raw: object,
    *,
    key: bytes | None,
    store_display: bool = True,
    display_max: int = DEFAULT_DISPLAY_MAX,
    hash_commands: bool = True,
    exit_code: int | None = None,
    duration_ms: int | None = None,
) -> dict[str, object] | None:
    """Reduce a raw command string to a ``SanitizedCommand`` dict, or ``None`` if unusable."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    argv0, subcommand, _segments = parse_command(raw)
    result: dict[str, object] = {"argv0": argv0 or "unknown"}
    if subcommand is not None:
        result["subcommand"] = subcommand
    if (
        isinstance(exit_code, int)
        and not isinstance(exit_code, bool)
        and -1024 <= exit_code <= 1024
    ):
        result["exit_code"] = exit_code
    if (
        isinstance(duration_ms, int)
        and not isinstance(duration_ms, bool)
        and 0 <= duration_ms <= 10**12
    ):
        result["duration_ms"] = duration_ms
    if store_display:
        limit = max(20, min(display_max, DEFAULT_DISPLAY_MAX))
        display, cut = truncate_display(redact_command(raw, argv0), limit)
        if display:
            result["display"] = display
            result["display_truncated"] = cut
    if hash_commands and key:
        digest = _keyed_hash(key, raw)
        if digest:
            result["command_hash"] = digest
    return result


def _keyed_hash(key: bytes, raw: str) -> str | None:
    try:
        import hmac

        normalized = "\x00".join(raw[:_MAX_RAW_COMMAND].split()).encode("utf-8", "replace")
        return hmac.digest(key, normalized, "sha256").hex()[:32]
    except (ImportError, ValueError, TypeError):  # pragma: no cover - defensive
        return None


# ---------------------------------------------------------------- paths


class PathResolver:
    """Relativize paths against workspace roots (symlink-resolved, cross-platform)."""

    __slots__ = ("_roots",)

    def __init__(self, roots: list[str]) -> None:
        resolved: list[str] = []
        for root in roots:
            if isinstance(root, str) and root and os.path.isabs(root):
                try:
                    real = os.path.realpath(root)
                except (OSError, ValueError):
                    continue
                if real not in resolved:
                    resolved.append(real)
        self._roots = resolved

    @property
    def roots(self) -> list[str]:
        return list(self._roots)

    def relativize(self, raw: object) -> str:
        """Return a workspace-relative POSIX path, or ``<external>`` if outside/unusable."""
        if not isinstance(raw, str) or not raw or len(raw) > 4096 or "\x00" in raw:
            return EXTERNAL
        try:
            if os.path.isabs(raw):
                candidate = os.path.realpath(raw)
            elif self._roots:
                candidate = os.path.realpath(os.path.join(self._roots[0], raw))
            else:
                return EXTERNAL
        except (OSError, ValueError):
            return EXTERNAL
        norm_candidate = os.path.normcase(os.path.normpath(candidate))
        for root in self._roots:
            try:
                norm_root = os.path.normcase(os.path.normpath(root))
                common = os.path.commonpath([norm_candidate, norm_root])
            except (OSError, ValueError):
                continue
            if os.path.normcase(os.path.normpath(common)) != norm_root:
                continue
            if norm_candidate == norm_root:
                return EXTERNAL  # the root itself is not a file path worth recording
            try:
                relative = os.path.relpath(candidate, root).replace(os.sep, "/")
            except ValueError:
                return EXTERNAL
            return _validated_relative(relative)
        return EXTERNAL


def _validated_relative(relative: str) -> str:
    if (
        not relative
        or len(relative) > 1024
        or "\\" in relative
        or not relative.isprintable()
        or relative.startswith("/")
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or re.match(r"^[A-Za-z]:", relative)
    ):
        return EXTERNAL
    return relative
