from __future__ import annotations

import os
from pathlib import Path

import pytest

from cursorfleet.adapters.cursor.hook_sanitize import (
    EXTERNAL,
    PathResolver,
    is_verify_command,
    parse_command,
    redact_command,
    sanitize_command,
    truncate_display,
)
from cursorfleet.events.models import SanitizedCommand

KEY = b"k" * 32


@pytest.mark.parametrize(
    ("raw", "argv0", "sub"),
    [
        ("npm test --silent", "npm", "test"),
        ("git -C /tmp/x status --short", "git", "status"),
        ("git -c core.pager=cat log -1", "git", "log"),
        ("FOO=bar BAZ=1 pytest -q tests/", "pytest", None),
        ("sudo -n git push", "git", "push"),
        ("./scripts/run.sh --flag", "run.sh", None),
        ("C:\\tools\\bin\\node.exe app.js", "node.exe", None),
        ("cd repo && uv run pytest", "cd", None),
        ("uv run ruff check .", "uv", "run"),
        ("docker compose up -d", "docker", "compose"),
    ],
)
def test_argv0_and_subcommand(raw: str, argv0: str, sub: str | None) -> None:
    got_argv0, got_sub, _ = parse_command(raw)
    assert (got_argv0, got_sub) == (argv0, sub)


def test_unusable_command_is_none() -> None:
    assert sanitize_command("   ", key=KEY) is None
    assert sanitize_command(None, key=KEY) is None
    assert sanitize_command(123, key=KEY) is None


def test_weird_argv0_degrades_to_unknown() -> None:
    result = sanitize_command("$(evil) arg", key=KEY)
    assert result is not None
    assert result["argv0"] == "unknown"


def test_result_validates_against_the_model() -> None:
    result = sanitize_command("git push -u origin main", key=KEY, exit_code=1, duration_ms=12)
    assert result is not None
    model = SanitizedCommand.model_validate(result)
    assert (model.argv0, model.subcommand, model.exit_code) == ("git", "push", 1)
    assert model.command_hash is not None


def test_hash_is_keyed_and_stable() -> None:
    a = sanitize_command("npm test", key=KEY)
    b = sanitize_command("npm   test", key=KEY)  # whitespace-normalized
    c = sanitize_command("npm test", key=b"z" * 32)
    d = sanitize_command("npm test --x", key=KEY)
    assert a is not None and b is not None and c is not None and d is not None
    assert a["command_hash"] == b["command_hash"]
    assert a["command_hash"] != c["command_hash"]
    assert a["command_hash"] != d["command_hash"]


def test_no_key_means_no_hash_and_privacy_knobs_apply() -> None:
    result = sanitize_command("npm test", key=None)
    assert result is not None and "command_hash" not in result
    off = sanitize_command("npm test", key=KEY, store_display=False, hash_commands=False)
    assert off is not None
    assert "display" not in off and "command_hash" not in off


def test_display_is_single_line_printable_and_bounded() -> None:
    nasty = "echo a\nb\tc\x1b[31m\u202e" + "x" * 500
    result = sanitize_command(nasty, key=KEY)
    assert result is not None
    display = result["display"]
    assert isinstance(display, str)
    assert display.isprintable() and "\n" not in display and len(display) <= 200
    assert result["display_truncated"] is True


def test_truncation_prefers_token_boundaries() -> None:
    text, cut = truncate_display("alpha beta gamma delta epsilon zeta", 20)
    assert cut and text.endswith("...") and len(text) <= 20
    assert " " not in text.removesuffix("...").strip() or text.startswith("alpha beta")
    assert truncate_display("short", 20) == ("short", False)


@pytest.mark.parametrize(
    ("raw", "gone"),
    [
        ("API_TOKEN=abc123def456 npm run build", "abc123def456"),
        ("deploy --token s3cr3tvalue", "s3cr3tvalue"),
        ("deploy --password=hunter2hunter2", "hunter2hunter2"),
        ("curl -H 'Authorization: Bearer abcdef.12345.zzzz' https://x.test", "abcdef.12345"),
        ("curl https://user:pa55w0rd@host.test/path", "pa55w0rd"),
        ("curl 'https://h.test/x?api_key=SECRETVALUE1&a=1'", "SECRETVALUE1"),
        ("echo sk-abcdefghijklmnopqrstuvwxyz0123", "sk-abcdefghijklmnopqrstuvwxyz0123"),
        ("echo ghp_abcdefghijklmnopqrstuvwxyz0123456789", "ghp_abcdefghij"),
        ("echo AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
        ("mail someone@example.com -s hi", "someone@example.com"),
        ("curl -u admin:topsecretpw http://x.test", "topsecretpw"),
        ('curl -d \'{"password": "p4ssw0rd!!", "u": 1}\' x', "p4ssw0rd"),
        ("echo eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N", "eyJhbG"),
    ],
)
def test_secrets_are_redacted(raw: str, gone: str) -> None:
    out = redact_command(raw, parse_command(raw)[0])
    assert gone not in out, out
    assert "<redacted>" in out or "<email>" in out


def test_private_key_block_is_redacted() -> None:
    raw = (
        "cat > k <<EOF\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\nabcdef\n"
        "-----END RSA PRIVATE KEY-----\nEOF"
    )
    out = redact_command(raw, "cat")
    assert "MIIEow" not in out and "BEGIN RSA" not in out


def test_ordinary_commands_stay_readable() -> None:
    raw = "uv run pytest tests/unit/test_hook_sanitize.py -q -k redact"
    assert redact_command(raw, "uv") == raw
    sha = "a" * 40
    assert sha in redact_command(f"git show {sha}", "git")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pytest -q", True),
        ("uv run pytest tests/", True),
        ("python3 -m pytest", True),
        ("npm test", True),
        ("npm run lint", True),
        ("cargo test --all", True),
        ("go test ./...", True),
        ("make check", True),
        ("cd x && ruff check .", True),
        ("git status", False),
        ("ls -la", False),
        ("npm install", False),
        ("echo hello", False),
    ],
)
def test_is_verify_command(raw: str, expected: bool) -> None:
    argv0, sub, _ = parse_command(raw)
    assert is_verify_command(argv0, sub, raw) is expected


# ------------------------------------------------------------------ paths


def test_paths_are_workspace_relative(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / "src").mkdir(parents=True)
    resolver = PathResolver([str(root)])
    assert resolver.relativize(str(root / "src" / "a.py")) == "src/a.py"
    assert resolver.relativize("src/b.py") == "src/b.py"  # relative -> first root
    assert resolver.relativize(str(root / "new" / "deep" / "c.py")) == "new/deep/c.py"


def test_paths_outside_roots_and_junk_are_external(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    resolver = PathResolver([str(root)])
    for raw in (
        str(other / "x"),
        str(root / ".." / "other" / "x"),
        "../escape.txt",
        str(root),
        "",
        "a\x00b",
        "x" * 5000,
        None,
        42,
    ):
        assert resolver.relativize(raw) == EXTERNAL, raw


def test_symlink_escape_is_external(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "secret"
    outside.mkdir()
    (outside / "f.txt").write_text("x", encoding="utf-8")
    try:
        os.symlink(outside, root / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    resolver = PathResolver([str(root)])
    assert resolver.relativize(str(root / "link" / "f.txt")) == EXTERNAL


def test_symlinked_workspace_root_resolves(tmp_path: Path) -> None:
    real = tmp_path / "real"
    (real / "src").mkdir(parents=True)
    link = tmp_path / "alias"
    try:
        os.symlink(real, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    resolver = PathResolver([str(link)])
    assert resolver.relativize(str(link / "src" / "a.py")) == "src/a.py"
    assert resolver.relativize(str(real / "src" / "a.py")) == "src/a.py"


def test_windows_style_input_never_leaks_on_posix(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX-only expectation")
    resolver = PathResolver([str(tmp_path)])
    # A drive-letter or backslash path is not absolute on POSIX; it must not become a
    # relative path containing backslashes.
    result = resolver.relativize("C:\\Users\\me\\secret.txt")
    assert result == EXTERNAL or ("\\" not in result and ":" not in result)


def test_non_absolute_roots_are_ignored() -> None:
    assert PathResolver(["relative/root", "", 5]).roots == []  # type: ignore[list-item]
