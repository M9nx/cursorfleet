# Sessions, generations, and conversations

CursorFleet watches **local Cursor IDE sessions** in one Git repository. It does
not start, schedule, or steer agents. Cloud agents and cloud subagents are
never visible: their hooks run in a remote environment and never reach the
local record.

## Conversation

A **conversation** is a Cursor chat. Cursor documents `conversation_id` as
stable across turns of that chat. CursorFleet maps it to `session_id`.

## Session

A **session** is CursorFleet's name for one Cursor conversation it has seen.
`cursorfleet status --json` lists one entry per conversation in the local
spool. Session start and end come from Cursor's session hooks when those fire.

Cursor documents `session_id` on session start as the same value as
`conversation_id`. That equality is not yet verified against a live Cursor
capture.

## Generation

A **generation** is Cursor's `generation_id`. Cursor documents it as changing
with every user message, while the conversation stays the same. CursorFleet
keeps the value as a correlation hint only. It is never a session key, an
agent id, or a join key between stores. Consumers must keep working if it is
absent or wrong.

Whether `generation_id` is actually stable within a turn and unique across
conversations is not yet verified.

## Local only

- Runtime data lives under the repository's Git common directory
  (`<git-common-dir>/cursorfleet/`), outside the working tree, shared by every
  linked worktree of that repo.
- There are no network calls, no telemetry, and no accounts.
- Events can be dropped. Absence of a session or event is not proof that
  nothing happened.

See [agents and events](agents-and-events.md), [worktrees](worktrees.md), and
[known limitations](../known-limitations.md).
