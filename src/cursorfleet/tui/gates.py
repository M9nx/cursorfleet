"""Display-only gate signals (v0.1 does NOT enforce anything).

Each gate is an independent signal with its own state: ``pass``, ``fail``, ``unknown`` or
``stale``. There is deliberately no aggregate score, count of passing gates or "ready" flag.

Evidence rules:

- Evidence comes only from ``test.completed`` events (a verify-looking shell command with
  its exit code, observed/derived from Cursor hooks) and ``gate.changed`` events. Anything
  an agent declares (artifacts, ``reviewed`` flags) is SELF-REPORTED and never counts
  (ADR 0006).
- Evidence is bound to the commit SHA recorded on the event. Evidence without a commit is
  ``unknown`` (it cannot be tied to a state of the code). When the worktree HEAD is known
  and differs, the gate is ``stale`` (the last result is still shown). When HEAD is not
  known (git disabled or the worktree is not linked), the gate stays ``unknown``.
- Classifying a command as unit tests, lint, type check and so on is a HEURISTIC over the
  sanitized command (``argv0``, subcommand, redacted display string). A chained command
  (``a && b``) that exits 0 supports every gate it contains; a failing chain says nothing
  reliable about which step failed, so its gates are ``unknown``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from cursorfleet.events.kinds import EventKind, GateState, Outcome
from cursorfleet.events.models import Event
from cursorfleet.state.models import utc

GATES: tuple[tuple[str, str], ...] = (
    ("unit_tests", "Unit tests"),
    ("integration_tests", "Integration tests"),
    ("type_check", "Type check"),
    ("lint", "Lint"),
    ("security_checks", "Security checks"),
    ("independent_review", "Independent review"),
    ("re_review", "Re-review"),
    ("documentation", "Documentation"),
    ("ci_status", "CI status"),
    ("merge_readiness", "Merge readiness"),
)
GATE_LABEL = dict(GATES)
OBSERVABLE = frozenset({"unit_tests", "integration_tests", "type_check", "lint", "security_checks"})

DISPLAY_ONLY = "display-only: v0.1 does not enforce gates"

_SPLIT = re.compile(r"\s*(&&|\|\||;|\|)\s*")
_WORDS = re.compile(r"[a-z0-9_.\-]+")
_LINT = {"ruff", "eslint", "flake8", "pylint", "golangci-lint", "shellcheck", "hadolint", "clippy"}
_TYPE = {"mypy", "pyright", "tsc", "typecheck", "type-check"}
_SECURITY = {"bandit", "semgrep", "trivy", "audit", "pip-audit", "gitleaks", "security"}


@dataclass(frozen=True)
class GateEvidence:
    gate: str
    state: str  # "pass" | "fail" | "unknown"
    ts: datetime
    commit: str | None
    worktree_id: str | None
    session_id: str
    agent: str | None
    origin: str  # "test.completed" | "gate.changed"
    command: str | None = None  # sanitized display, for the detail pane
    note: str | None = None


@dataclass(frozen=True)
class GateStatus:
    gate: str
    label: str
    state: str  # pass | fail | unknown | stale
    detail: str
    evidence: GateEvidence | None = None
    head: str | None = None


_UNIT = frozenset(
    {"pytest", "py.test", "jest", "vitest", "mocha", "rspec", "phpunit", "unittest", "ctest"}
    | {"tox", "nox", "test"}
)


def _classify_segment(words: list[str]) -> str | None:  # noqa: PLR0911
    """Gate for one command segment, or None if it is not a recognised verify step."""
    names = words
    joined = " ".join(names)
    if any(n in _LINT for n in names) and "format" not in names:
        return "lint"
    if any(n in _TYPE for n in names):
        return "type_check"
    if any(n in _SECURITY for n in names):
        return "security_checks"
    if "integration" in joined or "e2e" in joined:
        return "integration_tests"
    if any(n in _UNIT or n.startswith(("test:", "test-")) for n in names):
        return "unit_tests"
    if "lint" in joined:
        return "lint"
    if "check" in joined and "typ" in joined:
        return "type_check"
    return None


def classify_command(
    argv0: str | None, subcommand: str | None, display: str | None
) -> tuple[list[str], bool]:
    """Return ``(gates, chain_is_all_and)`` for a sanitized command.

    ``chain_is_all_and`` is True when the command has one segment or only ``&&`` joins, so a
    zero exit code implies every segment succeeded.
    """
    text = (display or " ".join(p for p in (argv0, subcommand) if p)).lower()
    parts = _SPLIT.split(text)
    segments = parts[0::2]
    separators = parts[1::2]
    gates: list[str] = []
    for segment in segments:
        gate = _classify_segment(_WORDS.findall(segment))
        if gate is not None and gate not in gates:
            gates.append(gate)
    return gates, all(s == "&&" for s in separators)


def _outcome_state(outcome: Outcome | None) -> str:
    if outcome is Outcome.OK:
        return "pass"
    if outcome is Outcome.FAILED:
        return "fail"
    return "unknown"


def evidence_from_events(events: Iterable[Event]) -> list[GateEvidence]:
    """Turn ``test.completed`` and ``gate.changed`` events into per-gate evidence."""
    found: list[GateEvidence] = []
    for event in events:
        if event.kind is EventKind.GATE_CHANGED and event.gate is not None:
            if event.gate.name in GATE_LABEL:
                state = {GateState.PASSING: "pass", GateState.FAILING: "fail"}.get(
                    event.gate.state, "unknown"
                )
                found.append(_evidence(event, event.gate.name, state, "gate.changed"))
        elif event.kind is EventKind.TEST_COMPLETED and event.command is not None:
            cmd = event.command
            gates, all_and = classify_command(cmd.argv0, cmd.subcommand, cmd.display)
            state = _outcome_state(event.outcome)
            note = None
            if len(gates) > 1 and not (state == "pass" and all_and):
                state = "unknown"
                note = "chained command: a single exit code does not identify which step failed"
            elif len(gates) > 1:
                note = "chained command with && only: every step succeeded"
            shown = cmd.display or " ".join(p for p in (cmd.argv0, cmd.subcommand) if p)
            found.extend(
                _evidence(event, gate, state, "test.completed", command=shown, note=note)
                for gate in gates
            )
    return found


def _evidence(  # noqa: PLR0913
    event: Event,
    gate: str,
    state: str,
    origin: str,
    *,
    command: str | None = None,
    note: str | None = None,
) -> GateEvidence:
    return GateEvidence(
        gate=gate,
        state=state,
        ts=utc(event.ts),
        commit=event.commit,
        worktree_id=event.worktree_id,
        session_id=event.session_id,
        agent=event.agent_id,
        origin=origin,
        command=command,
        note=note,
    )


def _same_commit(evidence_commit: str, head: str) -> bool:
    shorter, longer = sorted((evidence_commit.lower(), head.lower()), key=len)
    return longer.startswith(shorter)


def evaluate(
    evidence: Iterable[GateEvidence], *, worktree_id: str | None, head: str | None
) -> list[GateStatus]:
    """All ten gates for one worktree. ``head`` is its current HEAD, if known."""
    latest: dict[str, GateEvidence] = {}
    for item in evidence:
        if item.worktree_id != worktree_id:  # evidence only counts for its own worktree
            continue
        current = latest.get(item.gate)
        if current is None or (item.ts, item.session_id) > (current.ts, current.session_id):
            latest[item.gate] = item
    rows: list[GateStatus] = []
    for gate, label in GATES:
        found = latest.get(gate)
        if found is None:
            why = "no evidence" if gate in OBSERVABLE else "no evidence (not observable by hooks)"
            rows.append(GateStatus(gate, label, "unknown", why, None, head))
            continue
        rows.append(_judge(gate, label, found, head))
    return rows


def _judge(gate: str, label: str, item: GateEvidence, head: str | None) -> GateStatus:
    sha = item.commit[:8] if item.commit else None
    if item.commit is None:
        return GateStatus(
            gate, label, "unknown", f"last result {item.state}, not bound to a commit", item, head
        )
    if head is None:
        return GateStatus(
            gate,
            label,
            "unknown",
            f"last result {item.state} @{sha}; current HEAD unknown",
            item,
            head,
        )
    if not _same_commit(item.commit, head):
        return GateStatus(
            gate,
            label,
            "stale",
            f"STALE: was {item.state} @{sha}, HEAD is now @{head[:8]}",
            item,
            head,
        )
    if item.state == "unknown":
        return GateStatus(gate, label, "unknown", f"result unclear @{sha}", item, head)
    return GateStatus(gate, label, item.state, f"{item.state} @{sha} (HEAD)", item, head)


def evaluate_all(
    evidence: list[GateEvidence], heads: Mapping[str | None, str | None]
) -> dict[str | None, list[GateStatus]]:
    """Statuses per worktree id; ``None`` collects evidence not tied to a known worktree."""
    return {wt: evaluate(evidence, worktree_id=wt, head=head) for wt, head in heads.items()}
