from __future__ import annotations

import re

import pytest

from cursorfleet.events.ids import ULID_PATTERN, derive_agent_id, new_event_id


def test_new_event_id_shape() -> None:
    assert re.fullmatch(ULID_PATTERN, new_event_id())


def test_new_event_id_is_deterministic_with_inputs() -> None:
    a = new_event_id(now_ms=1_700_000_000_000, entropy=b"\x00" * 10)
    assert a == new_event_id(now_ms=1_700_000_000_000, entropy=b"\x00" * 10)
    assert a.endswith("0" * 16)


def test_event_ids_sort_by_time() -> None:
    early = new_event_id(now_ms=1_000, entropy=b"\xff" * 10)
    late = new_event_id(now_ms=2_000, entropy=b"\x00" * 10)
    assert early < late


def test_new_event_id_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError, match="48-bit"):
        new_event_id(now_ms=1 << 48)
    with pytest.raises(ValueError, match="10 bytes"):
        new_event_id(entropy=b"short")


@pytest.mark.parametrize(
    ("role", "instance", "expected"),
    [
        (None, None, None),
        ("reviewer", None, "reviewer"),
        ("reviewer", "abc", "reviewer#abc"),
        (None, "abc", "unknown#abc"),
    ],
)
def test_derive_agent_id(role: str | None, instance: str | None, expected: str | None) -> None:
    assert derive_agent_id(role, instance) == expected
