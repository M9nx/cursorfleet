from __future__ import annotations

import pytest

from cursorfleet.workflow.artifacts import ARTIFACT_SCHEMA, validate_artifact_text
from cursorfleet.workflow.frontmatter import FrontmatterError, parse_frontmatter, yaml_string

GOOD = f"""---
schema: {ARTIFACT_SCHEMA}
kind: handoff.created
task: add-login
author_role: implementer-alpha
created: 2026-10-04T12:00:00Z
to_role: reviewer
issue_ref: "#123"
context_refs:
  - src/app/login.py
  - tests/test_login.py
---
Body text is free-form and never parsed.
"""


def test_parse_scalars_lists_and_body() -> None:
    doc = parse_frontmatter(GOOD)
    assert doc.meta["kind"] == "handoff.created"
    assert doc.meta["issue_ref"] == "#123"
    assert doc.meta["context_refs"] == ["src/app/login.py", "tests/test_login.py"]
    assert doc.body.startswith("Body text")


def test_parse_types_and_inline_list() -> None:
    doc = parse_frontmatter('---\nalwaysApply: true\nn: 3\nglobs: [a, "b,c"]\nempty: []\n---\n')
    assert doc.meta == {"alwaysApply": True, "n": 3, "globs": ["a", "b,c"], "empty": []}


def test_crlf_and_bom_tolerated() -> None:
    doc = parse_frontmatter("\ufeff---\r\nname: x\r\n---\r\nbody")
    assert doc.meta == {"name": "x"}


@pytest.mark.parametrize(
    "text",
    [
        "no fence",
        "---\nname: x\n",  # unclosed
        "---\na: 1\na: 2\n---\n",  # duplicate key
        "---\nouter:\n  inner: 1\n---\n",  # nesting
        "---\nk: &anchor v\n---\n",  # anchor
        "---\nk: |\n---\n",  # block scalar
        "---\nk: !!python/object x\n---\n",  # tag
        "---\nk: v # comment\n---\n",  # inline comment
        "---\n- item\n---\n",  # list without key
        "---\nk: a: b\n---\n",  # ambiguous plain scalar
        "---\nbad key: v\n---\n",
        '---\nk: "unterminated\n---\n',
    ],
)
def test_rejects_unsupported_constructs(text: str) -> None:
    with pytest.raises(FrontmatterError):
        parse_frontmatter(text)


def test_yaml_string_round_trips() -> None:
    tricky = 'He said "hi": ok # not a comment\\'
    assert parse_frontmatter(f"---\nk: {yaml_string(tricky)}\n---\n").meta["k"] == tricky


def test_artifact_good() -> None:
    assert validate_artifact_text(GOOD, "add-login/02-handoff-implementer-alpha.md") == []


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda t: t.replace("kind: handoff.created", "kind: thought.created"), "artifact.kind"),
        (lambda t: t.replace("schema: " + ARTIFACT_SCHEMA, "schema: other/1"), "artifact.schema"),
        (lambda t: t.replace("task: add-login", "task: other-task"), "artifact.task"),
        (
            lambda t: t.replace("created: 2026-10-04T12:00:00Z", "created: yesterday"),
            "artifact.created",
        ),
        (lambda t: t.replace("---\nBody", "extra: 1\n---\nBody"), "artifact.unknown_key"),
        (lambda t: t.replace("task: add-login\n", ""), "artifact.missing_key"),
        (lambda t: t.replace("src/app/login.py", "/etc/passwd"), "artifact.context_refs"),
        (lambda t: t.replace("src/app/login.py", "../x"), "artifact.context_refs"),
        (lambda t: t.replace("src/app/login.py", "C:\\x"), "artifact.context_refs"),
        (lambda t: t.replace('"#123"', '"https://u:p@h/x"'), "artifact.issue_ref"),
        (lambda t: t.replace("to_role: reviewer", "to_role: bad role!"), "artifact.to_role"),
    ],
)
def test_artifact_problems(mutation, code: str) -> None:  # type: ignore[no-untyped-def]
    problems = validate_artifact_text(mutation(GOOD), "add-login/x.md")
    assert code in {p.code for p in problems}


def test_artifact_must_live_in_task_dir_and_be_small() -> None:
    assert "artifact.location" in {p.code for p in validate_artifact_text(GOOD, "x.md")}
    huge = GOOD + "x" * 70_000
    assert [p.code for p in validate_artifact_text(huge, "add-login/x.md")] == [
        "artifact.too_large"
    ]
