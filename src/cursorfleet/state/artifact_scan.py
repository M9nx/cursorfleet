"""Read-only scanner turning agent-declared artifacts into self-reported events (ADR 0006).

Artifacts (``<work dir>/<task>/<NN>-<kind>-<role>.md``, schema ``cursorfleet.artifact/1``)
are the only producer of ``plan.created``, ``handoff.created``, ``blocker.raised`` and
``context.loaded``. Everything here is SELF-REPORTED and untrusted:

- Only the validated frontmatter fields are kept (task slug, kind, author/target role,
  ``created``, ``issue_ref``, ``context_refs`` paths). The Markdown body is never stored,
  hashed, logged or displayed; there are no title or summary fields in the schema.
- An invalid artifact becomes an :class:`ArtifactIssue` carrying a *fixed* description for
  its problem code, never the parser's message (which may quote file content). The scan
  never raises: unreadable, oversized, symlinked and malformed files are reported.
- The scan never writes, follows symlinks, or reads past the size cap, and stops after
  ``MAX_ARTIFACT_FILES`` files.

Events derived from records use ``producer=work_artifact``, ``source=self_reported`` and
``attribution=unknown`` (``author_role`` is spoofable) in the synthetic session
``work:<task>``. Ids are deterministic (path + frontmatter hash), so rescans and the same
file appearing in several worktrees dedupe.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath

from pydantic import ValidationError

from cursorfleet import __version__
from cursorfleet.events.ids import new_event_id
from cursorfleet.events.models import Event
from cursorfleet.state.models import utc
from cursorfleet.workflow.artifacts import MAX_ARTIFACT_BYTES, validate_artifact_text
from cursorfleet.workflow.frontmatter import FrontmatterError, parse_frontmatter

DEFAULT_WORK_DIR = ".cursorfleet/work"
MAX_ARTIFACT_FILES = 2000
SESSION_PREFIX = "work:"

_MIN_TS = datetime(1971, 1, 1, tzinfo=UTC)
_MAX_TS = datetime(2200, 1, 1, tzinfo=UTC)

# Fixed, content-free descriptions. The parser's own messages can quote file content.
PROBLEM_TEXT: dict[str, str] = {
    "artifact.too_large": "file is larger than the 64 KiB artifact limit",
    "artifact.frontmatter": "frontmatter is missing or not in the strict subset",
    "artifact.missing_key": "a required frontmatter key is missing",
    "artifact.unknown_key": "frontmatter has a key outside the schema",
    "artifact.schema": "schema is not cursorfleet.artifact/1",
    "artifact.kind": "kind is not plan/handoff/blocker/context",
    "artifact.location": "artifact must live in <work dir>/<task>/<file>.md",
    "artifact.task": "task is not a slug equal to the directory name",
    "artifact.author_role": "author_role is not a safe id",
    "artifact.to_role": "to_role is not a safe id",
    "artifact.created": "created is not an ISO 8601 timestamp in a sane range",
    "artifact.issue_ref": "issue_ref is not short printable text",
    "artifact.context_refs": "context_refs is not a list of workspace-relative paths",
    "artifact.symlink": "symlinks are not read",
    "artifact.unreadable": "file could not be read",
    "artifact.encoding": "file is not valid UTF-8",
    "artifact.too_many": f"scan stopped after {MAX_ARTIFACT_FILES} files",
    "artifact.event_invalid": "frontmatter values do not fit the event model",
}


@dataclass(frozen=True)
class ArtifactRecord:
    """Validated frontmatter of one artifact. Self-reported; the body is not kept."""

    path: str  # relative to the work dir, "/" separated: "<task>/<file>.md"
    task: str
    kind: str  # plan.created | handoff.created | blocker.raised | context.loaded
    author_role: str
    created: datetime
    to_role: str | None = None
    issue_ref: str | None = None
    context_refs: tuple[str, ...] = ()
    fingerprint: str = ""  # sha256(path + frontmatter)[:16]

    @property
    def session_id(self) -> str:
        return SESSION_PREFIX + self.task


@dataclass(frozen=True)
class ArtifactIssue:
    path: str  # relative to the work dir
    code: str

    @property
    def message(self) -> str:
        return PROBLEM_TEXT.get(self.code, "artifact problem")


@dataclass
class ArtifactScan:
    records: list[ArtifactRecord] = field(default_factory=list)
    issues: list[ArtifactIssue] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)  # self-reported, one per valid record
    files: int = 0  # candidate files examined


def record_to_event(record: ArtifactRecord) -> Event | None:
    """Map a record onto the event model; ``None`` if the values do not fit it."""
    millis = int(record.created.timestamp() * 1000)
    seed = hashlib.sha256(f"{record.path}\0{record.fingerprint}".encode()).digest()[:10]
    refs: list[dict[str, str]] = [{"path": ref} for ref in record.context_refs]
    data: dict[str, object] = {
        "event_id": new_event_id(millis, seed),
        "ts": record.created.isoformat(),
        "producer": "work_artifact",
        "producer_version": __version__,
        "source": "self_reported",
        "kind": record.kind,
        "session_id": record.session_id,
        "agent_role": record.author_role,
        "attribution": "unknown",
        "paths": refs,
    }
    if record.issue_ref is not None:
        data["issue_ref"] = record.issue_ref
    try:
        return Event.model_validate(data)
    except ValidationError:
        # issue_ref allows more characters than the event field does: retry without it.
        data.pop("issue_ref", None)
        try:
            return Event.model_validate(data)
        except ValidationError:
            return None


def _parse_created(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = utc(parsed)
    return parsed if _MIN_TS <= parsed <= _MAX_TS else None


def _record_from_text(text: str, rel: str) -> ArtifactRecord | list[str]:
    """Validate ``text``; return the record, or the list of problem codes."""
    problems = [p.code for p in validate_artifact_text(text, rel)]
    if problems:
        return sorted(set(problems))
    try:
        doc = parse_frontmatter(text)
    except FrontmatterError:  # pragma: no cover - validate_artifact_text already parsed it
        return ["artifact.frontmatter"]
    meta = doc.meta
    created = _parse_created(meta.get("created"))
    if created is None:
        return ["artifact.created"]
    refs_raw = meta.get("context_refs", [])
    refs = tuple(r for r in refs_raw if isinstance(r, str)) if isinstance(refs_raw, list) else ()
    to_role = meta.get("to_role")
    issue = meta.get("issue_ref")
    # Fingerprint covers the frontmatter only, so editing the body never changes identity.
    frontmatter_only = text.replace("\r\n", "\n").split("\n---", 2)[0]
    fingerprint = hashlib.sha256(f"{rel}\0{frontmatter_only}".encode()).hexdigest()[:16]
    return ArtifactRecord(
        path=rel,
        task=str(meta["task"]),
        kind=str(meta["kind"]),
        author_role=str(meta["author_role"]),
        created=created,
        to_role=to_role if isinstance(to_role, str) else None,
        issue_ref=issue if isinstance(issue, str) else None,
        context_refs=refs,
        fingerprint=fingerprint,
    )


_CacheValue = tuple[int, int, "ArtifactRecord | list[str]"]


class ArtifactScanner:
    """Scans the work dir of one or more worktree roots; caches by ``(mtime_ns, size)``."""

    def __init__(self, work_rel: str = DEFAULT_WORK_DIR) -> None:
        self._work_rel = work_rel
        self._cache: dict[str, _CacheValue] = {}

    def scan(self, roots: Sequence[str]) -> ArtifactScan:
        """Scan every root (first one wins on duplicates). Never raises."""
        result = ArtifactScan()
        seen: set[tuple[str, str]] = set()
        live: set[str] = set()
        for root in dict.fromkeys(roots):
            try:
                self._scan_root(root, result, seen, live)
            except OSError:
                continue
            if result.files > MAX_ARTIFACT_FILES:
                break
        for stale in set(self._cache) - live:
            del self._cache[stale]
        result.records.sort(key=lambda r: (r.created, r.path))
        for record in result.records:
            event = record_to_event(record)
            if event is None:
                result.issues.append(ArtifactIssue(record.path, "artifact.event_invalid"))
            else:
                result.events.append(event)
        return result

    # ------------------------------------------------------------------ internals

    def _scan_root(
        self, root: str, result: ArtifactScan, seen: set[tuple[str, str]], live: set[str]
    ) -> None:
        base = os.path.join(root, *self._work_rel.split("/"))
        if not os.path.isdir(base) or os.path.islink(base):
            return
        for rel, full in self._candidates(base, result):
            if result.files >= MAX_ARTIFACT_FILES:
                result.issues.append(ArtifactIssue(rel, "artifact.too_many"))
                result.files += 1  # sentinel: stop the outer loop
                return
            result.files += 1
            live.add(full)
            outcome = self._load(full, rel)
            if isinstance(outcome, list):
                result.issues.extend(ArtifactIssue(rel, code) for code in outcome)
            elif (outcome.path, outcome.fingerprint) not in seen:
                seen.add((outcome.path, outcome.fingerprint))
                result.records.append(outcome)

    def _candidates(self, base: str, result: ArtifactScan) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for entry in sorted(_scandir(base), key=lambda e: e.name):
            if entry.is_symlink():
                result.issues.append(ArtifactIssue(entry.name, "artifact.symlink"))
                continue
            if entry.is_file(follow_symlinks=False):
                if entry.name.endswith(".md") and entry.name != "AGENTS.md":
                    found.append((entry.name, entry.path))  # not under a task directory
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
            for inner in sorted(_scandir(entry.path), key=lambda e: e.name):
                rel = str(PurePosixPath(entry.name, inner.name))
                if not inner.name.endswith(".md") or inner.name == "AGENTS.md":
                    continue
                if inner.is_symlink():
                    result.issues.append(ArtifactIssue(rel, "artifact.symlink"))
                elif inner.is_file(follow_symlinks=False):
                    found.append((rel, inner.path))
        return found

    def _load(self, full: str, rel: str) -> ArtifactRecord | list[str]:
        try:
            st = os.stat(full, follow_symlinks=False)
        except OSError:
            return ["artifact.unreadable"]
        cached = self._cache.get(full)
        if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
            return cached[2]
        outcome = self._read(full, rel, st.st_size)
        self._cache[full] = (st.st_mtime_ns, st.st_size, outcome)
        return outcome

    @staticmethod
    def _read(full: str, rel: str, size: int) -> ArtifactRecord | list[str]:
        if size > MAX_ARTIFACT_BYTES:
            return ["artifact.too_large"]
        # O_NOFOLLOW: a file swapped for a symlink after the scan's lstat is refused (ELOOP).
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        try:
            fd = os.open(full, flags)
            with os.fdopen(fd, "rb") as handle:
                raw = handle.read(MAX_ARTIFACT_BYTES + 1)
        except OSError:
            return ["artifact.unreadable"]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return ["artifact.encoding"]
        return _record_from_text(text, rel)


def _scandir(path: str) -> list[os.DirEntry[str]]:
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        return []


__all__ = [
    "DEFAULT_WORK_DIR",
    "MAX_ARTIFACT_FILES",
    "PROBLEM_TEXT",
    "SESSION_PREFIX",
    "ArtifactIssue",
    "ArtifactRecord",
    "ArtifactScan",
    "ArtifactScanner",
    "record_to_event",
]
