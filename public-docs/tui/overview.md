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

Telemetry is best-effort. Any view can be incomplete.

## Keys

| Key | Action |
| --- | --- |
| `a` | Active run (**default**) |
| `u` | Runs list |
| `o` | Sessions (archive / overview lanes) |
| `l` | Timeline |
| `w` | Worktrees |
| `g` | Observations (non-authoritative; ADR 0011) |
| `e` | Evidence |
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
| Active run | Task-centric run: participants, suggested sessions, run-scoped git, declared handoffs/blockers. |
| Runs | Active and archived runs (`cursorfleet run`). |
| Sessions | Agents in lanes: QUEUED through UNKNOWN / NO TELEMETRY. Enter opens agent detail. |
| Timeline | Events newest first, with source/attribution, agent, summary, and risk. |
| Worktrees | Branch, HEAD, dirty files, ahead/behind, stale or prunable, owning agent, last activity. |
| Observations | Heuristic verification signals per worktree; not proof anything passed. |
| Evidence | Heuristic observations plus what agents DECLARED in work artifacts. |
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

Same as in-repo [`docs/tui.md`](https://github.com/M9nx/cursorfleet/blob/main/docs/tui.md).
