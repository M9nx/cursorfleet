---
name: cursorfleet-artifacts
description: Write CursorFleet plan, handoff, blocker and context-manifest artifacts under the work directory in the strict frontmatter format. Use when handing work between agents, raising a blocker, or recording which context was loaded.
---

# CursorFleet artifacts

Artifacts are Markdown files with a small frontmatter block. CursorFleet reads them to show plans, handoffs and blockers. They are **self-reported**: anything you write is a claim, not evidence, and a forged one looks the same as an honest one.

## Where

`{{work_dir}}/<task>/<NN>-<kind>-<author_role>.md`, for example `{{work_dir}}/add-login-form/02-handoff-implementer-alpha.md`.
`<task>` is a slug (`a-z`, `0-9`, `-`, `.`, `_`; starts with a letter or digit) and must equal the `task` field.

## Format

The frontmatter is a strict YAML subset: one `key: value` per line, plain or double-quoted scalars, and lists as `- item` lines. No nesting, no anchors, no multi-line values. Unknown keys are rejected.

```
---
schema: cursorfleet.artifact/1
kind: handoff.created
task: add-login-form
author_role: implementer-alpha
created: 2026-10-04T12:00:00Z
to_role: reviewer
issue_ref: "#123"
context_refs:
  - src/app/login.py
  - tests/test_login.py
---
Free-form Markdown body.
```

| Field | Required | Value |
| --- | --- | --- |
| `schema` | yes | `cursorfleet.artifact/1` |
| `kind` | yes | `plan.created`, `handoff.created`, `blocker.raised` or `context.loaded` |
| `task` | yes | the task slug, equal to the directory name |
| `author_role` | yes | the roster id or role of the author, e.g. `reviewer` |
| `created` | yes | ISO 8601 timestamp, UTC preferred |
| `to_role` | no | who should act next |
| `issue_ref` | no | short reference such as `#123`; no URLs with credentials |
| `context_refs` | no | workspace-relative `/` paths, at most 50 |

## Body conventions

- **plan.created**: goal, non-goals, files, steps, risks, test strategy.
- **handoff.created**: what changed (paths), checks run with exit codes, what is not done, what the receiver should do first.
- **blocker.raised**: what is blocked, why, what you tried, what decision or input is needed.
- **context.loaded**: the rules, skills and AGENTS.md files you relied on (as `context_refs`). Self-reported; never claim a file you did not load.

## Never write

Prompts, your reasoning, file contents, command output, environment variables, emails, transcript paths, or secrets. Summaries and paths only.

Read-only agents cannot write files: they return the complete artifact text in their final message and the coordinator saves it.
