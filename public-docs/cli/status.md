# `cursorfleet status`

```bash
cursorfleet status [--json] [--repo DIR] [--stale-after-minutes N] [--no-git]
```

Read-mostly snapshot of sessions, agents, lanes, and worktrees. Use this in
scripts; the TUI needs an interactive terminal.

| Option | Default | Meaning |
| --- | --- | --- |
| `--json` | off | Stable machine-readable document. |
| `--repo DIR` | cwd | A directory inside the Git repo. |
| `--stale-after-minutes N` | 15 | Silence after which an agent becomes `stale_offline`. |
| `--no-git` | off | Skip the Git collector. Worktrees are then empty. |

Outside a Git repository the command exits 1. With `--json` it still prints a
document whose `error.code` is `not_a_git_repo`.

`status` may update the SQLite projection under
`<git-common-dir>/cursorfleet/`. It never touches the working tree or the
network. Git commands are local and read-only; it never runs `git fetch`.

## `status --json`

`schema` is `"cursorfleet.status/1"`. Check it before reading anything else.

**Unknown fields.** Additive keys and new `lane` / `stale_reasons` values keep
`/1`. Consumers **must ignore unknown keys** and treat unknown enum values as
`unknown`. Removed or retyped keys will bump the schema to `/2`.

Key order is fixed. Timestamps are UTC ISO-8601 with a trailing `Z`.

## No token budget

Cursor hooks expose no token or cost data (only `preCompact` reports context
usage). `limits.token_budget` and per-session `token_budget` are always
`"unknown"`. Progress is `elapsed_s`, `tool_call_count`, and `compactions`
only.

Other honesty rules in the document:

- There is no `idle` lane. Silence becomes `stale_offline` after
  `telemetry.stale_after_s` (default 900 s). A worktree with no hook
  telemetry has `telemetry: "none"` and `lane: "unknown"`.
- Cloud agents are `limits.cloud_agents: "not_visible"`.
- v0.1 never enforces: `limits.enforcement: "none"`.
- `last_test` and `gates[]` are heuristic and non-authoritative.
- Telemetry is best-effort: any field can be missing or stale.

`attribution` on each agent is `exact`, `inferred`, or `unknown`. See
[agents and events](../concepts/agents-and-events.md).

Before pasting `--json` into an issue, check branch names, paths, and
`issue_ref` values. Those can be sensitive even though content is not stored.
