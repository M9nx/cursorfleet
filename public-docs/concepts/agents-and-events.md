# Agents and events

CursorFleet shows a roster of local agents and a stream of sanitized events.
v0.1 is observe-only: it never allows, denies, or asks, and it never blocks
an agent.

## Roster and the coordinator

The roster is `.cursorfleet/roster.toml` (a default roster is used if the file
is absent). Each enabled roster agent becomes a Cursor subagent file, except
the **coordinator**.

The coordinator is the **main agent**, delivered as a skill (and optionally a
rule). It is never written as a subagent file. That is a CursorFleet design
choice, not a Cursor platform limit: Cursor can nest subagents one level
deep, but CursorFleet keeps the coordinator as the main agent so workers stay
within that depth and so identity inside subagent hooks is not required for
the coordinator itself.

Roster capability notes are documentation only. Cursor subagent frontmatter
has no per-agent tool allowlist, path scope, network, or Git permission.

## Observed, derived, and self-reported

Every event carries a `source`:

| Source | Meaning |
| --- | --- |
| `observed` | Came from a Cursor hook payload, after the allowlist parser. |
| `derived` | Computed by CursorFleet (for example a command that looked like a test run). |
| `self_reported` | Declared by an agent in a work artifact under `.cursorfleet/work/`. |

Self-reported and derived items are labelled and never count as gate evidence.
`observed` means "came from a hook payload", not "tamper-proof": a same-user
agent can forge or delete the spool.

There are **no thought, prompt, or response events**. CursorFleet does not
register the hooks that would receive user prompts, model thinking, or
assistant text. File contents and command output are not stored either.

## Attribution

`attribution` is exactly one of `exact`, `inferred`, or `unknown`. It says how
firmly an event is tied to an agent, not whether the work succeeded.

| Value | Meaning |
| --- | --- |
| `exact` | A unique current agent instance is identified by the payload, or is linked to it by an id relationship that has been verified. |
| `inferred` | A weaker guess: role only, timing, worktree, branch, ordering, or self-report. A role-only identity is never `exact`. |
| `unknown` | Parent-only identity, or no defensible link to a child agent. This is the default. |

A parent conversation id never confirms a child agent. Two concurrent
subagents of the same type are indistinguishable by role.

## Q1 is OPEN

Whether tool hooks fired **inside** a subagent identify the current subagent
instance (ADR 0001 Q1) is **OPEN**. Until that is classified, per-agent tool
timelines and tool counts can be incomplete or mis-attributed, especially
with parallel subagents sharing a checkout.

Custom subagent naming (Q2: whether `subagent_type` shows the custom name) is
also OPEN. See [known limitations](../known-limitations.md).

## What you see

The TUI and `status --json` group work into lanes (working, blocked, stale,
and so on). Lane assignment is a heuristic. Silence is not idle: see
[current TUI status](../tui/current-status.md).
