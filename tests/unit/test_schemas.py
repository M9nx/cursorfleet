from __future__ import annotations

import json
from pathlib import Path

import pytest

from cursorfleet.schema_gen import generate_schemas, main

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
NAMES = ["config.schema.json", "roster.schema.json", "event.schema.json", "policy.schema.json"]


def test_all_expected_schemas_generated() -> None:
    assert sorted(generate_schemas()) == sorted(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_checked_in_schema_matches_models(name: str) -> None:
    on_disk = json.loads((SCHEMAS_DIR / name).read_text("utf-8"))
    assert on_disk == generate_schemas()[name], (
        f"{name} drifted from the Pydantic models; run `uv run python scripts/gen_schemas.py`"
    )


def test_check_mode_detects_drift(tmp_path: Path) -> None:
    assert main(tmp_path, check=True) == 1
    assert main(tmp_path, check=False) == 0
    assert main(tmp_path, check=True) == 0
    (tmp_path / "event.schema.json").write_text("{}", encoding="utf-8")
    assert main(tmp_path, check=True) == 1


def test_policy_schema_is_marked_reserved() -> None:
    policy = generate_schemas()["policy.schema.json"]
    assert policy["x-cursorfleet-status"] == "reserved-for-v0.2"
    assert policy["additionalProperties"] is False
    assert policy["properties"] == {}


def test_event_schema_forbids_extras_everywhere() -> None:
    schema = generate_schemas()["event.schema.json"]
    assert schema["additionalProperties"] is False
    for name, definition in schema["$defs"].items():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False, name
