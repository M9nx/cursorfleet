"""SR-01: adversarial commands must not stall the hook (regex denial of service).

Before the fix a single 64 KiB command made the redaction regexes run for 5-10 s, longer
than the hook timeout Cursor applies. Timings here are deliberately generous (the fixed
code needs milliseconds); they fail only if a quadratic path comes back.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from cursorfleet.adapters.cursor.hook_sanitize import redact_command, redact_text, sanitize_command
from m2_helpers import run_hook, spool_bytes

BUDGET_S = 1.5

ADVERSARIAL = {
    "letters": "a" * 65_536,
    "sensitive-name-run-after-quote": '"' + "token" * 13_000,
    "sensitive-name-run-after-semicolon": ";" + "token" * 13_000,
    "email-like-local-part": "a" * 30_000 + "." * 30_000,
    "dotted-domain": "a@" + "a." * 30_000,
    "at-signs": "a@" * 30_000,
    "many-header-words": "Authorization " * 4_000,
    "many-pem-starts": "-----BEGIN PRIVATE KEY----- " * 2_000,
    "quoted-keys": '"api_key" ' * 6_000,
    "query-pairs": "&a=b" * 16_000,
}


@pytest.mark.parametrize("name", sorted(ADVERSARIAL))
def test_sanitize_command_is_fast_on_adversarial_input(name: str) -> None:
    started = time.perf_counter()
    result = sanitize_command(ADVERSARIAL[name], key=b"k" * 32)
    elapsed = time.perf_counter() - started
    assert result is not None
    assert elapsed < BUDGET_S, f"{name}: {elapsed:.2f}s"
    display = result.get("display")
    assert not isinstance(display, str) or len(display) <= 200


@pytest.mark.parametrize("name", ["letters", "sensitive-name-run-after-quote"])
def test_redact_text_and_command_are_bounded_directly(name: str) -> None:
    started = time.perf_counter()
    redact_text(ADVERSARIAL[name])
    redact_command(ADVERSARIAL[name])
    assert time.perf_counter() - started < BUDGET_S


def test_hook_run_with_a_huge_hostile_command_is_fast_and_still_records(repo: Path) -> None:
    payload = {
        "hook_event_name": "preToolUse",
        "conversation_id": "redos-session",
        "tool_name": "Shell",
        "tool_use_id": "t1",
        "tool_input": {"command": "token" * 12_000},
        "workspace_roots": [str(repo)],
    }
    started = time.perf_counter()
    code, reply = run_hook(payload)
    elapsed = time.perf_counter() - started
    assert code == 0 and reply == '{"permission":"allow"}'
    assert elapsed < BUDGET_S, f"{elapsed:.2f}s"
    assert b"tool.started" in spool_bytes(repo)  # the event is kept, the display is bounded


def test_secret_inside_the_stored_prefix_is_still_redacted_with_a_long_tail() -> None:
    secret = "ghp_" + "A1b2C3d4E5" * 3
    raw = f"curl -H 'Authorization: Bearer {secret}' https://example.test/" + "x" * 5_000
    shown = sanitize_command(raw, key=None)
    assert shown is not None
    assert secret not in str(shown) and "<redacted>" in str(shown)


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("mysql -u root -pHunter2Hunter2 mydb", "Hunter2Hunter2"),
        ("mysqldump --single-transaction -pS3cretValue db", "S3cretValue"),
        ("sshpass -p S3cretValue ssh host uptime", "S3cretValue"),
        ("cd app && mysql -pS3cretValue -e 'select 1'", "S3cretValue"),
    ],
)
def test_attached_and_sshpass_password_forms_are_redacted(raw: str, secret: str) -> None:
    shown = sanitize_command(raw, key=None)
    assert shown is not None
    assert secret not in str(shown)
    assert "<redacted>" in str(shown)


def test_other_p_flags_are_left_alone() -> None:
    shown = sanitize_command("python -m pytest -pno:cacheprovider -p xdist", key=None)
    assert shown is not None and "-pno:cacheprovider" in str(shown)
