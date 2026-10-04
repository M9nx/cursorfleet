"""Step 0: the state-layer artifact scanner (self-reported events, validation problems)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cursorfleet.events.kinds import Attribution, EventKind, Source
from cursorfleet.state.artifact_scan import (
    MAX_ARTIFACT_FILES,
    PROBLEM_TEXT,
    ArtifactScanner,
)
from cursorfleet.state.reducer import reduce_events

WORK = ".cursorfleet/work"
BODY_SECRET = "SECRET-BODY-TOKEN-9f31"  # noqa: S105 - synthetic canary


def artifact(  # noqa: PLR0913
    kind: str = "plan.created",
    *,
    task: str = "add-login",
    role: str = "architect",
    created: str = "2026-10-04T12:00:00Z",
    extra: str = "",
    body: str = "Free text body.",
) -> str:
    return (
        "---\n"
        "schema: cursorfleet.artifact/1\n"
        f"kind: {kind}\n"
        f"task: {task}\n"
        f"author_role: {role}\n"
        f"created: {created}\n"
        f"{extra}"
        "---\n"
        f"{body}\n"
    )


def put(root: Path, rel: str, text: str) -> Path:
    path = root / WORK / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_artifacts_become_self_reported_events(tmp_path: Path) -> None:
    put(
        tmp_path,
        "add-login/01-plan-architect.md",
        artifact("plan.created", extra='issue_ref: "#12"\n'),
    )
    put(
        tmp_path,
        "add-login/02-handoff-implementer.md",
        artifact(
            "handoff.created",
            role="implementer",
            created="2026-10-04T13:00:00Z",
            extra="to_role: reviewer\ncontext_refs:\n  - src/app.py\n",
        ),
    )
    put(tmp_path, "add-login/03-blocker-tester.md", artifact("blocker.raised", role="tester"))
    put(tmp_path, "add-login/04-context-scout.md", artifact("context.loaded", role="scout"))
    scan = ArtifactScanner().scan([str(tmp_path)])
    assert scan.issues == []
    assert {e.kind for e in scan.events} == {
        EventKind.PLAN_CREATED,
        EventKind.HANDOFF_CREATED,
        EventKind.BLOCKER_RAISED,
        EventKind.CONTEXT_LOADED,
    }
    for event in scan.events:
        assert event.source is Source.SELF_REPORTED
        assert event.attribution is Attribution.UNKNOWN
        assert event.session_id == "work:add-login"
        assert event.producer.value == "work_artifact"
    handoff = next(r for r in scan.records if r.kind == "handoff.created")
    assert handoff.to_role == "reviewer"
    assert handoff.context_refs == ("src/app.py",)
    plan_event = next(e for e in scan.events if e.kind is EventKind.PLAN_CREATED)
    assert plan_event.issue_ref == "#12"


def test_events_feed_the_reducer_without_claiming_observation(tmp_path: Path) -> None:
    put(tmp_path, "t1/01-blocker-tester.md", artifact("blocker.raised", task="t1", role="tester"))
    sessions = reduce_events(ArtifactScanner().scan([str(tmp_path)]).events)
    agent = sessions["work:t1"].agents["tester"]
    assert agent.blockers == 1
    assert agent.lane.value == "blocked"
    assert agent.lane_source is Source.SELF_REPORTED
    assert agent.last_live_ts is None  # never counts as live telemetry


def test_invalid_artifacts_are_issues_with_fixed_text_not_file_content(tmp_path: Path) -> None:
    put(tmp_path, "t1/01-plan-a.md", artifact(task="t1", role="a", extra=f"bogus: {BODY_SECRET}\n"))
    put(tmp_path, "t1/02-plan-a.md", "no frontmatter at all " + BODY_SECRET)
    put(tmp_path, "t1/03-plan-a.md", artifact(task="other"))
    put(tmp_path, "t1/04-plan-a.md", artifact(task="t1", created="not-a-date"))
    put(tmp_path, "loose.md", artifact())
    put(
        tmp_path,
        "t1/05-plan-a.md",
        artifact(task="t1", extra="context_refs:\n  - ../../etc/passwd\n"),
    )
    scan = ArtifactScanner().scan([str(tmp_path)])
    assert scan.records == []
    codes = {i.code for i in scan.issues}
    assert {
        "artifact.unknown_key",
        "artifact.frontmatter",
        "artifact.task",
        "artifact.created",
        "artifact.location",
        "artifact.context_refs",
    } <= codes
    for issue in scan.issues:
        assert issue.message == PROBLEM_TEXT[issue.code]
        assert BODY_SECRET not in issue.message
        assert BODY_SECRET not in issue.path


def test_body_is_never_kept(tmp_path: Path) -> None:
    put(tmp_path, "t1/01-plan-a.md", artifact(task="t1", role="a", body=BODY_SECRET))
    scan = ArtifactScanner().scan([str(tmp_path)])
    blob = repr(scan.records) + "".join(e.model_dump_json() for e in scan.events)
    assert BODY_SECRET not in blob


def test_event_ids_are_stable_and_body_edits_do_not_change_identity(tmp_path: Path) -> None:
    path = put(tmp_path, "t1/01-plan-a.md", artifact(task="t1", role="a", body="one"))
    first = ArtifactScanner().scan([str(tmp_path)]).events[0].event_id
    path.write_text(artifact(task="t1", role="a", body="two, longer"), encoding="utf-8")
    assert ArtifactScanner().scan([str(tmp_path)]).events[0].event_id == first
    path.write_text(artifact(task="t1", role="a", extra="issue_ref: X-1\n"), encoding="utf-8")
    assert ArtifactScanner().scan([str(tmp_path)]).events[0].event_id != first


def test_oversize_binary_and_symlink_are_reported_not_fatal(tmp_path: Path) -> None:
    put(tmp_path, "t1/01-plan-a.md", "x" * (70 * 1024))
    bad = tmp_path / WORK / "t1" / "02-plan-a.md"
    bad.write_bytes(b"---\n\xff\xfe\n---\n")
    target = tmp_path / "outside.md"
    target.write_text(artifact(task="t1"), encoding="utf-8")
    link = tmp_path / WORK / "t1" / "03-plan-a.md"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("symlinks unavailable")
    scan = ArtifactScanner().scan([str(tmp_path)])
    assert {i.code for i in scan.issues} == {
        "artifact.too_large",
        "artifact.encoding",
        "artifact.symlink",
    }
    assert scan.records == []


def test_missing_work_dir_and_unreadable_root_are_empty(tmp_path: Path) -> None:
    scan = ArtifactScanner().scan([str(tmp_path), str(tmp_path / "does-not-exist")])
    assert scan.records == [] and scan.issues == [] and scan.files == 0


def test_same_artifact_in_two_worktrees_is_deduplicated(tmp_path: Path) -> None:
    text = artifact(task="t1", role="a")
    put(tmp_path / "wt1", "t1/01-plan-a.md", text)
    put(tmp_path / "wt2", "t1/01-plan-a.md", text)
    scan = ArtifactScanner().scan([str(tmp_path / "wt1"), str(tmp_path / "wt2")])
    assert len(scan.records) == 1 and len(scan.events) == 1


def test_scan_cache_rereads_only_changed_files(tmp_path: Path) -> None:
    path = put(tmp_path, "t1/01-plan-a.md", artifact(task="t1", role="a"))
    scanner = ArtifactScanner()
    assert len(scanner.scan([str(tmp_path)]).records) == 1
    path.write_text(artifact("blocker.raised", task="t1", role="a"), encoding="utf-8")
    second = scanner.scan([str(tmp_path)])
    assert [r.kind for r in second.records] == ["blocker.raised"]
    path.unlink()
    assert scanner.scan([str(tmp_path)]).records == []


def test_file_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cursorfleet.state.artifact_scan.MAX_ARTIFACT_FILES", 3)
    for n in range(6):
        put(tmp_path, f"t1/{n:02d}-plan-a.md", artifact(task="t1", role="a"))
    scan = ArtifactScanner().scan([str(tmp_path)])
    assert len(scan.records) == 3
    assert any(i.code == "artifact.too_many" for i in scan.issues)
    assert MAX_ARTIFACT_FILES == 2000


def test_issue_ref_outside_the_event_alphabet_is_kept_on_record_only(tmp_path: Path) -> None:
    put(
        tmp_path,
        "t1/01-plan-a.md",
        artifact(task="t1", role="a", extra='issue_ref: "Fix login (v2)"\n'),
    )
    scan = ArtifactScanner().scan([str(tmp_path)])
    assert scan.records[0].issue_ref == "Fix login (v2)"
    assert scan.events[0].issue_ref is None
