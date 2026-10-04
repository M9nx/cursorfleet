"""Nothing sensitive may reach the spool: corpus tests, property tests, import hygiene."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from cursorfleet.events.models import Event
from m2_helpers import ALL_HOOKS, doc_payload, init_repo, paths_of, plant_install_marker, run_hook

SPOOL_SETTINGS = settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)

# ------------------------------------------------------------------ synthetic secrets corpus
# Every value below is fabricated; none is a live credential.
# Slack uses a non-matching synthetic shape (underscore, no digit run) on
# purpose: GitHub push protection treats realistic xox[bpars]- tokens as secrets.

SECRETS: dict[str, str] = {
    "openai": "sk-proj-AbCdEfGhIjKlMnOpQrStUv123456",
    "github_pat": "ghp_" + "aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5",
    "github_fine": "github_pat_11ABCDEFG0abcdefghij_klmnopqrstuvwxyz0123456789",
    "aws_access": "AKIAIOSFODNN7EXAMPLE",
    "slack": "xoxb_SYNTHETIC_not_a_token",
    "stripe": "sk_live_" + "abcdefghijklmnopqrstuvwx",
    "google": "AIza" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q",
    "jwt": (
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    ),
    "npm": "npm_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
    "gitlab": "glpat-abcdefghij1234567890",
    "random_password": "Tr0ub4dor&3-correct-horse",
    "hex_blob": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "base64_blob": "dGhpcyBpcyBhIHNlY3JldCB0b2tlbiB2YWx1ZSE9Zg",
}

CONTEXTS: list[str] = [
    "export API_TOKEN={s} && npm run build",
    "DB_PASSWORD={s} ./migrate.sh",
    "tool --token {s}",
    "tool --token={s}",
    "tool --password {s} --verbose",
    "tool --api-key {s}",
    "curl -H 'Authorization: Bearer {s}' https://api.example.test/v1",
    'curl -H "Authorization: token {s}" https://api.example.test/v1',
    "curl -H 'X-Api-Key: {s}' https://api.example.test/v1",
    "curl --header 'Cookie: session={s}' https://example.test",
    "git clone https://deploy:{s}@git.example.test/o/r.git",
    "curl 'https://api.example.test/p?access_token={s}&a=1'",
    "curl -u admin:{s} https://example.test",
    'curl -d \'{{"password": "{s}", "user": "u"}}\' https://example.test',
    "echo {s}",
    "printf '%s' {s} | tool login",
]
# Plain `echo <secret>` is only caught for recognisable formats; see KNOWN_FORMAT below.
KNOWN_FORMAT = {
    "openai",
    "github_pat",
    "github_fine",
    "aws_access",
    "stripe",
    "google",
    "jwt",
    "npm",
    "gitlab",
    "base64_blob",
}  # bare 40/64-hex strings are kept on purpose: commit ids and file digests
BARE_CONTEXTS = {"echo {s}", "printf '%s' {s} | tool login"}

EMAILS = ["alice@example.com", "bob.smith+tag@sub.example.co.uk", "x_y@corp-internal.io"]
PEM = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAAB\n"
    "AAAAMwAAAAtzc2gtZWQyNTUxOQAAACD0000000000000000000000000000000000000000000000000\n"
    "-----END OPENSSH PRIVATE KEY-----"
)


def corpus() -> Iterator[tuple[str, str, str]]:
    for context in CONTEXTS:
        for name, secret in SECRETS.items():
            if context in BARE_CONTEXTS and name not in KNOWN_FORMAT:
                continue
            yield f"{name}|{context}", context.format(s=secret), secret


def session_bytes(repo_root: Path, session: str) -> bytes:
    chunks = []
    spool = Path(paths_of(repo_root).spool)
    if spool.exists():
        for file in sorted(spool.rglob("*")):
            if file.is_file() and session in str(file.parent):
                chunks.append(file.read_bytes())
    return b"".join(chunks)


def tool_payload(repo_root: Path, command: str, hook: str = "preToolUse") -> dict[str, Any]:
    payload = doc_payload(hook)
    payload["workspace_roots"] = [str(repo_root)]
    if hook in {"beforeShellExecution", "afterShellExecution"}:
        payload["command"] = command
    else:
        payload["tool_input"] = {"command": command, "working_directory": str(repo_root)}
    payload["conversation_id"] = "corpus-session"
    return payload


@pytest.mark.parametrize("hook", ["preToolUse", "postToolUse", "beforeShellExecution"])
def test_secret_corpus_never_reaches_the_spool(hook: str, repo: Path) -> None:
    cases = list(corpus())
    assert len(cases) > 100
    for _label, command, _secret in cases:
        run_hook(tool_payload(repo, command, hook))
    blob = session_bytes(repo, "corpus-session")
    assert blob
    text = blob.decode("utf-8")
    leaks = [label for label, _c, secret in cases if secret in text]
    assert leaks == []
    for line in blob.splitlines():
        Event.model_validate(json.loads(line[9:]))


def test_emails_urls_and_pem_blocks_are_removed(repo: Path) -> None:
    commands = [f"git log --author={mail}" for mail in EMAILS]
    commands += [f"mail -s hi {mail}" for mail in EMAILS]
    commands.append(f"cat <<EOF > key\n{PEM}\nEOF")
    commands.append(f"echo '{PEM}'")
    for command in commands:
        run_hook(tool_payload(repo, command))
    text = session_bytes(repo, "corpus-session").decode("utf-8")
    for mail in EMAILS:
        assert mail not in text
    assert "b3BlbnNzaC1rZXk" not in text and "PRIVATE KEY" not in text


def test_display_can_be_turned_off_entirely(repo: Path) -> None:
    cfg = repo / ".cursorfleet"
    cfg.mkdir(exist_ok=True)
    (cfg / "config.toml").write_text("[privacy]\nstore_command_display = false\n", encoding="utf-8")
    command = "curl --novel-flag unusual-secret-xyz-123456789 example.test"
    run_hook(tool_payload(repo, command))
    text = session_bytes(repo, "corpus-session").decode("utf-8")
    assert "unusual-secret" not in text and "novel-flag" not in text
    assert '"argv0":"curl"' in text


# ------------------------------------------------------------------ forbidden payload fields

FORBIDDEN_FIELDS = {
    "prompt": "SENTINELprompt",
    "text": "SENTINELtext",
    "thinking": "SENTINELthinking",
    "user_email": "SENTINELuser@private.example",
    "transcript_path": "/home/SENTINELtranscript",
    "agent_transcript_path": "/home/SENTINELagent",
    "file_content": "SENTINELfilecontent",
    "content": "SENTINELcontent",
    "output": "SENTINELoutput",
    "stdout": "SENTINELstdout",
    "stderr": "SENTINELstderr",
    "summary": "SENTINELsummary",
    "task": "SENTINELtask",
    "description": "SENTINELdescription",
    "agent_message": "SENTINELagentmessage",
    "error_message": "SENTINELerror",
    "failure_type": "SENTINELfailure",
    "edits": [{"old_string": "SENTINELold", "new_string": "SENTINELnew"}],
    "modified_files": ["SENTINELmodified.py"],
    "cwd": "/SENTINELcwd",
    "env": {"TOKEN": "SENTINELenv"},
    "attachments": [{"file_path": "/SENTINELattach"}],
    "model": "SENTINELmodel",
    "model_params": [{"id": "x", "value": "SENTINELparam"}],
}


@pytest.mark.parametrize("hook", ALL_HOOKS)
def test_forbidden_fields_never_reach_the_spool(hook: str, repo: Path) -> None:
    payload = doc_payload(hook)
    payload.update(FORBIDDEN_FIELDS)
    payload["workspace_roots"] = [str(repo)]
    payload["conversation_id"] = "sentinel-session"
    if isinstance(payload.get("tool_input"), dict):
        payload["tool_input"].update({"contents": "SENTINELbody", "env": {"A": "SENTINELenv2"}})
    if "tool_output" in payload:
        payload["tool_output"] = json.dumps({"exitCode": 2, "stdout": "SENTINELtoolout"})
    environ = {"SECRET_TOKEN": "SENTINELenviron", "HOME": "/home/SENTINELhome"}
    run_hook(payload, environ=environ)
    blob = session_bytes(repo, "sentinel-session")
    assert blob, hook
    assert b"SENTINEL" not in blob and b"private.example" not in blob


def test_runtime_dir_holds_no_prompt_like_content_for_any_hook(repo: Path) -> None:
    for hook in ALL_HOOKS:
        payload = doc_payload(hook)
        payload["workspace_roots"] = [str(repo)]
        payload["prompt"] = "SENTINELprompt"
        run_hook(payload, environ={"X": "SENTINELenv"})
    root = Path(paths_of(repo).root)
    for file in root.rglob("*"):
        if file.is_file() and file.name != "hmac.key":
            assert b"SENTINEL" not in file.read_bytes(), file


# ------------------------------------------------------------------ Hypothesis properties


@pytest.fixture(scope="module")
def shared_repo(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    root = init_repo(tmp_path_factory.mktemp("prop") / "repo")
    plant_install_marker(root)
    previous = os.getcwd()
    os.chdir(root)
    try:
        yield root
    finally:
        os.chdir(previous)


_counter = {"n": 0}


def fresh_session() -> str:
    _counter["n"] += 1
    return f"prop-{_counter['n']}"


secret_values = st.from_regex(r"[A-Za-z0-9]{16,40}", fullmatch=True)
names = st.sampled_from(["API_KEY", "MY_SECRET", "DB_PASSWORD", "AUTH_TOKEN", "ACCESS_KEY"])
flags = st.sampled_from(["--token", "--password", "--api-key", "--secret", "--auth-token"])
safe_word = st.from_regex(r"[a-z]{3,12}", fullmatch=True)


@st.composite
def secret_commands(draw: st.DrawFn) -> tuple[str, str]:
    secret = draw(secret_values)
    word = draw(safe_word)
    template = draw(
        st.sampled_from(
            [
                "export {n}={s} && {w} run",
                "{n}={s} {w} build",
                "{w} {f} {s}",
                "{w} {f}={s} -v",
                "curl -H 'Authorization: Bearer {s}' https://{w}.example.test",
                "curl -H 'X-Api-Key: {s}' https://{w}.example.test",
                "git clone https://u:{s}@{w}.example.test/o/r.git",
                "curl 'https://{w}.example.test/p?access_token={s}&a=1'",
                "curl -u admin:{s} https://{w}.example.test",
                '{w} --data \'{{"password": "{s}"}}\'',
            ]
        )
    )
    command = template.format(n=draw(names), f=draw(flags), s=secret, w=word)
    return command, secret


@SPOOL_SETTINGS
@given(case=secret_commands())
def test_property_marked_secrets_never_reach_the_spool(
    case: tuple[str, str], shared_repo: Path
) -> None:
    command, secret = case
    session = fresh_session()
    payload = tool_payload(shared_repo, command)
    payload["conversation_id"] = session
    code, _ = run_hook(payload)
    assert code == 0
    assert secret.encode() not in session_bytes(shared_repo, session)


@SPOOL_SETTINGS
@given(
    local=st.from_regex(r"[a-z][a-z0-9._]{2,12}", fullmatch=True),
    domain=st.from_regex(r"[a-z]{3,10}\.(com|org|io)", fullmatch=True),
    word=safe_word,
)
def test_property_email_addresses_are_removed(
    local: str, domain: str, word: str, shared_repo: Path
) -> None:
    assume(local != "git")
    mail = f"{local}@{domain}"
    session = fresh_session()
    payload = tool_payload(shared_repo, f"{word} --author {mail} --since yesterday")
    payload["conversation_id"] = session
    run_hook(payload)
    assert mail.encode() not in session_bytes(shared_repo, session)


json_leaf = st.one_of(
    st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False), st.text(max_size=40)
)
json_value = st.recursive(
    json_leaf,
    lambda inner: st.one_of(
        st.lists(inner, max_size=4), st.dictionaries(st.text(max_size=12), inner, max_size=5)
    ),
    max_leaves=12,
)


@SPOOL_SETTINGS
@given(
    hook=st.sampled_from(ALL_HOOKS),
    extra=st.dictionaries(st.text(max_size=12), json_value, max_size=6),
    sentinel=st.from_regex(r"ZQX[0-9a-f]{12}", fullmatch=True),
)
def test_property_unknown_fields_are_dropped_and_events_stay_valid(
    hook: str, extra: dict[str, Any], sentinel: str, shared_repo: Path
) -> None:
    session = fresh_session()
    payload = doc_payload(hook)
    payload["workspace_roots"] = [str(shared_repo)]
    allow = {"hook_event_name", "conversation_id", "session_id"}
    payload.update({k: v for k, v in extra.items() if k not in allow})
    payload["conversation_id"] = session
    payload["__novel_field__"] = sentinel
    payload["prompt"] = sentinel
    code, out = run_hook(payload)
    assert code == 0 and out in {"{}", '{"permission":"allow"}'}
    blob = session_bytes(shared_repo, session)
    assert sentinel.encode() not in blob
    for line in blob.splitlines():
        Event.model_validate(json.loads(line[9:]))


@SPOOL_SETTINGS
@given(data=st.binary(max_size=2000))
def test_property_arbitrary_stdin_never_crashes_or_writes(data: bytes, shared_repo: Path) -> None:
    before = {p: p.stat().st_size for p in Path(paths_of(shared_repo).spool).rglob("*.jsonl")}
    code, out = run_hook(data)
    assert code == 0 and out in {"{}", '{"permission":"allow"}'}
    after = {p: p.stat().st_size for p in Path(paths_of(shared_repo).spool).rglob("*.jsonl")}
    assert after == before


# ------------------------------------------------------------------ import hygiene

BANNED_PREFIXES = (
    "pydantic",
    "typer",
    "textual",
    "click",
    "rich",
    "sqlite3",
    "socket",
    "ssl",
    "http",
    "urllib",
    "asyncio",
    "requests",
    "email",
    "ftplib",
    "smtplib",
    "xmlrpc",
    "multiprocessing",
    "concurrent",
    "subprocess",
    "dataclasses",
    "pathlib",
    "typing",
)  # ``enum`` is excluded: ``re`` (needed by ``json``) imports it anyway

DRIVER = """
import json, sys, time
t0 = time.perf_counter()
from cursorfleet.adapters.cursor import hook_main
t1 = time.perf_counter()
code = hook_main.main()
sys.stderr.write(json.dumps({"mods": sorted(sys.modules), "import_s": t1 - t0, "code": code}))
"""


def run_driver(cwd: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    env = {k: v for k, v in os.environ.items() if k != "CURSOR_PROJECT_DIR"}
    done = subprocess.run(
        [sys.executable, "-c", DRIVER],
        input=json.dumps(payload).encode(),
        capture_output=True,
        cwd=cwd,
        env=env,
        timeout=60,
        check=True,
    )
    return json.loads(done.stderr), done.stdout.decode().strip()


def test_hook_path_imports_no_heavy_or_network_modules(repo: Path) -> None:
    for hook in ("sessionStart", "preToolUse", "postToolUse", "subagentStop"):
        payload = doc_payload(hook)
        payload["workspace_roots"] = [str(repo)]
        info, out = run_driver(repo, payload)
        assert info["code"] == 0 and out
        banned = sorted(m for m in info["mods"] if m.split(".")[0] in BANNED_PREFIXES)
        assert banned == [], f"{hook}: {banned}"
        assert not any(m.startswith("cursorfleet.") and "events.models" in m for m in info["mods"])


def test_hook_with_privacy_config_still_stays_light(repo: Path) -> None:
    cfg = repo / ".cursorfleet"
    cfg.mkdir(exist_ok=True)
    (cfg / "config.toml").write_text(
        "[privacy]\ncommand_display_max_chars = 80\n", encoding="utf-8"
    )
    payload = doc_payload("preToolUse")
    payload["workspace_roots"] = [str(repo)]
    info, _ = run_driver(repo, payload)
    heavy = set(BANNED_PREFIXES) - {"typing"}  # tomllib itself imports typing (user opt-in cost)
    assert not [m for m in info["mods"] if m.split(".")[0] in heavy]
    assert "tomllib" in info["mods"]


def test_hook_import_time_and_module_count_sanity(repo: Path) -> None:
    payload = doc_payload("stop")
    payload["workspace_roots"] = [str(repo)]
    info, _ = run_driver(repo, payload)
    # Generous, flake-free bounds. Real latency numbers live in docs/hook-latency.md and are
    # produced by scripts/bench_hook.py (not asserted here).
    assert info["import_s"] < 1.0
    cursorfleet_modules = [m for m in info["mods"] if m.split(".")[0] == "cursorfleet"]
    assert len(cursorfleet_modules) <= 14, cursorfleet_modules
