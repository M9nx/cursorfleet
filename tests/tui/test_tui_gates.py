"""Gate logic: independent signals, commit binding, STALE when HEAD moved, no aggregate."""

from __future__ import annotations

import pytest

from cursorfleet.events.models import Event
from cursorfleet.tui import gates
from cursorfleet.tui.gates import GATES, classify_command, evaluate, evidence_from_events
from m2_helpers import make_event

HEAD_A = "a" * 40
HEAD_B = "b" * 40
WT = "wt-0123456789ab"


def evt(  # noqa: PLR0913
    n: int,
    display: str,
    outcome: str = "ok",
    *,
    commit: str | None = HEAD_A,
    worktree: str | None = WT,
    minute: int = 0,
) -> Event:
    extra: dict[str, object] = {
        "source": "derived",
        "outcome": outcome,
        "command": {"argv0": display.split(maxsplit=1)[0], "display": display},
    }
    if commit:
        extra["commit"] = commit
    if worktree:
        extra["worktree_id"] = worktree
    return Event.model_validate(
        make_event(
            "s1", n, kind="test.completed", ts=f"2026-10-04T12:{minute:02d}:00.000Z", **extra
        )
    )


@pytest.mark.parametrize(
    ("display", "expected"),
    [
        ("pytest -q", ["unit_tests"]),
        ("uv run pytest tests/integration", ["integration_tests"]),
        ("uv run ruff check .", ["lint"]),
        ("uv run mypy src", ["type_check"]),
        ("npx tsc --noEmit", ["type_check"]),
        ("bandit -r src", ["security_checks"]),
        ("npm test", ["unit_tests"]),
        ("uv run ruff format .", []),
        (
            "uv run ruff check . && uv run mypy src && uv run pytest",
            ["lint", "type_check", "unit_tests"],
        ),
    ],
)
def test_classification(display: str, expected: list[str]) -> None:
    argv0 = display.split(maxsplit=1)[0]
    assert classify_command(argv0, None, display)[0] == expected


def test_all_ten_gates_always_listed_and_no_aggregate() -> None:
    rows = evaluate([], worktree_id=WT, head=HEAD_A)
    assert [r.gate for r in rows] == [g for g, _ in GATES]
    assert len(rows) == 10
    assert {r.state for r in rows} == {"unknown"}
    assert not any(hasattr(gates, name) for name in ("overall", "score", "aggregate", "ready"))


def test_pass_is_bound_to_head_and_goes_stale_when_head_moves() -> None:
    evidence = evidence_from_events([evt(1, "uv run pytest -q")])
    at_head = {r.gate: r for r in evaluate(evidence, worktree_id=WT, head=HEAD_A)}
    assert at_head["unit_tests"].state == "pass"
    moved = {r.gate: r for r in evaluate(evidence, worktree_id=WT, head=HEAD_B)}
    assert moved["unit_tests"].state == "stale"
    assert "STALE" in moved["unit_tests"].detail and "aaaaaaaa" in moved["unit_tests"].detail
    assert moved["lint"].state == "unknown"  # independent: other gates untouched


def test_abbreviated_commit_still_matches_head() -> None:
    evidence = evidence_from_events([evt(1, "pytest", commit="aaaaaaa")])
    row = next(r for r in evaluate(evidence, worktree_id=WT, head=HEAD_A) if r.gate == "unit_tests")
    assert row.state == "pass"


def test_failing_run_is_fail_and_latest_wins() -> None:
    events = [evt(1, "pytest", "failed", minute=1), evt(2, "pytest", "ok", minute=2)]
    rows = evaluate(evidence_from_events(events), worktree_id=WT, head=HEAD_A)
    assert next(r for r in rows if r.gate == "unit_tests").state == "pass"
    events = [evt(1, "pytest", "ok", minute=1), evt(2, "pytest", "failed", minute=2)]
    rows = evaluate(evidence_from_events(events), worktree_id=WT, head=HEAD_A)
    assert next(r for r in rows if r.gate == "unit_tests").state == "fail"


def test_evidence_without_commit_or_head_stays_unknown() -> None:
    unbound = evidence_from_events([evt(1, "pytest", commit=None)])
    row = next(r for r in evaluate(unbound, worktree_id=WT, head=HEAD_A) if r.gate == "unit_tests")
    assert row.state == "unknown" and "not bound to a commit" in row.detail
    bound = evidence_from_events([evt(1, "pytest")])
    row = next(r for r in evaluate(bound, worktree_id=WT, head=None) if r.gate == "unit_tests")
    assert row.state == "unknown" and "HEAD unknown" in row.detail


def test_evidence_only_counts_for_its_own_worktree() -> None:
    evidence = evidence_from_events([evt(1, "pytest", worktree="wt-other0000000")])
    row = next(r for r in evaluate(evidence, worktree_id=WT, head=HEAD_A) if r.gate == "unit_tests")
    assert row.state == "unknown"


def test_chain_semantics() -> None:
    ok = evidence_from_events([evt(1, "uv run ruff check . && uv run pytest -q")])
    assert {e.gate: e.state for e in ok} == {"lint": "pass", "unit_tests": "pass"}
    failed = evidence_from_events([evt(1, "ruff check . && pytest", "failed")])
    assert {e.state for e in failed} == {"unknown"}  # which step failed is not knowable
    semi = evidence_from_events([evt(1, "ruff check . ; pytest")])
    assert {e.state for e in semi} == {"unknown"}


def test_gate_changed_events_count_but_unknown_names_do_not() -> None:
    changed = Event.model_validate(
        make_event(
            "s1",
            3,
            kind="gate.changed",
            gate={"name": "ci_status", "state": "failing"},
            commit=HEAD_A,
            worktree_id=WT,
            ts="2026-10-04T12:00:00.000Z",
        )
    )
    other = Event.model_validate(
        make_event(
            "s1",
            4,
            kind="gate.changed",
            gate={"name": "vibes", "state": "passing"},
            ts="2026-10-04T12:00:00.000Z",
        )
    )
    evidence = evidence_from_events([changed, other])
    assert [e.gate for e in evidence] == ["ci_status"]
    row = next(r for r in evaluate(evidence, worktree_id=WT, head=HEAD_A) if r.gate == "ci_status")
    assert row.state == "fail"


def test_non_observable_gates_never_pass_from_hooks_alone() -> None:
    events = [evt(1, "uv run pytest -q"), evt(2, "uv run ruff check .")]
    rows = evaluate(evidence_from_events(events), worktree_id=WT, head=HEAD_A)
    states = {r.gate: r.state for r in rows}
    for gate in (
        "independent_review",
        "re_review",
        "documentation",
        "ci_status",
        "merge_readiness",
    ):
        assert states[gate] == "unknown"
