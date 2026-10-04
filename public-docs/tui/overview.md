# TUI overview

```bash
cursorfleet tui [--path DIR] [--refresh SECONDS] [--no-git] [--no-watch]
```

An observe-only Textual dashboard for local agents in one repository. It
reads the SQLite projection (from the hook spool) and the read-only Git
collector. It never enforces, approves, or blocks anything, never fetches,
never touches the network, and never shows prompts, thinking text,
responses, file contents, or command output.

The command needs an interactive terminal and exits **2** otherwise. In
scripts use [`cursorfleet status --json`](../cli/status.md).

| Option | Default | Meaning |
| --- | --- | --- |
| `--path DIR` | cwd | A directory inside the Git repo. |
| `--refresh` | `2.0` | Poll interval, 0.25 to 60 seconds. |
| `--no-git` | off | Skip the Git collector (worktrees and gates show unknown). |
| `--no-watch` | off | Poll only, even if the optional `watchfiles` extra is installed. |

Telemetry is best-effort. Any view can be incomplete. The dashboard is
implemented, provisional, and unvalidated against live Cursor. New TUI work
is frozen until the live spike runs.

## Keys

| Key | Action |
| --- | --- |
| `o` | Overview (default) |
| `l` | Timeline |
| `w` | Worktrees |
| `g` | Gates |
| `e` | Evidence |
| `v` | Violations (**planned:** policy engine in v0.2; placeholder only) |
| `j` / `k`, arrows | Move |
| Enter | Open detail |
| Esc | Back, close, or clear the filter |
| `/` | Filter |
| `m` | Timeline: load more (200 rows first) |
| `p` | Pin the agent to the top of its lane (this session only) |
| `t` | Toggle 2x2 tiles (160+ columns) |
| `r` | Re-read now (index, git, artifacts) |
| Tab | Cycle focus: list, detail |
| `?` | Help |
| `q` | Quit |

## Screens

| Screen | What it shows |
| --- | --- |
| Overview | Agents in lanes: QUEUED, LOADING CONTEXT, PLANNING, WORKING, VERIFYING, AWAITING REVIEW, PATCHING, BLOCKED, DONE, STALE / OFFLINE, UNKNOWN / NO TELEMETRY. Enter opens agent detail. |
| Timeline | Events newest first, with source/attribution, agent, summary, and risk. |
| Worktrees | Branch, HEAD, dirty files, ahead/behind, stale or prunable, owning agent, last activity. `r` only re-reads. |
| Gates | Ten heuristic, non-authoritative signals per worktree. Not proof that anything passed. |
| Evidence | Heuristic test/lint/type observations, and separately what agents DECLARED in work artifacts. |
| Violations | **Planned / under development.** Placeholder: policy engine arrives in v0.2. |
| Help | Keys, layouts, honesty rules, setup hints. |

Agent detail shows role, task, issue refs, context sources, status and its
basis, worktree/branch/commit, changed-file count, last tools, last test
evidence, gates for that worktree, elapsed time, tool-call count,
compactions, handoff destination, and a stop report if Cursor sent one.
Token and cost are always "unknown (not exposed by Cursor hooks)".

## Layouts

| Width | Layout |
| --- | --- |
| Under 100 columns | One pane. Enter opens detail, Esc returns. Readable at 80x24. |
| 100 to 159 | List on the left, detail on the right. |
| 160 and up | Same, or `t` for a 2x2 grid: list, detail, recent events, gates and worktrees. |

Four panes are never placed side by side. Resizing switches layout live and
keeps the selection. The tile preference survives a trip through a narrower
size.

## Filter (`/`)

On the timeline, space-separated terms are ANDed: `agent:`, `session:`,
`kind:` (exact or prefix, e.g. `kind:tool`), `risk:`, `source:`,
`attribution:`, `file:`, `since:`, `until:` (relative `15m`, `2h`, `1d`, or
an ISO time), and bare words that match the summary. A bad term shows a
filter-problem line and is ignored. On other screens `/` filters rows by
text. Enter applies; Esc clears.

## Honesty

- Silence is **not** idle. See [current status](current-status.md).
- Timeline tags: `obs` (hook), `drv` (derived), `SELF` (artifact).
- Attribution is `exact`, `inferred`, or `unknown`. A role-only identity is
  `inferred`.
- Gate tiles are heuristic and non-authoritative.

Every state has a text label and an ASCII marker. `NO_COLOR` (any value)
drops colour for bold, dim, and reverse only.

Implemented versus planned: [current status](current-status.md).
