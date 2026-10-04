"""Display-only verification observations (v0.1 does NOT enforce gates).

Heuristic command classification may be listed here; it never satisfies a gate
(ADR 0011). PASS/FAIL gate tiles are intentionally not derived from tier 1-3 data.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from cursorfleet.events.kinds import VERIFICATION_KINDS, EventKind, Outcome
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
    state: str  # "observed" | "unknown" — never pass/fail for heuristics
    ts: datetime
    commit: str | None
    worktree_id: str | None
    session_id: str
    agent: str | None
    origin: str
    command: str | None = None
    note: str | None = None
    exit_outcome: str | None = None  # ok | failed | unknown from hook


@dataclass(frozen=True)
class GateStatus:
    gate: str
    label: str
    state: str  # not_evaluated | observed | unknown | stale
    detail: str
    evidence: GateEvidence | None = None
    head: str | None = None


_UNIT = frozenset(
    {"pytest", "py.test", "jest", "vitest", "mocha", "rspec", "phpunit", "unittest", "ctest"}
    | {"tox", "nox", "test"}
)


def _classify_segment(words: list[str]) -> str | None:  # noqa: PLR0911
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


def _outcome_label(outcome: Outcome | None) -> str:
    if outcome is Outcome.OK:
        return "ok"
    if outcome is Outcome.FAILED:
        return "failed"
    return "unknown"


def evidence_from_events(events: Iterable[Event]) -> list[GateEvidence]:
    """Heuristic verification observations; never mapped to PASS/FAIL gates."""
    found: list[GateEvidence] = []
    for event in events:
        if event.kind is EventKind.GATE_CHANGED and event.gate is not None:
            if event.gate.name in GATE_LABEL:
                found.append(
                    _evidence(
                        event,
                        event.gate.name,
                        "unknown",
                        "gate.changed",
                        note="gate.changed is not tier-4 evidence in v0.1",
                    )
                )
        elif event.kind in VERIFICATION_KINDS and event.command is not None:
            cmd = event.command
            gates, all_and = classify_command(cmd.argv0, cmd.subcommand, cmd.display)
            exit_label = _outcome_label(event.outcome)
            note = "heuristic observation; not proof of pass or fail"
            if len(gates) > 1 and not (exit_label == "ok" and all_and):
                note = (
                    "chained command: exit code does not identify which step ran; "
                    + note
                )
            elif len(gates) > 1:
                note = "chained && command; " + note
            shown = cmd.display or " ".join(p for p in (cmd.argv0, cmd.subcommand) if p)
            origin = (
                "verification.observed"
                if event.kind is EventKind.VERIFICATION_OBSERVED
                else "test.completed"
            )
            found.extend(
                _evidence(
                    event,
                    gate,
                    "observed",
                    origin,
                    command=shown,
                    note=note,
                    exit_outcome=exit_label,
                )
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
    exit_outcome: str | None = None,
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
        exit_outcome=exit_outcome,
    )


def _same_commit(evidence_commit: str, head: str) -> bool:
    shorter, longer = sorted((evidence_commit.lower(), head.lower()), key=len)
    return longer.startswith(shorter)


def evaluate(
    evidence: Iterable[GateEvidence], *, worktree_id: str | None, head: str | None
) -> list[GateStatus]:
    latest: dict[str, GateEvidence] = {}
    for item in evidence:
        if item.worktree_id != worktree_id:
            continue
        current = latest.get(item.gate)
        if current is None or (item.ts, item.session_id) > (current.ts, current.session_id):
            latest[item.gate] = item
    rows: list[GateStatus] = []
    for gate, label in GATES:
        found = latest.get(gate)
        if found is None:
            why = "not evaluated" if gate in OBSERVABLE else "not evaluated (not observable)"
            rows.append(GateStatus(gate, label, "not_evaluated", why, None, head))
            continue
        rows.append(_judge(gate, label, found, head))
    return rows


def _judge(gate: str, label: str, item: GateEvidence, head: str | None) -> GateStatus:
    sha = item.commit[:8] if item.commit else None
    exit_bit = f", exit {item.exit_outcome}" if item.exit_outcome else ""
    if item.commit is None:
        return GateStatus(
            gate,
            label,
            "observed",
            f"heuristic observation{exit_bit}; not bound to a commit",
            item,
            head,
        )
    if head is None:
        return GateStatus(
            gate,
            label,
            "observed",
            f"heuristic observation{exit_bit} @{sha}; HEAD unknown",
            item,
            head,
        )
    if not _same_commit(item.commit, head):
        return GateStatus(
            gate,
            label,
            "stale",
            f"STALE: observation{exit_bit} was @{sha}, HEAD now @{head[:8]}",
            item,
            head,
        )
    return GateStatus(
        gate,
        label,
        "observed",
        f"heuristic observation{exit_bit} @{sha} (HEAD)",
        item,
        head,
    )


def evaluate_all(
    evidence: list[GateEvidence], heads: Mapping[str | None, str | None]
) -> dict[str | None, list[GateStatus]]:
    return {wt: evaluate(evidence, worktree_id=wt, head=head) for wt, head in heads.items()}
