# Terminal UI (`cursorfleet tui`)

An observe-only Textual dashboard for the agents running in one repository. It reads the
SQLite projection (built from the hook spool) and the read-only git collector. It never
enforces, approves or blocks anything, never fetches, never touches the network, and never
holds or shows prompts, thinking text, responses, file contents or command output (see
[privacy](privacy.md)).

> **Status: implemented, provisional, unvalidated against live Cursor.** New TUI work is
> frozen until the live spike runs ([status](status.md)). Where this page and the code
> differ from an accepted ADR, the difference is marked **Divergence** and tracked in
> [follow-ups](follow-ups.md). Telemetry is best-effort, so any view can be incomplete.

```bash
cursorfleet tui [--path DIR] [--refresh SECONDS] [--no-git] [--no-watch]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--path` | cwd | Any directory inside the git repo. |
| `--refresh` | `2.0` | Poll interval, 0.25 to 60 seconds. |
| `--no-git` | off | Skip the git collector (worktrees and gates show "unknown"). |
| `--no-watch` | off | Poll only, even if the optional `watchfiles` package is installed. |

The command needs an interactive terminal and exits with status 2 otherwise; in scripts use
`cursorfleet status --json`.

## Screens

| Key | Screen | What it shows |
| --- | --- | --- |
| `o` | Overview (default) | Agents grouped into lanes: QUEUED, LOADING CONTEXT, PLANNING, WORKING, VERIFYING, AWAITING REVIEW, PATCHING, BLOCKED, DONE, STALE / OFFLINE, and UNKNOWN / NO TELEMETRY. Lanes sort by blockers, then recency. Enter opens the agent detail. |
| `l` | Timeline | Events, newest first, with `source/attribution`, agent, summary and risk. Filterable (below). Large histories are paged: 200 rows at first, `m` loads more. |
| `w` | Worktrees | Branch, HEAD, dirty files, ahead/behind, stale or prunable, owning agent, last activity. `r` only re-reads. |
| `g` | Gates | Ten heuristic, non-authoritative signals per worktree (below). |
| `e` | Evidence | Heuristic test/lint/type observations, and, separately, what agents DECLARED in work artifacts. |
| `v` | Violations | Placeholder: "policy engine arrives in v0.2". |
| `?` | Help | Keys, layouts, honesty rules, setup hints. |

**Agent detail** shows role, task, issue refs, context sources, status and the basis for it,
worktree/branch/commit, changed-file count, last tools, last test evidence, gates for that
worktree, elapsed time, tool-call count, compactions, handoff destination and a stop report
if Cursor sent one. Token and cost are always "unknown (not exposed by Cursor hooks)".

### Honesty rules

- **Silence is not idle.** An agent with no recent events is STALE / OFFLINE. An agent or
  worktree with no hook telemetry is in UNKNOWN / NO TELEMETRY with setup guidance.
- **Observed versus self-reported.** Timeline tags: `obs` (from a Cursor hook), `drv`
  (derived by CursorFleet, e.g. a test run), `SELF` (declared by an agent in a work
  artifact). Self-reported and heuristic items are labelled and never count as gate
  evidence ([ADR 0011](adr/0011-evidence-trust-model.md)).
- **Attribution is a label, not a fact.** Per [ADR 0003](adr/0003-event-model-and-sanitization.md)
  it is `exact`, `inferred_temporal` or `unknown`, and an aggregate shows its weakest
  member. **Divergence:** the code still uses the older labels (`exact`, `inferred`,
  `unknown`) and does not yet apply weakest-wins everywhere.
- **Basis tags.** Each card says how its lane was decided: `observed`, `lifecycle-only`,
  `SELF-REPORTED`, `derived` or `no telemetry`.

## Gates

**Heuristic and non-authoritative. Not proof that anything passed.** The gate screen is a
display of guesses; v0.1 does not enforce or certify any gate, and `stop` cannot block
completion ([ADR 0008](adr/0008-enforcement-boundaries.md)). The screen is labelled
"heuristic, non-authoritative".

The ten signals: unit tests, integration tests, type check, lint, security checks,
independent review, re-review, documentation, CI status, merge readiness. Each is its own
signal, never aggregated. Intended states are UNKNOWN, STALE and "observed (heuristic)".
A real PASS or FAIL needs evidence from a deterministic runner bound to a commit SHA, which
arrives in v0.3 ([ADR 0011](adr/0011-evidence-trust-model.md)). Heuristic events never
satisfy a gate (rule R1 in [ADR 0003](adr/0003-event-model-and-sanitization.md)).

**Divergence (violation of R1).** The current code derives PASS and FAIL tiles from
`test.completed` events, which come from a command classifier over sanitized shell command
text and its exit code (`tui/gates.py`: `classify_command`, `evidence_from_events`). An
`&&`-chain that exits 0 counts for every gate it contains; a failing or `;`/`||` chain gives
UNKNOWN. When HEAD moves past the recorded commit the signal becomes STALE and keeps the old
result. Until fixed, read PASS and FAIL here as "a command that looked like this exited 0 or
non-zero", nothing more. The target is `verification.observed` events shown as observations
with their method and confidence, never as gates. Review, documentation, CI and merge
readiness have no observable source in v0.1 and stay UNKNOWN.

## Timeline filter (`/`)

Space-separated terms, all ANDed: `agent:`, `session:`, `kind:` (exact or prefix, e.g.
`kind:tool`), `risk:`, `source:`, `attribution:`, `file:`, `since:`, `until:` (relative
`15m`, `2h`, `1d`, or an ISO time) and bare words, which match the event summary text.
Example: `kind:tool risk:medium since:2h`. A bad term shows a "filter problem" line and is
ignored. On other screens `/` filters rows by text. Enter applies and returns to the list;
Esc clears.

## Keys

| Key | Action |
| --- | --- |
| `o` `l` `w` `g` `e` `v` | Switch screen |
| `j` / `k`, arrows | Move |
| Enter | Open detail |
| Esc | Back, close or clear the filter |
| `/` | Filter |
| `m` | Timeline: load more |
| `p` | Pin the agent to the top of its lane (this session only) |
| `t` | Toggle 2x2 tiles (160+ columns) |
| `r` | Re-read now (index, git, artifacts) |
| Tab | Cycle focus: list, detail |
| `?` | Help |
| `q` | Quit |

## Layout

| Width | Layout |
| --- | --- |
| under 100 columns | One pane. Enter opens the detail, Esc returns. Readable at 80x24. |
| 100 to 159 | List on the left, detail on the right. |
| 160 and up | Same, or `t` for a 2x2 grid: list, detail, recent events, gates and worktrees. |

Four panes are never placed side by side. Resizing switches layout live and keeps the
selection. The tile preference survives a trip through a narrower size.

## Accessibility

Every state has a text label and an ASCII marker (`[W] WORKING`, `[PASS   ]`); colour is only
a hint. `NO_COLOR` (any value) switches to bold, dim and reverse styling only.

## Refresh and failure behaviour

A timer re-reads the spool every `--refresh` seconds on a worker thread; overlapping loads
coalesce. The projection is reloaded only when new events arrived; git is re-collected about
every 10 seconds, or immediately on `r`. If the optional `watchfiles` package is installed
(`pip install "cursorfleet[watch]"`), spool changes trigger an immediate refresh; the timer remains as
the fallback, and a watcher that fails shows a message and polling continues.

A missing or corrupt SQLite file is rebuilt from the spool. Corrupt or skipped spool lines
are counted in the banner. A failing refresh keeps the last good data on screen and shows
"refresh failed". The UI does not crash on any of these.

## Work artifacts in the dashboard (state layer)

Agents may leave `.cursorfleet/work/<task>/<NN>-<kind>-<role>.md` files
([ADR 0006](adr/0006-agent-declared-events.md)). The decided format is TOML frontmatter
between `+++` fences, schema `cursorfleet.artifact/0.1`, with `artifact_id`, `revision` and
a BLAKE2s `digest`. **Divergence:** the code and the generated templates still read a YAML
subset with schema `cursorfleet.artifact/1` and no identity, revision or digest; see
[kit.md](kit.md). In both formats every artifact event is self-reported and ineligible as
gate evidence. On every refresh a
read-only scanner (`state/artifact_scan.py`) turns valid ones into `self_reported` events
(`plan.created`, `handoff.created`, `blocker.raised`, `context.loaded`) in a synthetic
session `work:<task>`, and reports invalid ones as problems with a fixed description. The
body is never read past the size cap into any stored field, and never displayed; only the
validated frontmatter fields are kept. Scanning covers the main checkout and every linked
worktree; symlinks are skipped, at most 2000 files are read, and nothing is written.
Artifact events are held in memory, not persisted.

The projection database also stores a compact `events` table (a validated event copy plus
indexed columns) so the timeline can filter and page in SQL. It is created additively; an
older database is reindexed once from the spool. `status --json` is unchanged.

## Limits

- Local Cursor sessions only; cloud agents are invisible.
- Role, task and issue-ref values from artifacts are identifiers allowed by the schema and
  are shown as-is (labelled SELF-REPORTED). They are not secret-scanned.
- Lane assignment from hooks without tool activity is "lifecycle-only" and coarse.
- Token and cost data is not available from hooks.
- Windows and macOS terminals are expected to work but are tested on Linux only.

## PROVISIONAL (depends on unverified Cursor behaviour)

- Agent attribution on tool events ([ADR 0001](adr/0001-cursor-capabilities.md) Q1) and
  subagent start/stop pairing, which drive per-agent cards and tool counts.
- Whether the runtime directory resolves identically from every Cursor surface (Q4); if not,
  some agents appear under UNKNOWN / NO TELEMETRY.
- That agents follow the artifact conventions at all, and that `author_role` is not forged
  (it can be; ADR 0006).
- Gate command classification, which is a heuristic over sanitized commands and is
  non-authoritative (see Gates).
- Command text display. The decision is default OFF ([ADR 0003](adr/0003-event-model-and-sanitization.md));
  **Divergence:** the code stores a sanitized command string by default.
