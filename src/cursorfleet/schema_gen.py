"""Generate the checked-in JSON Schemas from the Pydantic models.

Usage: ``uv run python scripts/gen_schemas.py [--check]``. ``--check`` exits 1 if
the files under ``schemas/`` differ from the models (also enforced by a test).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from cursorfleet.config.models import FleetConfig
from cursorfleet.config.roster import Roster
from cursorfleet.events.models import Event

DIALECT = "https://json-schema.org/draft/2020-12/schema"
ID_BASE = "https://raw.githubusercontent.com/M9nx/cursorfleet/main/schemas/"  # identifier only


def _from_model(model: type[BaseModel], filename: str, title: str) -> dict[str, Any]:
    schema = model.model_json_schema(mode="validation")
    schema["title"] = title
    return {"$schema": DIALECT, "$id": ID_BASE + filename, **schema}


def _policy_placeholder() -> dict[str, Any]:
    return {
        "$schema": DIALECT,
        "$id": ID_BASE + "policy.schema.json",
        "title": "CursorFleet policy (reserved for v0.2)",
        "description": (
            "Placeholder. The policy engine (v0.2 Guard) does not exist in v0.1, so no policy "
            "file is valid yet: this schema accepts only an empty object. Do not rely on its shape."
        ),
        "x-cursorfleet-status": "reserved-for-v0.2",
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    }


def generate_schemas() -> dict[str, dict[str, Any]]:
    """Return ``{filename: schema}`` for every schema we ship."""
    return {
        "config.schema.json": _from_model(FleetConfig, "config.schema.json", "CursorFleet config"),
        "roster.schema.json": _from_model(Roster, "roster.schema.json", "CursorFleet roster"),
        "event.schema.json": _from_model(Event, "event.schema.json", "CursorFleet event"),
        "policy.schema.json": _policy_placeholder(),
    }


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main(schemas_dir: Path, *, check: bool) -> int:
    drifted: list[str] = []
    for name, schema in generate_schemas().items():
        target = schemas_dir / name
        text = render(schema)
        if check:
            if not target.is_file() or json.loads(target.read_text("utf-8")) != schema:
                drifted.append(name)
        else:
            target.write_text(text, encoding="utf-8")
    if drifted:
        sys.stderr.write(f"schema drift: {', '.join(drifted)} (run scripts/gen_schemas.py)\n")
        return 1
    return 0
