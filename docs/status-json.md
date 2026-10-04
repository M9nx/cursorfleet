# `cursorfleet status --json`

Stable, versioned output of `cursorfleet status --json`. The document is pinned by a
golden snapshot test (`tests/integration/test_cli_state.py`,
`tests/fixtures/status/status.v1.golden.json`). Regenerate the snapshot deliberately with
`UPDATE_GOLDEN=1 uv run pytest tests/integration/test_cli_state.py`.

## Versioning

- `schema` is `"cursorfleet.status/1"`. Consumers should check it before reading anything else.
- **Additive changes** (new optional keys, new `lane`/`stale_reasons` values) keep `/1`;
  consumers must ignore unknown keys and treat unknown enum values as `unknown`.
- **Breaking changes** (removed or retyped keys, changed meaning) bump to `/2`.
- Key order is fixed; timestamps are UTC ISO-8601 with a trailing `Z`.

## Pending changes (decided, not implemented)

Status: implemented, provisional, unvalidated against live Cursor. These ADR decisions
change this document after the live spike ([follow-ups](follow-ups.md)); until then the
text below describes the current code.

- **Schema ids move to `0.1`** until the first public release
  ([ADR 0003](adr/0003-event-model-and-sanitization.md)): `cursorfleet.status/0.1`, with
  `/1` reserved for the first stable contract. Consumers should expect the golden snapshot
  to change once.
- **Attribution values** become `exact`, `inferred_temporal` and `unknown` (currently
  `inferred`), and an aggregate shows its weakest member.
- **`last_test` and `gates[]`** are heuristic and non-authoritative. They will be replaced by
  `verification.observed` observations carrying a method and confidence; no heuristic value
  will count as a gate ([ADR 0011](adr/0011-evidence-trust-model.md)).
- **`reviewed`** is a heuristic flag today ([ADR 0010](adr/0010-reducer-state-semantics.md)).
- Telemetry is best-effort, so any field can be missing or stale.

## Honesty rules

- `unknown` is a value, not a gap. A worktree with no hook telemetry has
  `telemetry: "none"` and `lane: "unknown"`; it is never reported as idle.
- Silence is **not** idleness. An agent that stops emitting observed events becomes
  `stale_offline` after `telemetry.stale_after_s` (default 900 s) and keeps its previous
  lane in `last_lane`. There is no `idle` lane.
- Cursor hooks expose no token or cost data, so `token_budget` is always `"unknown"`.
  Progress is reported as `elapsed_s`, `tool_call_count` and `compactions` only.
- Cloud agents are not visible (`limits.cloud_agents: "not_visible"`) and v0.1 never
  enforces anything (`limits.enforcement: "none"`).
- `lane_basis` says how the lane is known: `observed_activity` (hook events),
  `lifecycle_only` (a running subagent with no attributed events; PROVISIONAL, ADR 0001
  Q1), `self_reported`, `derived`, or `none`.

## Top level

| key | type | meaning |
| --- | --- | --- |
| `schema` | string | `cursorfleet.status/1` |
| `generated_at` | timestamp | The clock used for staleness (`now`) |
| `repo` | object | `common_dir`, `runtime_dir` (absolute paths) |
| `telemetry` | object | See below |
| `limits` | object | `token_budget`, `cloud_agents`, `enforcement` (constants) |
| `git` | object | `available` (bool), `error` (string or null) |
| `sessions` | array | One entry per Cursor conversation seen in the spool |
| `tasks` | array | Sessions grouped by `issue_ref` (empty until work artifacts exist) |
| `worktrees` | array | One entry per git worktree, main first |

### `telemetry`

`state` (`hooks` or `none`), `sessions`, `events`, `spool_files`, `stale_after_s`,
`source` (`projection`, `replay` or `none`), `corruption` (counters for skipped spool
lines: `bad_format`, `bad_crc`, `bad_json`, `invalid_event`, `unknown_version`,
`oversize`, `misplaced`, `torn_tail`, `resynced`, `total`) and `notes` (human strings,
for example "no hook telemetry indexed").

### `sessions[]`

`session_id`, `lane`, `ended`, `end_outcome`, `first_ts`, `last_ts`, `started_ts`,
`ended_ts`, `elapsed_s`, `tool_call_count`, `compactions`, `event_count`, `by_source`
(`observed`/`derived`/`self_reported` counts), `cursor_version`, `branch`, `commit`,
`worktree_ids`, `unpaired_stops` (PROVISIONAL subagent-stop pairing misses),
`token_budget`, `agents[]`, `gates[]`.

### `sessions[].agents[]`

`key` (`main` or `role#instance`), `role`, `instance_id`, `attribution`
(`exact`/`inferred`/`unknown`), `lane`, `lane_source`, `lane_basis`, `stale`,
`last_lane`, `lifecycle` (`none`/`running`/`stopped`), `lifecycle_only`, `first_ts`,
`last_ts`, `elapsed_s`, `tool_call_count`, `tool_failures`, `compactions`,
`last_context_usage_percent`, `files_changed`, `reviewed`, `last_test`
(`outcome`, `ts`), `stop_report` (`outcome`, `duration_ms`, `tool_call_count`,
`message_count`), `issue_refs`, `worktree_id`, `branch`, `token_budget`.

Lanes: `queued`, `loading_context`, `planning`, `working`, `verifying`,
`awaiting_review`, `patching`, `blocked`, `done`, `stale_offline`, `unknown`. Lane rules
are heuristics over observed events, documented in `cursorfleet.state.reducer`.

### `worktrees[]`

`path`, `worktree_id`, `is_main`, `exists`, `branch`, `head`, `detached`, `bare`,
`locked`, `prunable`, `dirty_count`, `upstream`, `ahead`, `behind`, `last_commit_ts`,
`last_event_ts`, `stale`, `stale_reasons` (`missing_path`, `prunable`, `inactive`),
`telemetry`, `lane`, `owners[]` (`session_id`, `agent_key`, `role`, `lane`,
`attribution`), `tasks`, `error`.

- `ahead`/`behind` compare `HEAD` with the **existing** upstream ref. CursorFleet never
  runs `git fetch`, so the numbers can lag the remote. `null` means no upstream, a
  detached HEAD, or an unreadable ref.
- `dirty_count` counts `git status --porcelain` entries (untracked directories count once).
- `inactive` means neither hooks nor commits touched the worktree for 72 hours.

## Related commands

- `cursorfleet replay <session-id> [--json]` rebuilds one session from the spool twice and
  reports `deterministic` plus a SHA-256 `digest` of the resulting state (`cursorfleet.replay/1`).
- `cursorfleet index [--rebuild]` syncs or rebuilds the SQLite projection.
- `cursorfleet events export --sanitized` and `cursorfleet events purge` are described in
  [privacy](privacy.md).

`status` reads the spool, may update the projection under `<git-common-dir>/cursorfleet/`,
and runs read-only git commands; it never touches the working tree or the network.
