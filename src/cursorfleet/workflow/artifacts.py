"""Validation of agent-declared Markdown artifacts under ``.cursorfleet/work/`` (ADR 0006).

Artifacts are self-reported and untrusted: this module only checks *shape*. The
body is never parsed or copied anywhere. PROVISIONAL (ADR 0006): the ``schema``
value and field set may change once agents have been observed using them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

from cursorfleet.events.ids import SAFE_ID_PATTERN
from cursorfleet.events.pathcheck import check_relative_posix
from cursorfleet.workflow.frontmatter import Document, FrontmatterError, parse_frontmatter

ARTIFACT_SCHEMA_LEGACY = "cursorfleet.artifact/1"
ARTIFACT_SCHEMA = "cursorfleet.artifact/0.1"
ARTIFACT_SCHEMAS: frozenset[str] = frozenset({ARTIFACT_SCHEMA, ARTIFACT_SCHEMA_LEGACY})
ARTIFACT_KINDS: frozenset[str] = frozenset(
    {"plan.created", "handoff.created", "blocker.raised", "context.loaded"}
)
REQUIRED_KEYS_LEGACY: frozenset[str] = frozenset(
    {"schema", "kind", "task", "author_role", "created"}
)
REQUIRED_KEYS: frozenset[str] = frozenset(
    {"schema", "kind", "task", "artifact_id", "revision", "author_role", "created"}
)
OPTIONAL_KEYS: frozenset[str] = frozenset({"to_role", "issue_ref", "context_refs", "digest"})
MAX_ARTIFACT_BYTES = 64 * 1024
MAX_CONTEXT_REFS = 50
MAX_ISSUE_REF_CHARS = 128

TASK_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SAFE_ID = re.compile(SAFE_ID_PATTERN)
_URL_USERINFO = re.compile(r"://[^/\s]*@")


@dataclass(frozen=True)
class ArtifactProblem:
    code: str
    message: str


def _check_created(value: object) -> str | None:
    if not isinstance(value, str):
        return "must be a string"
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return "must be an ISO 8601 date or timestamp"
    return None


def validate_artifact_text(text: str, rel_path: str) -> list[ArtifactProblem]:  # noqa: PLR0912, PLR0915
    """Validate one artifact. ``rel_path`` is relative to the work dir (``<task>/<file>.md``)."""
    problems: list[ArtifactProblem] = []
    if len(text.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        problems.append(ArtifactProblem("artifact.too_large", f"larger than {MAX_ARTIFACT_BYTES}"))
        return problems
    try:
        doc: Document = parse_frontmatter(text)
    except FrontmatterError as exc:
        return [ArtifactProblem("artifact.frontmatter", str(exc))]
    meta = doc.meta
    schema = meta.get("schema") if isinstance(meta.get("schema"), str) else None
    required = REQUIRED_KEYS if schema == ARTIFACT_SCHEMA else REQUIRED_KEYS_LEGACY
    allowed_keys = required | OPTIONAL_KEYS

    missing = sorted(required - meta.keys())
    if missing:
        problems.append(ArtifactProblem("artifact.missing_key", f"missing: {', '.join(missing)}"))
    unknown = sorted(meta.keys() - allowed_keys)
    if unknown:
        problems.append(ArtifactProblem("artifact.unknown_key", f"unknown: {', '.join(unknown)}"))

    if schema is not None and schema not in ARTIFACT_SCHEMAS:
        problems.append(
            ArtifactProblem("artifact.schema", f"schema must be one of {sorted(ARTIFACT_SCHEMAS)}")
        )
    if "kind" in meta and meta["kind"] not in ARTIFACT_KINDS:
        allowed = ", ".join(sorted(ARTIFACT_KINDS))
        problems.append(ArtifactProblem("artifact.kind", f"kind must be one of: {allowed}"))

    parts = PurePosixPath(rel_path).parts
    dir_task = parts[0] if len(parts) >= 2 else None
    if dir_task is None:
        problems.append(
            ArtifactProblem("artifact.location", "must live in <work>/<task>/<file>.md")
        )
    task = meta.get("task")
    if "task" in meta:
        if not isinstance(task, str) or not TASK_SLUG.match(task):
            problems.append(ArtifactProblem("artifact.task", "task must be a lowercase slug"))
        elif dir_task is not None and task != dir_task:
            problems.append(ArtifactProblem("artifact.task", "task must equal the directory name"))

    for key in ("author_role", "to_role"):
        if key in meta:
            value = meta[key]
            if not isinstance(value, str) or not _SAFE_ID.match(value):
                problems.append(ArtifactProblem(f"artifact.{key}", f"{key} must be a safe id"))

    if "created" in meta:
        err = _check_created(meta["created"])
        if err:
            problems.append(ArtifactProblem("artifact.created", f"created {err}"))

    if "issue_ref" in meta:
        ref = meta["issue_ref"]
        if (
            not isinstance(ref, str)
            or not ref
            or len(ref) > MAX_ISSUE_REF_CHARS
            or not ref.isprintable()
            or _URL_USERINFO.search(ref)
        ):
            problems.append(
                ArtifactProblem(
                    "artifact.issue_ref",
                    "issue_ref must be short printable text without URL credentials",
                )
            )

    if "context_refs" in meta:
        refs = meta["context_refs"]
        if not isinstance(refs, list) or len(refs) > MAX_CONTEXT_REFS:
            problems.append(
                ArtifactProblem(
                    "artifact.context_refs",
                    f"context_refs must be a list of at most {MAX_CONTEXT_REFS} paths",
                )
            )
        else:
            for ref_item in refs:
                try:
                    if not isinstance(ref_item, str):
                        msg = "not a string"
                        raise ValueError(msg)
                    check_relative_posix(ref_item)
                except ValueError as exc:
                    problems.append(
                        ArtifactProblem("artifact.context_refs", f"bad context_ref: {exc}")
                    )
                    break
    return problems
