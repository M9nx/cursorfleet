"""Run metadata under ``<git-common-dir>/cursorfleet/runs/`` (B2)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUNS_SCHEMA = "cursorfleet.run/0.1"


@dataclass
class RunRecord:
    run_id: str
    task_slug: str
    created_at: str
    archived: bool = False
    session_ids: list[str] = field(default_factory=list)
    schema: str = RUNS_SCHEMA

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema"] = RUNS_SCHEMA
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RunRecord:
        return cls(
            run_id=str(data["run_id"]),
            task_slug=str(data["task_slug"]),
            created_at=str(data.get("created_at", datetime.now(tz=UTC).isoformat())),
            archived=bool(data.get("archived", False)),
            session_ids=[str(s) for s in data.get("session_ids", [])],
        )


def runs_dir(runtime_root: str) -> Path:
    return Path(runtime_root) / "runs"


def _run_path(root: str, run_id: str) -> Path:
    safe = run_id.replace("/", "_").replace("\\", "_")
    return runs_dir(root) / f"{safe}.json"


def list_runs(runtime_root: str) -> list[RunRecord]:
    directory = runs_dir(runtime_root)
    if not directory.is_dir():
        return []
    out: list[RunRecord] = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out.append(RunRecord.from_json(data))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
    return out


def load_run(runtime_root: str, run_id: str) -> RunRecord | None:
    path = _run_path(runtime_root, run_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return RunRecord.from_json(data)


def save_run(runtime_root: str, record: RunRecord) -> None:
    directory = runs_dir(runtime_root)
    directory.mkdir(parents=True, exist_ok=True)
    path = _run_path(runtime_root, record.run_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def attach_session(runtime_root: str, run_id: str, session_id: str) -> bool:
    record = load_run(runtime_root, run_id)
    if record is None or record.archived:
        return False
    if session_id not in record.session_ids:
        record.session_ids.append(session_id)
        save_run(runtime_root, record)
    return True
