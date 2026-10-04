from __future__ import annotations

import os
import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cursorfleet.events.ids import fs_name_for, safe_id, worktree_id_for

PORTABLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
WINDOWS_BAD = set('<>:"/\\|?*') | {chr(i) for i in range(32)}


@pytest.mark.parametrize("name", ["abc", "doc-example-conversation", "a.b_c-1", "x" * 100])
def test_portable_ids_are_kept(name: str) -> None:
    assert fs_name_for(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "../x", "a/b", "a\\b", "C:", "x:y", "CON", "con", "nul.txt", "COM1", "LPT9.log",
        "trailing.", "h-collision", "MixedCase", "", " ", "a b", "é", "x" * 400, "\x00", "..", ".",
    ],
)  # fmt: skip
def test_unsafe_ids_become_hashes(name: str) -> None:
    out = fs_name_for(name)
    assert out.startswith("h-") and len(out) == 26
    assert fs_name_for(name) == out  # stable


@given(st.text(max_size=300))
def test_fs_names_are_always_safe_everywhere(identifier: str) -> None:
    out = fs_name_for(identifier)
    assert PORTABLE.match(out) or out.startswith("h-")
    assert out == out.lower()  # no case-only collisions on case-insensitive filesystems
    assert not (set(out) & WINDOWS_BAD)
    assert not out.endswith(".") and out not in {".", ".."}
    assert os.sep not in out and "/" not in out


@given(st.text(max_size=60), st.text(max_size=60))
def test_distinct_ids_rarely_collide(a: str, b: str) -> None:
    if a != b:
        assert fs_name_for(a) != fs_name_for(b)


def test_safe_id_validates_or_hashes() -> None:
    assert safe_id("ok-id_1") == "ok-id_1"
    hashed = safe_id("has space")
    assert hashed is not None and hashed.startswith("h-")
    assert safe_id(None) is None and safe_id(5) is None and safe_id("") is None


def test_worktree_id_is_stable_and_safe() -> None:
    a = worktree_id_for("/srv/some/repo")
    assert a == worktree_id_for("/srv/some/repo") and re.fullmatch(r"wt-[0-9a-f]{12}", a)
    assert a != worktree_id_for("/srv/some/other")
