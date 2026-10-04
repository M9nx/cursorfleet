# Empirical test plan (M0a live Cursor spike)

> **NOTHING IN THIS PLAN HAS BEEN EXECUTED OR VERIFIED.** No live Cursor session, CLI run,
> stress test or benchmark described here has been performed. Every result is **OPEN**.
> Statements about Cursor behaviour are quoted from the Cursor documentation ("per docs") or
> are questions to answer; none is a verified fact. The only measured number anywhere near
> this plan is the Linux steady-state latency of our own hook, measured outside Cursor
> (ADR 0001 section C).

This is the contract for the live spike. It adds no code. New M2 and TUI work stays frozen
until it is done ([status](status.md)). It is the author's plan, not an independent audit.
Human next steps (do not run the spike from an agent): [`spike-prep.md`](spike-prep.md).

## Ground rules

- **Procedures** live in [`spike/README.md`](../spike/README.md) ("README" below, by section
  number); the questions are in [`spike/questions.md`](../spike/questions.md). The spike kit
  is not changed by this plan. Where the kit has no procedure for a row, the row says so and
  gives manual steps; extending the kit is a follow-up.
- **Scratch repo only.** One commit, no real secrets, no real credentials, no network from
  hooks. Keep an out-of-band terminal so a mis-set hook cannot lock you out of cleanup.
- **Synthetic data only.** Canaries and filler are made up. Never paste real prompts, emails,
  paths or tokens into notes, fixtures or issues.
- **"Expected" always means "expected per docs".** A doc statement can be refuted. Doc
  sources, read on 2026-10-04: [hooks](https://cursor.com/docs/hooks),
  [subagents](https://cursor.com/docs/subagents),
  [rules](https://cursor.com/docs/context/rules),
  [skills](https://cursor.com/docs/skills),
  [headless CLI](https://cursor.com/docs/cli/headless). Worktree facts are taken from
  ADR 0001 A8 and were not re-read. The sections cited below are the doc page headings.
- **Model non-determinism.** The model chooses which tool to call. An attempt counts only if
  the Cursor transcript shows the intended tool call happened; otherwise discard and redo.
  Each row states how many repetitions it needs.
- **Hook sets.** The *product set* is the nine hooks of ADR 0007 (`sessionStart`,
  `sessionEnd`, `preToolUse`, `postToolUse`, `postToolUseFailure`, `subagentStart`,
  `subagentStop`, `preCompact`, `stop`). The *diagnostic set* is the spike kit's
  `hooks.json.example`: the nine plus `beforeShellExecution`, `afterShellExecution` and
  `afterFileEdit`. The kit never registers `beforeMCPExecution`, `afterMCPExecution`,
  `beforeReadFile`, `beforeSubmitPrompt`, `afterAgentResponse`, `afterAgentThought`, the Tab
  hooks or `workspaceOpen`.
- **Throwaway tooling** (scripts for stress, canaries, latency) lives outside this repository
  and is not committed. If one proves useful, a follow-up can propose adding it.
- **Raw captures** follow the handling rules in row 16, for every row.
- **Verdict vocabulary.** Spike questions use `CONFIRMED`, `REFUTED`, `PARTIAL`, `OPEN`; the
  ADR 0001 matrix uses `NOT RUN`, `PASS`, `FAIL`, `PARTIAL`. Today every value is `OPEN`.

## Result record (one per row, all fields OPEN)

Every row ends with a result record in this shape. Fill it in only after a run; keep `OPEN`
until then. A row with sub-results (per scenario, per OS, per case) keeps one `OPEN` cell per
sub-result in its own table.

```text
Result: OPEN
Date: -
Cursor version / OS / surface: -
Evidence path (never inside the repo working tree): -
Reviewer sign-off: -
Raw-capture sign-off (perms checked, retention deadline, deleted on, verified by): -
ADRs affected: <ids>
```

## Row index and numbering

Rows 1 to 14 keep their old numbers, so inbound references in other docs (for example
[`follow-ups.md`](follow-ups.md)) remain valid. Rows 15 to 18 are new.

| Row | Topic | Old row |
| --- | --- | --- |
| 1 | Scenario-to-hook matrix, IDE main agent | 1 (replaced) |
| 2 | CLI interactive `agent` | 2 |
| 3 | CLI headless `agent -p`, without and with `--force` | 3 (expanded) |
| 4 | Agents Window | 4 |
| 5 | Cursor-managed worktree | 5 |
| 6 | Manual worktree | 6 |
| 7 | Concurrency: real overlap and synthetic multi-process stress (Q5) | 7 (strengthened) |
| 8 | Subagent identity inside tool hooks (Q1) | 8 (new vocabulary) |
| 9 | Custom `subagent_type` naming (Q2) | 9 |
| 10 | `generation_id` and `Task` linkage | 10 (criteria added) |
| 11 | Permission-hook reply shape (release gate) | 11 (case matrix) |
| 12 | `ask` on permission hooks | 12 |
| 13 | Latency: hook process outside Cursor (A) and end-to-end (B) (Q6) | 13 (split) |
| 14 | Instruction loading with behavioural canaries | 14 (replaced) |
| 15 | Privacy-boundary release gate | new |
| 16 | Raw-capture permissions, retention and cleanup | new |
| 17 | Non-git workspace | new |
| 18 | Existing-hooks coexistence | new |

## Order of work

1. Setup and self-test (README 0, 1). Read row 16 first.
2. IDE main agent and subagents (README 2): rows 1, 8, 9, 10, 12.
3. IDE worktrees and parallel subagents (README 3): rows 5, 6, 7(a).
4. Agents Window (README 3, last paragraph): row 4.
5. CLI (README 4): rows 2, 3.
6. Failures, compaction, reply shapes and latency on each OS (README 5): rows 11, 13.
7. Synthetic stress on each OS: row 7(b).
8. Instruction loading (not in the README): row 14.
9. Non-git and coexistence: rows 17, 18.
10. Privacy-boundary gate on the final configuration: row 15.
11. Analysis and verdicts (README 6), cleanup (row 16), then ADR updates.

## Rows

### 1. IDE (desktop), main agent: scenario-to-hook matrix

Purpose: replace "every hook fires" with a verdict per scenario and per hook, so a gap names
the exact trigger and hook. Scenarios 1.1 to 1.17 run first in the IDE; rows 2, 3 and 4
repeat the subset marked in the surface grid below.

- Procedure: README 1 (scratch repo, kit installed, `.cursor/` committed, workspace
  trusted). Before each scenario set a label that names it and the repetition:
  `python3 .cursor/hooks/capture_hook.py --set-label ide-1.4-r1`. Start a fresh agent chat
  per scenario unless stated. Prompts name the tool to use ("use the shell tool to run ..."),
  and the Cursor transcript must show that tool call. Repeat each scenario 3 times.
- Reading the capture (read-only; one line per hook call):

  ```sh
  jq -c '{e:.hook_event_name,t:.ids.tool_name,u:.ids.tool_use_id,s:.start_epoch_ms,l:.label}' \
    "$(python3 .cursor/hooks/capture_hook.py --print-capture-dir)/captures.jsonl"
  ```

- Record for every scenario (from the kit's records, which hold key names and value types,
  not values): hooks fired by name and count per label; order by `start_epoch_ms`; payload
  key shapes (`keys`, with nested key names for `tool_input` and `edits`); ids and their
  equality relations (`conversation_id`, `generation_id`, `session_id`, `tool_use_id`,
  `tool_call_id`, `subagent_id`, `parent_conversation_id`); enums, booleans and counters
  (`vals`); `cursor_version`; whether `model`, `model_id` and `model_params` are present;
  the names (never values) of `CURSOR_*` and `CLAUDE_*` environment variables seen by the
  hook process (`env_names_seen`); the surface; whether the Hooks output channel logged errors.
- The kit cannot see values, so it cannot say whether `postToolUse.tool_output` for Shell
  carries an exit code (ADR 0007 open question). Answer that with a one-off throwaway hook
  in the scratch repo that writes one boolean per call (is an `exitCode` key present), never
  the text.

Table 1A: what to expect per scenario. "Expected" is per docs (hooks reference, sections
for each hook; ADR 0001 A1 to A5). "Do not assume" lists hooks that must not be expected, or
that the docs are silent on: record them if they appear, and never require them.

| ID | Scenario and trigger | Expected to fire (per docs) | Must NOT be expected | Result |
| --- | --- | --- | --- | --- |
| 1.1 | Open a new agent chat | `sessionStart` (fire-and-forget; `session_id` same as `conversation_id` per docs) | `stop` or `sessionEnd` before the first turn ends; `workspaceOpen` (not registered) | OPEN |
| 1.2 | Successful Shell: run `echo hello` | `preToolUse` (Shell), then `postToolUse` (Shell), same `tool_use_id`; diagnostic set adds `beforeShellExecution`, `afterShellExecution` | `postToolUseFailure` for that `tool_use_id`; `subagentStart` | OPEN |
| 1.3 | Successful Read: read `README.md` | `preToolUse` (Read), `postToolUse` (Read) | `beforeReadFile` (content hook, never registered; if it appears the scratch `hooks.json` is wrong, stop and fix it) | OPEN |
| 1.4 | Write or edit: (a) create a file, (b) edit an existing file, (c) delete a file | `preToolUse` and `postToolUse` with a write-class tool (`Write`, and `Delete` for (c); record each `tool_name` verbatim); diagnostic set adds `afterFileEdit` for edits | `postToolUseFailure`; `afterFileEdit` for the delete (docs silent: record) | OPEN |
| 1.5 | Grep: search the repo for the word `scratch` | `preToolUse` (Grep), `postToolUse` (Grep) | `postToolUseFailure` | OPEN |
| 1.6 | MCP tool, only if a harmless read-only MCP server is already configured; otherwise record `not reachable` | `preToolUse` and `postToolUse` with `tool_name` of the form `MCP:<tool_name>` (matcher docs) | `beforeMCPExecution`, `afterMCPExecution` (not registered in the kit or the product) | OPEN |
| 1.7 | Failed tool call: (a) Shell `cat does-not-exist.txt`; (b) Read a missing file | `preToolUse`, then `postToolUseFailure` (`failure_type` `error`) or, if Cursor treats a non-zero exit as a normal Shell result, `postToolUse`; record which, for (a) and (b) separately | both `postToolUse` and `postToolUseFailure` for one `tool_use_id` (docs describe success-only and failure-only); `permission_denied` | OPEN |
| 1.8 | Tool denied, if reachable harmlessly: (a) decline an approval prompt in the UI; (b) ask `cf-reviewer` (`readonly: true`) to create a file; (c) a scratch `preToolUse` deny, only through row 11 | `postToolUseFailure` with `failure_type` `permission_denied` (docs: runs when a tool "fails, times out, or is denied") | a `postToolUse` for the denied call | OPEN |
| 1.9 | Subagent, foreground: README 2 prompt (`cf-reviewer`, then `cf-writer`, sequential) | parent: `preToolUse` and `postToolUse` with `Task`; `subagentStart`, tool hooks from inside the subagent, then `subagentStop` with `status` `completed` | `subagent_id` on `subagentStop` (docs list none); subagents having their own `sessionStart` or `sessionEnd` (docs silent) | OPEN |
| 1.10 | Subagent, background: a scratch agent with `is_background: true` (made by hand in the scratch repo, not under `spike/`), or the UI's background option | same hooks as 1.9; the `Task` call may return before `subagentStop` | `subagentStop` before the parent's `stop`; `postToolUse` (`Task`) after `subagentStop` | OPEN |
| 1.11 | Subagent aborted (stop it from the UI) or errored (only if it happens naturally) | `subagentStop` with `status` `aborted` or `error` | a `followup_message` effect (the kit never returns one) | OPEN |
| 1.12 | Manual compaction, if the UI offers a manual control (record its exact name and Cursor version; otherwise `not reachable`) | `preCompact` with `trigger` `manual` | any hook able to block or alter compaction (observational per docs) | OPEN |
| 1.13 | Auto compaction: grow the context with harmless synthetic filler (repeated Reads of a large generated text file); give up after 10 turns | `preCompact` with `trigger` `auto` and the `context_*` counters | `trigger` `manual`; compaction without a `preCompact` | OPEN |
| 1.14 | Agent stop, completed: let a normal turn end | `stop` with `status` `completed`, `loop_count` 0 | `loop_count` above 0 (the kit returns `{}`); `sessionEnd` as a consequence of `stop` | OPEN |
| 1.15 | Agent stop, aborted: press Stop while a harmless `sleep 20` Shell call runs | `stop` with `status` `aborted`; possibly `postToolUseFailure` with `is_interrupt` true | `stop` with `status` `completed` | OPEN |
| 1.16 | Agent stop, error: only if it happens naturally; never force an error | `stop` with `status` `error` | none | OPEN |
| 1.17 | Session end: (a) close the chat tab; (b) close the window; (c) a conversation that simply finished | `sessionEnd` with `reason` from `completed`, `aborted`, `error`, `window_close`, `user_close`; record which action gives which value | `sessionEnd` for every conversation (fire-and-forget, the window may be gone); `sessionEnd` after (c) with no close action | OPEN |

Table 1B: extra evidence and refute conditions. The general rule applies to every
scenario, then the scenario-specific rows add to it.

- **PASS** (per scenario): in 3 of 3 valid repetitions every expected hook fired the stated
  number of times with the documented keys present and ids related as stated, and no
  "must NOT be expected" hook appeared.
- **PARTIAL**: an expected hook fired in 1 or 2 of 3 repetitions, or documented keys are
  missing (list them).
- **REFUTED**: an expected hook fired in 0 of 3 valid repetitions, or a hook the docs say
  must not appear did.
- Undocumented keys and doc-silent behaviours are recorded, never counted for or against.

| ID | Also record | Specific refute |
| --- | --- | --- |
| 1.1 | `session_id` equals `conversation_id`; `is_background_agent`; `composer_mode` | two `sessionStart` for one new chat |
| 1.2 | `duration` on `postToolUse`; order of `preToolUse` against `beforeShellExecution` (diagnostic); exit-code boolean (manual check above) | `tool_use_id` differs between pre and post |
| 1.3 | nested key names of `tool_input` (is there a path-like key?) | no `preToolUse` for a Read the transcript shows |
| 1.4 | nested key names of `tool_input` and `edits` items (ADR 0007: is there a path key to allowlist?); `tool_name` per sub-run; whether (a) gives `afterFileEdit` | no write-class tool event for a file that exists afterwards (then `file.changed` can come only from git) |
| 1.5 | `tool_name` verbatim | none beyond the general rule |
| 1.6 | exact `tool_name` form; whether a `matcher` of `MCP:` style works | no `preToolUse` for an MCP call (ADR 0007: omitting the MCP hooks then loses data) |
| 1.7 | for (a) and (b) which of `postToolUse` and `postToolUseFailure` fired; `failure_type`; `is_interrupt`; `duration` | both fire for one `tool_use_id` |
| 1.8 | which route produced which hook and `failure_type` | a denied call still yields `postToolUse` |
| 1.9 | order of `Task` pre, `subagentStart`, inner tool hooks, `subagentStop`, `Task` post; keys on `subagentStart` and `subagentStop`; number of inner tool hooks against `subagentStop.tool_call_count` (a lower count means missed hooks) | no `subagentStart` for a subagent the UI shows |
| 1.10 | order of `stop`, `subagentStop` and `postToolUse` (`Task`) | none beyond the general rule |
| 1.11 | `status` on `subagentStop`; whether `stop` also fires | none beyond the general rule |
| 1.12, 1.13 | `context_usage_percent`, `context_tokens`, `context_window_size`, `message_count`, `messages_to_compact`, `is_first_compaction`; whether `preCompact` precedes the next `preToolUse` | `trigger` does not match how it was triggered |
| 1.14 | `stop` count per user message (should be 1) | two `stop` for one turn |
| 1.15 | `stop.status`; whether the in-flight tool gave `postToolUseFailure` | none beyond the general rule |
| 1.16 | `stop.status` | not applicable if it never happened (record `not reachable`) |
| 1.17 | `reason`, `duration_ms`, type of `final_status`; time between the UI action and the hook; order against the last `stop` | no `sessionEnd` after (a) in 3 of 3 |

Surface grid (which hooks fired where). Fill each cell with the list of hooks seen, once the
scenario was run on that surface: rows 1 to 4 supply the cells. All cells OPEN.

| Scenario | IDE (row 1) | CLI interactive (row 2) | `-p` without `--force` (row 3) | `-p --force` (row 3) | Agents Window (row 4) |
| --- | --- | --- | --- | --- | --- |
| 1.1 session start | OPEN | OPEN | OPEN | OPEN | OPEN |
| 1.2 Shell success | OPEN | OPEN | OPEN | OPEN | OPEN |
| 1.4 write or edit | OPEN | OPEN | OPEN | OPEN | OPEN |
| 1.7 failed tool | OPEN | OPEN | OPEN | OPEN | OPEN |
| 1.9 subagent foreground | OPEN | OPEN | OPEN | OPEN | OPEN |
| 1.14 stop completed | OPEN | OPEN | OPEN | OPEN | OPEN |
| 1.17 session end | OPEN | OPEN | OPEN | OPEN | OPEN |

- Artifacts: `captures.jsonl` per label; analysis section listing hooks seen and
  `cursor_versions`; reviewed fixtures in `tests/fixtures/cursor/ide/` (row 16 rules).
- Can change: ADR 0001 A5 and the matrix row; ADR 0007 (hook set, `file.changed` source,
  exit-code source); ADR 0003 hook-to-kind mapping; ADR 0010 (`postToolUse` against
  `postToolUseFailure`, `stop` against `sessionEnd`); `hook_normalize` field assumptions;
  whether the IDE claim can be made at all.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; ADRs affected: 0001, 0003, 0007, 0010.

### 2. CLI interactive `agent`

- Procedure: README 4, interactive session, label `cli-interactive`. Run the surface-grid
  subset of row 1 (scenarios 1.1, 1.2, 1.4, 1.7, 1.9, 1.14, 1.17) and fill the "CLI
  interactive" column.
- Optional diagnostic: add a `workspaceOpen` entry to the scratch repo's `hooks.json` (not
  to `spike/`). Per docs that hook runs in the desktop app and the CLI; the kit accepts the
  name and drops its content. It shows whether the CLI loaded project hooks at all.
- Artifacts: events per label; fixtures in `tests/fixtures/cursor/cli/`.
- Pass: the set of hooks that fire is recorded per hook name, each on a documented-field
  payload, and `cursor_version` is meaningful.
- Fail or partial: the README and platform docs keep "CLI not supported".
- Can change: ADR 0001 (Q3 verdict), platform-support, product-contract supported surface.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; ADRs affected: 0001 Q3.

### 3. CLI headless `agent -p`: without and with `--force`

Docs (headless page, "File modification in scripts"): `--print` is non-interactive; without
`--force` (or `--yolo`) "changes are only proposed, not applied"; with it the agent changes
files directly. The page says nothing about hooks (ADR 0001 A12). This row tests three
variants with the same prompt, each under its own label, run from the scratch repo root.

- Setup: README 0 and 1, then README 4. Authenticate with `agent login`, or with
  `CURSOR_API_KEY` set in the environment only: never on a command line, in a committed
  script, or in notes. The kit records environment variable *names* that match `CURSOR_*`
  or `CLAUDE_*` (so the name `CURSOR_API_KEY` can appear in `env_names`, never its value).
- Safety: scratch repo only; start each run from a clean `git status`; wrap each run in a
  5-minute wall-clock limit so a hang cannot linger; use only the documented flags `-p`,
  `--force`, `--output-format` and `--stream-partial-output` (not `--yolo`).
- Prompt P (harmless, identical in every variant): "Create notes/p1.txt containing the single
  line hello. Then run 'git status' in the shell. Then use the cf-reviewer subagent to review
  README.md. Reply done." Failure prompt F: "Run `cat does-not-exist.txt` and report its exit
  code."
- Set the label first, one per variant: `cli-print-noforce`, `cli-print-force`,
  `cli-print-stream`.

**3a. Without `--force`** (`agent -p "<P>"`, then `agent -p "<F>"`)

- Record side effects: `git status --porcelain` afterwards, whether `notes/p1.txt` exists, the
  process exit code, whether anything prompted or hung.
- Record hooks (scenarios 1.1, 1.2, 1.4, 1.7, 1.9, 1.14, 1.17): which of `preToolUse`,
  `postToolUse`, `postToolUseFailure` and (diagnostic) `afterFileEdit` fire for the write that
  is proposed but not applied, with `failure_type` if any; whether the read-only `git status`
  Shell call ran at all (docs are silent); subagent hooks; `cursor_version`.
- Classify what fires for the not-applied write, per repetition (3 repetitions):

  | Code | Observation | Meaning if it holds |
  | --- | --- | --- |
  | W1 | no tool hook for the write | hooks do not see proposed edits |
  | W2 | `preToolUse` only | the write is announced, never completed |
  | W3 | `preToolUse` and `postToolUse` succeed, file absent | hooks report success while nothing was applied: a hook-derived `file.changed` would be a false positive here (ADR 0007, ADR 0003 mapping); only git can say a file changed |
  | W4 | `preToolUse` and `postToolUseFailure` (for example `permission_denied`) | denied or not-applied writes show as failures; no `file.changed` |
  | W5 | file applied without `--force` | the docs are refuted for this version |

- Pass (3a): one code per repetition recorded, identical in 3 of 3 (otherwise PARTIAL with
  the rates), and the file is absent. Refute: W5, or no hook fires at all in 3 of 3 (then
  hooks do not run under `-p`; row 2's consequence applies).

**3b. With `--force`** (`agent -p --force "<P>"`, then `"<F>"`)

- Side effects must stay inside the scratch repo: check `git status --porcelain` lists only
  `notes/p1.txt`, `git worktree list` is unchanged, and (with 3c) every tool-call path is
  inside the scratch repo.
- Record hooks for the same scenarios as 3a, plus whether the write gives `preToolUse` and
  `postToolUse` with a write-class tool and `afterFileEdit` (diagnostic) in 3 of 3 runs.
- Pass (3b): each hook that fires is recorded per hook name on a documented-field payload
  with `cursor_version`, and the file exists. Refute: the file exists but no write-class
  hook fired in 3 of 3 (hooks do not observe headless writes), or no hook fires at all.
  The ADR 0001 matrix row "CLI headless `agent -p`" takes this result for PASS or FAIL; 3a
  and 3c are extra columns.

**3c. `--output-format stream-json`** (`agent -p --force --output-format stream-json "<P>"`,
optionally with `--stream-partial-output`)

- The stream carries message text and tool arguments including file paths (ADR 0001 A11), so
  the output file is a raw capture (row 16): redirect it into the raw capture directory, never
  to a shared log, and never commit it. Docs list the event types `system` (`init`),
  `assistant`, `tool_call` (`started`, `completed`) and `result` (`duration_ms`).
- Keep only: counts of `type` and `subtype`, tool-call kinds, `result.duration_ms`. Check
  locally, without printing it, that the API key value does not occur in the file.
- Compare with the capture of the same run: `tool_call` `started` count against `preToolUse`
  count, and `completed` against `postToolUse` plus `postToolUseFailure`.
- Pass (3c): the hook set and counts equal those of 3b, and the stream counts reconcile with
  the hook counts (or each difference has a recorded cause, for example `Task`). Refute: the
  output format changes which hooks fire, or hook counts are below stream counts (hooks missed
  events, which bounds how much any CLI telemetry could be trusted).

- Artifacts: events per label; fixtures in `tests/fixtures/cursor/cli-print/` (3b only, by the
  row 16 review), recorded separately from row 2.
- Can change: ADR 0001 (Q3 verdict), ADR 0007 (what `file.changed` can rely on), ADR 0003
  (hook-to-kind mapping), platform-support, whether CI or scripted agent runs can be observed.
  Stream ingestion stays a v0.2 non-goal regardless (ADR 0001 A11).
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; ADRs affected: 0001 Q3, 0003, 0007.

### 4. Agents Window

- Procedure: README 3 last paragraph (label `agents-window-wt`): start an agent from the
  Agents Window into a worktree, one file edit and one shell command.
- Artifacts: fixtures in `tests/fixtures/cursor/agents-window/`; `git worktree list`
  (do not paste home paths into issues).
- Pass: hooks fire and `workspace_roots` is recorded.
- Fail or partial: not supported; the doc statement stays.
- Can change: ADR 0001 (Q3), ADR 0002 (runtime dir resolution, Q4), ADR 0012.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence: -;
  reviewer sign-off: -; ADRs affected: 0001 Q3, 0002 Q4, 0012.

### 5. Cursor-managed worktree (`/worktree`, `/best-of-n`)

- Procedure: README 3 (labels `ide-worktree-cmd`, `ide-best-of-n`).
- Artifacts: Q3/Q4 `git_kind` table, `capture_dir_source`; fixtures in
  `tests/fixtures/cursor/worktree-managed/`.
- Pass: project hooks fire from the worktree; `workspace_roots` and hook cwd are recorded;
  the runtime directory under the git common dir resolves identically from the main
  checkout and the worktree (Q4).
- Fail: ADR 0002 runtime directory choice is wrong for worktrees and must be revisited.
- Can change: ADR 0002 (blocking), ADR 0012, the `worktree_id` derivation, TUI worktree view.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence: -;
  reviewer sign-off: -; ADRs affected: 0002 Q4, 0012.

### 6. Manual worktree (`git worktree add`, opened in Cursor)

- Procedure: create the worktree by hand, open it in Cursor, repeat row 5's scenario. The
  README has no manual-worktree section; use README 3's analysis steps.
- Artifacts: fixtures in `tests/fixtures/cursor/worktree-manual/`.
- Pass: same criteria as row 5.
- Can change: ADR 0002, ADR 0012, platform-support.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence: -;
  reviewer sign-off: -; ADRs affected: 0002 Q4, 0012.

### 7. Concurrency: real overlap and synthetic multi-process stress (Q5)

Question (ADR 0001 Q5, ADR 0002): do hook processes overlap in time, and do concurrent
appends to the spool stay intact on every OS we claim? Two experiments answer different
halves: (a) whether Cursor really runs hooks concurrently, (b) whether the spool survives
heavy concurrent appends whatever Cursor does. A green (a) does not replace (b).

**Storage being tested (corrected).** ADR 0002: `spool/<session_id>/<writer>.jsonl`, that is
one spool file per writer per session, where the writer is `main` or the subagent instance id
when known. It is not one file shared by every session. Each line is `<crc32 hex8> <space>
<event json>` plus a newline, at most 8,192 bytes, written with one `O_APPEND` write. A
writer file rotates to `<writer>.<ms>-<pid>.jsonl` at 4 MiB, and a session directory stops
accepting appends at its byte cap (default 50 MiB) by writing a `.capped` marker. Two
consequences for the design of this test:

- If tool hooks carry no subagent instance id (row 8 is not EXACT), every hook process of a
  session uses writer `main`, so many short-lived processes append to the same file. That
  multi-process-per-file case is the realistic worst case and is tested (topology T2 below).
- The spike kit's `captures.jsonl` is one shared file per repository, which is harsher than
  the product layout. It is a fair worst case for (a) but says nothing about the product's
  file split.

#### 7(a). Real Cursor overlap test

- Procedure: README 3 (label `ide-parallel-wt`), extended to four variants, each repeated 5
  times with its own label (`ide-par-v1-r1` and so on):
  - V1: two parallel `cf-writer` subagents, isolation requested in the prompt (README 3).
  - V2: the same two, no isolation requested (distinct target files, so no overwrites).
  - V3: two parallel subagents of different types (`cf-reviewer` and `cf-writer`).
  - V4: parallel tool calls in the main agent: "in one step, run these four independent
    commands at the same time: `echo a`, `echo b`, `echo c`, `echo d`". Whether Cursor
    issues them in parallel is itself a result.
- Overlap predicate (timestamps prove it): two hook records overlap when their pids differ
  and `s1 < e2` and `s2 < e1`, with `s` = `start_epoch_ms` and `e` = `end_epoch_ms` of the
  kit's records; cross-check with the monotonic fields (`mono_start_ms`, `mono_end_ms`). The
  kit measures from interpreter-level start to just before its final write
  (`latency_excludes_final_write`), so each measured interval lies inside the real process
  lifetime: an observed overlap is conclusive, a missing overlap is not proof of serialization.
- Evidence: Q5 section of `analyze.py` (`max_concurrent_hook_processes`,
  `overlapping_process_pairs`, `tool_calls_started_while_another_open`,
  `overlapping_subagent_windows`), `corrupt_lines_skipped`, and for each repetition the list
  of overlapping pairs by `tool_use_id`. `overlapping_subagent_windows` pairs starts with stops
  by type and order, so it is approximate for same-type subagents: build the windows by hand
  from the row 8 ground truth.
- Also record: whether isolation was honoured (`git worktree list`, `workspace_roots`),
  `subagentStart.git_branch` and `is_parallel_worker`, and whether the work truly overlapped
  (task cards in the UI).
- Pass (a): in at least one repetition of V1 or V3, hook processes belonging to different
  subagents overlap; V4 either shows overlapping hook processes for different `tool_use_id`s
  or is recorded as sequential; `corrupt_lines_skipped` is 0 in every repetition.
- Refute (a): a torn or interleaved line in the shared capture (the ADR 0002 append claim
  fails for Cursor's real pattern). If the work overlapped (windows overlap, tool calls
  started while another was open) but no hook processes did in 5 of 5 repetitions per variant,
  record "serialized observed": the risk is lower on that version and surface, but (b) is
  still required. If Cursor never ran anything concurrently, (a) stays OPEN.

#### 7(b). Synthetic multi-process stress test (design validation, throwaway tooling)

This is a design-validation experiment, performed with throwaway tooling kept outside the
repository or a documented manual procedure. It adds no product code and changes none.

- Writers: a driver spawns W separate OS processes (not threads) with a start barrier. Each
  process writes E events through the product append function with explicit arguments, or
  through the product hook for (b2), and logs every outcome to its own private ack file that
  is not part of the spool.
- Event: a JSON object with writer index `w`, per-writer sequence `n` (0 to E-1), a unique id
  `w<w>-n<n>`, and ASCII padding. Bounded size: the whole encoded line (CRC prefix, body and
  newline) is between 256 and 8,192 bytes, drawn uniformly, with 5% exactly 8,192 bytes, 5%
  exactly 4,097 bytes and 5% at most 512 bytes. No line exceeds the 8,192-byte limit
  (`MAX_LINE_BYTES`). The random seed is recorded so a run can be repeated.
- Configurations (every one run at least 3 times per OS):

  | Config | Writers x events | Total | Topology | Rotation and cap |
  | --- | --- | --- | --- | --- |
  | A | 8 x 750 | 6,000 | T1: one writer file per process | defaults (4 MiB, 50 MiB) |
  | B | 8 x 750 | 6,000 | T2: all processes share one writer file (`main`) | defaults |
  | C | 16 x 400 | 6,400 | T2 | rotate at 256 KiB, to force many rotations |
  | D | 8 x 750 | 6,000 | T2 | rotate at 256 KiB, session cap 2 MiB |

  Each total is at least 5,000 events across at least 8 writer processes. The total size of
  B is about 25 MiB, so B also crosses the 4 MiB rotation several times.
- (b1) Raw-line level: call the product `append_event` (imported, not modified) with
  arbitrary JSON text of the sizes above, so size can be controlled (valid `Event` objects
  cannot be padded to 8 KiB). Verify with an independent checker that recomputes
  `zlib.crc32`, not with the product reader.
- (b2) Hook level: invoke the real `cursorfleet-hook` as a subprocess with an argv list and a
  timeout, 8 concurrent workers, at least 6,000 synthetic `preToolUse` payloads in total
  (doc-derived shape, `tool_use_id` of the form `tu-<worker>-<seq>`, one shared
  `conversation_id`), in a throwaway git repo that is not the Cursor scratch repo. A second
  variant gives each worker its own `subagent_id` (T1-like). A third run raises the count until
  the session directory exceeds 8 MiB (at least two rotations at the default 4 MiB). A fourth
  sets `CURSORFLEET_MAX_SESSION_MB=1` to trigger the cap. Capture every exit code and stdout:
  all must be 0 and the allow reply. Verify with the product reader (`cursorfleet status
  --json` and `replay`) and by counting `tool_use_id` values in the spool.
- Assertions, for every run:
  1. **No lost events.** Every event a writer acknowledged as written appears exactly once in
     the spool (all segments); lost 0, duplicated 0. Events a writer was told were not
     written (cap reached, I/O error) are counted separately as dropped.
  2. **No torn or interleaved lines.** Every physical line is 8 hex digits, a space, a JSON
     body that parses, and a newline; the number of lines equals the number of events; no line
     is over 8,192 bytes; no line holds two records; no line lacks its terminating newline.
  3. **CRC valid** on 100% of lines.
  4. **Per-writer order preserved.** For each writer, `n` is strictly increasing in file
     order (segments ordered by the millisecond stamp in the file name, the live file last).
  5. **Rotation and cap behave.** A live file never exceeds rotate size plus the lines
     written by processes already past the size check (bound: rotate size + W x 8,192 bytes);
     rotated names are unique; no zero-length leftovers; in D the `.capped` marker exists and
     nothing acknowledged is written after it; record the overshoot past the cap, which
     design-wise is up to one segment plus in-flight lines because the cap is checked only
     when a file is created or rotated. Specifically look for a rotation race: two processes
     crossing the rotation size together, where the second rename could take the fresh file
     (a risk read off `state/spool.py`, not an observed bug).
  6. **Corruption counters.** Report the independent checker's counts and the product
     reader's `Corruption` counters (`bad_format`, `bad_crc`, `bad_json`, `invalid_event`,
     `unknown_version`, `oversize`, `misplaced`, `torn_tail`, `resynced`, `total`). They must
     be 0 here. Negative control: inject exactly 10 known-bad lines of each kind (bad CRC, bad
     shape, torn tail, oversize) into a copy of a spool and confirm the counters report exactly
     those, so a 0 means something.
- Operating systems: every OS that [platform-support](platform-support.md) lists: Linux,
  macOS, Windows. Run on the CI matrix runners (`ubuntu-latest`, `macos-latest`,
  `windows-latest`, as in `.github/workflows/ci.yml`) through a throwaway branch or a manual
  workflow run that is not merged, and on at least one real machine per OS where available
  (macOS and Windows have never been run by hand). Record the file system (for example ext4,
  APFS, NTFS), that it is a local disk (no network or synced folders), CPU count and Python
  version. On Windows also record whether any `os.write` returned fewer bytes than requested
  and any antivirus involvement.
- Pass (b): assertions 1 to 6 hold in every run of every configuration on an OS. An OS whose
  runs all pass may claim "intact concurrent appends"; a green Linux run says nothing about
  macOS or Windows.
- Refute (b): any lost event, torn or interleaved line, CRC failure or order violation not
  explained by the cap, on an OS. That OS cannot claim intact appends and Q5 is REFUTED
  there. Consequences: ADR 0002 (spool design, the Windows `O_APPEND` assumption, per-process
  segment files or another scheme) and platform-support. If only T2 fails, the per-writer
  split is enough only when row 8 gives EXACT; otherwise ADR 0002 must change.

- Artifacts: Q5 section, `spike/results/` notes, per-OS stress reports (counts, seeds, the
  six assertions, counters), with no event content.
- Can change: ADR 0002 (blocking for the OS claim), ADR 0010 (pairing), ADR 0012, ADR 0001
  matrix row "Concurrency and parallel subagents".
- Result record, per OS (all OPEN): Linux: OPEN; macOS: OPEN; Windows: OPEN. Date: -;
  Cursor version / OS / surface: -; evidence path: -; reviewer sign-off: -;
  ADRs affected: 0001 Q5, 0002, 0010, 0012.

### 8. Subagent identity inside tool hooks (Q1)

Question (ADR 0001 Q1): do tool hooks fired inside a subagent identify the **current
subagent instance**, or can they be **deterministically linked** to it through an
empirically verified id relationship? Per docs only `subagentStart` documents `subagent_id`,
`subagent_type` and `parent_conversation_id`; `subagentStop` documents `subagent_type` but no
id; tool hooks document no subagent identity.

**Result vocabulary** (the only four outcomes; classify per hook name, by hand). Each outcome
maps to one Q1 verdict and one ADR 0003 `attribution` value. The mapping is the owner
decision of 2026-10-04; the canonical enum is exactly `exact | inferred | unknown`:

| Outcome | Definition | Q1 verdict | `attribution` |
| --- | --- | --- | --- |
| EXACT | Tool hooks inside the subagent carry an id that uniquely identifies the *current subagent instance*, and that id equals `subagentStart.subagent_id` of exactly one start (or is otherwise deterministically linkable to it by a relationship this row has verified), so it is linkable to a role and a lifecycle. | CONFIRMED | `exact` |
| ROLE_ONLY | Tool hooks carry only the subagent type or role (for example `subagent_type`). It names the kind of agent, not the instance: two concurrent subagents of one type are indistinguishable. A role-only identity is never `exact`. | PARTIAL | `inferred` |
| PARENT_ONLY | Tool hooks carry only the parent's conversation id (for example `parent_conversation_id`, or a `conversation_id` equal to the parent's). It says who spawned the work, not which subagent did it. | REFUTED | `unknown` |
| UNKNOWN | No identity-bearing field of any kind is present on the tool hooks (inside subagent windows they look like main-agent tool hooks): REFUTED. If instead a candidate field exists but its meaning cannot be established, or the evidence is ambiguous or inconsistent (a field present on some hooks or runs only, a value shared where it should be unique, an id that never matches a `subagentStart`), the verdict stays **OPEN**. | REFUTED, or OPEN if ambiguous | `unknown` |

Rules for classification:

- **Parent identity is not current-subagent identity.** `parent_conversation_id`, or the
  parent's `conversation_id` appearing on a tool hook, must never be reported as EXACT. It
  can at most produce PARENT_ONLY. `parent_tool_call_id` is not that field: treat it as an
  unclassified deterministic-link candidate until this row's concurrent runs verify it.
- If several fields are present, the outcome is the strongest level that holds in 100% of
  valid runs; a field that is present only part of the time counts as absent for that level
  (so the outcome drops, usually to UNKNOWN) and its rate is recorded.
- If role and parent are both present but no instance id, the outcome is ROLE_ONLY; note
  that the parent field was also present.
- A per-subagent unique value that never equals any `subagentStart.subagent_id` cannot be
  linked to a start: classify UNKNOWN (ambiguous, so the verdict stays OPEN) and note
  "unlinked discriminator".
- Any other id-like key whose meaning the docs do not give is a *candidate*: record it, never
  promote it automatically, and classify it by hand with the evidence below.
- The `spike/analyze.py` Q1 output is a **hint requiring manual classification** per this
  row. It reports four separate buckets: `direct_current_identity`, `role_only_identity`,
  `parent_only_identity` and `unclassified_identity_candidates`. `parent_conversation_id`
  can only ever land in `parent_only_identity`. `parent_tool_call_id` is an unclassified
  deterministic-link candidate (not EXACT, not parent-only) until R8.1/R8.2 verify it.
  Its overall verdict follows this mapping (CONFIRMED only from `direct_current_identity`,
  PARTIAL for role-only, REFUTED for parent-only or nothing, OPEN when only unclassified
  candidates exist) but it does not replace the hand classification; keep its raw outputs
  (`tool_hook_keys_with_agent_identity`, `tool_conversation_id_relation`, and the
  linkage evidence structures — observed / comparable / matches / mismatches /
  unavailable / collisions — for Task / `parent_tool_call_id` / stop-id /
  child-conversation). Missing fields are unavailable, never a 0-match refutation.
  `session_id` is session-level correlation, not a Q1 identity candidate. Q1 and Q2
  remain **OPEN**. One sequential Cursor 3.22.7 observation is UNVERIFIED and does
  not fill this row: it saw optional `subagent_id` and `child_conversation_id` on
  `subagentStop` (not guaranteed) and inner hooks using a child `conversation_id`.
  That first capture also dropped scalar `parent_tool_call_id` and
  `child_conversation_id` at the hook. Copy the updated `capture_hook.py`, start a
  **fresh labeled** capture, and do not append formal row-8 evidence to the older
  jsonl.

- **Row-8 readiness gate** (`analyze.py`, not a Q1 verdict). Formal R8.1 / R8.2
  concurrent classification starts only when the analyzer prints
  `ROW 8 READINESS: READY: required parallel/background lifecycle observed with matched start/stop`.
  Required for READY: overlapping subagent windows **or** `is_parallel_worker=true`
  **or** Task `run_in_background=true`, **and** matched start/stop for those
  parallel instances. If starts exist but stops are missing, or background flags
  are missing and there is no overlap, the analyzer prints
  `ROW 8 READINESS: BLOCKED/OPEN: required parallel/background lifecycle not observed; do not infer a Q1 verdict`.
  The gate never prints `FAIL` and never classifies Q1. Q1 and Q2 remain **OPEN**
  until a human classifies after READY captures.

- **Cursor 3.22.7 Linux observation (not a verdict; not a row-8 result).** A later
  sanitized capture (raw files remain private and outside this repository) showed:
  two-agent attempts repeatedly produced `subagentStart=2`, `subagentStop=0`,
  `is_parallel_worker=true` count=0, `overlapping_subagent_windows=0`, Task
  `run_in_background` missing=2; `parent_tool_call_id` matched every comparable
  inner event (45 comparable, 45 matches, 0 mismatches, 0 collisions). After the
  custom agent was set to `is_background: true`, Cursor was fully reloaded, and a
  fresh chat ran `/cf-writer`, a one-agent probe still had Task
  `run_in_background` missing=1. Formal repeated parallel classification has
  **not** run. Treat readiness as `BLOCKED/OPEN`. Do not start R8.1 / R8.2 on
  this observation, and do not infer that Cursor 3.22.7 on Linux can or cannot
  run parallel subagents beyond what those counts show.

- Procedure: README 2 and 3, extended to three run types, each with its own label.
  - R8.1: two concurrent subagents of the same type (`cf-writer` twice, README 3), 5 runs.
  - R8.2: two concurrent subagents of different types (`cf-reviewer` and `cf-writer`), 5 runs.
  - R8.3: baseline, the same agents one at a time (3 runs), plus one built-in `explore`
    subagent. Sequential windows are clean, so they give per-instance ground truth.
- Ground truth must not come from the hook data under test. Use the Cursor task cards (which
  subagent did what), a distinct target file per subagent, and per-subagent tool-call counts:
  ask the subagents for clearly different numbers of tool calls (for example 3 and 6). The
  `tool_call_count` on each `subagentStop` and the count of tool hooks per candidate field
  value must then agree.
- For each hook name (`preToolUse`, `postToolUse`, `postToolUseFailure`, and in the
  diagnostic set `beforeShellExecution`, `afterShellExecution`, `afterFileEdit`) compare the
  key set and ids of tool hooks inside subagent windows with those of main-agent tool hooks
  in the same conversation. Record the field(s), their presence rate, whether the value is
  distinct between the two concurrent subagents, whether it equals a `subagent_id`, and the
  agreement with the ground-truth counts.
- Also record, as separate sub-results: whether `subagentStop` carries any instance id equal
  to a start's `subagent_id` (needed for ADR 0010 pairing preference 1); whether tool-hook
  `conversation_id` equals the parent's.
- Pass (CONFIRMED, hypothesis "tool hooks identify the current subagent instance"): EXACT for
  every tool hook name tested, in all valid runs of R8.1 and R8.2 (zero mismatches against
  ground truth). Overall PARTIAL: at least one hook name is EXACT or ROLE_ONLY but the
  overall result is not CONFIRMED (list each hook name with its outcome; attribution is then
  decided per hook name). Overall REFUTED: every hook name is PARENT_ONLY or UNKNOWN with
  no ambiguity. Overall OPEN: ambiguity remains and no hook name is better than UNKNOWN. In
  every case record the per-hook outcomes. Fixtures: `tests/fixtures/cursor/subagent/` (row
  16 review).

What each outcome means for the ADRs (all consequences are OPEN until a result exists):

| Outcome | ADR 0003 attribution (`exact`, `inferred`, `unknown`) | ADR 0010 reducer and ADR 0002 |
| --- | --- | --- |
| EXACT | tool events may be `exact` with `agent_instance_id` and `agent_id` `role#instance` | the unattributed `main` accumulation shrinks; lanes can rest on observed activity per instance; writer = instance id becomes viable (topology T1, row 7); stop-to-start pairing still needs an id on `subagentStop` |
| ROLE_ONLY | `inferred`, never `exact` (owner decision 2026-10-04; ADR 0003 section 2 now says so): with concurrent same-type subagents a role claim cannot name the instance, so it is never displayed or exported as instance attribution | tool events attach to a role at most, never to an instance entry; writer stays `main` (topology T2 matters); pairing unchanged (role plus start time against `stop_ts - duration_ms`, preference 2) |
| PARENT_ONLY | `unknown` for the current subagent; never `exact`. The parent id only groups under the parent session, which `session_id` already does | tool events accumulate on `main` with `attribution: unknown`; temporal attribution (`inferred`) is not emitted in v0.1 |
| UNKNOWN | `unknown` | as PARENT_ONLY; per-agent cards show lifecycle only (`lifecycle_only` basis). Worktree or `workspace_roots` identity could only ever be a heuristic (`inferred`, ADR 0011 tier 2), never `exact`, and only if isolation is honoured |

Result table, per hook name (all cells OPEN; fill with one of the four outcomes):

| Hook | R8.1 same type, concurrent | R8.2 different types, concurrent | R8.3 sequential baseline |
| --- | --- | --- | --- |
| `preToolUse` | OPEN | OPEN | OPEN |
| `postToolUse` | OPEN | OPEN | OPEN |
| `postToolUseFailure` | OPEN | OPEN | OPEN |
| diagnostic shell and edit hooks | OPEN | OPEN | OPEN |

- Artifacts: `tool_hook_keys_with_agent_identity`, `tool_conversation_id_relation`, the hand
  classification table above, the ground-truth comparison; fixtures as above.
- Can change: ADR 0003 attribution and field map, ADR 0010 (lanes, pairing), ADR 0002 writer
  naming, ADR 0012 owner mapping, ADR 0011 (what counts as tier 2), the TUI per-agent view,
  and the per-role story in v0.2. (The ADR 0001 Q1 wording that said "names the subagent or
  its parent" was replaced on 2026-10-04 by the current-instance question above.)
- Result record: OPEN; date: -; Cursor version / OS / surface: Cursor 3.22.7 /
  Linux observation recorded above is **not** this result; evidence path: - (raw
  captures stay outside the repo); reviewer sign-off: -; ADRs affected: 0001 Q1,
  0002, 0003, 0010, 0011, 0012. Formal repeated parallel classification has not
  run. Q1 stays OPEN.

### 9. Custom `.cursor/agents` `subagent_type` naming (Q2)

Per docs the `subagent_type` examples are `generalPurpose`, `explore` and `shell`; custom
agents are not mentioned in the hooks reference, and a subagent file's `name` defaults to its
filename.

- Procedure: README 2 with `cf-reviewer` and `cf-writer`, plus `/cf-reviewer review README.md`.
  Add one more scratch agent by hand (not under `spike/`) whose filename differs from its
  `name`, for example file `cf-note-taker.md` with `name: cf-scribe`, so that the value can be
  told apart: filename, frontmatter `name`, or a fixed `generalPurpose`. Invoke each by
  `/<name>` and by prose, 3 times each, and record which invocation names work.
- Matcher probe without changing the kit: in the scratch `hooks.json` add a second
  `subagentStart` entry with the same command plus `"matcher": "cf-scribe"`. Count records per
  start: 2 records (different pids) means the matcher matched, 1 means it did not. Repeat with
  a matcher of the filename form and of `cf-reviewer`.
- Artifacts: `types_seen`, `non_builtin_types`; same fixtures directory as row 8.
- Pass: the value for each custom agent is recorded verbatim for `subagentStart` and
  `subagentStop` and is the same on both, and the matcher result is recorded.
- Fail: it is `generalPurpose` or another fixed value for custom agents: the role mapping must
  come from elsewhere.
- Can change: `hook_normalize` role mapping, ADR 0003 (`agent_role`), ADR 0012, the kit's
  roster file names.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; ADRs affected: 0001 Q2, 0003, 0012.

### 10. `generation_id` and `Task` linkage (secondary questions)

Per docs `generation_id` is a base field "that changes with every user message", while
`conversation_id` is stable across turns. Per docs `subagentStart.tool_call_id` is the "ID of
the tool call that triggered the subagent"; whether that equals the `Task` call's
`tool_use_id` is unverified (ADR 0001 section B, ADR 0003 and ADR 0010 candidate link).

**Design invariant.** `generation_id` must never become a primary identity key: not an event
id, not an agent instance id, not a session key, not a join key between stores. At most it is
a grouping or correlation *hint* for the events of one user turn, and every consumer must
work correctly when it is absent or wrong. The ADR 0003 field map already keeps it as a plain
carried field; this row decides whether even the hint is safe.

- Procedure: README 2 and 3, plus one dedicated multi-turn session (label `ide-gen-r1`, run 3
  times): in one chat send three user messages, each causing at least two tool calls; run a
  foreground subagent in message 2 and a parallel pair in message 3; abort one turn and then
  send another message; open a second and a third conversation in the same repo, and one in a
  worktree (rows 5 and 6).
- Criteria for `generation_id` (every count is over the capture; all results OPEN):

  | ID | Property | Pass | Refute |
  | --- | --- | --- | --- |
  | G1 | Stable across tool calls within a turn | all main-agent hook records between two user messages share one value, in every turn (at least 9 turns) | any turn with two or more values |
  | G2 | Changes per user message | consecutive user messages in a conversation (including after the aborted turn) give different values, constant within each turn, for at least 6 transitions | a new user message reuses the previous value, or the value changes mid-turn |
  | G3 | Relation to subagent runs | recorded, for `subagentStart`, inner tool hooks and `subagentStop`, as one of: equal to the parent turn's value, a distinct value per subagent, or absent; the same relation in every run | the relation changes between runs or within a run |
  | G4 | Uniqueness across conversations | no value occurs in two different conversations (at least 3, one in a worktree) and none is reused by another turn | at least one collision |
  | G5 | Presence on hooks | present, non-null and ID-shaped on every record of the nine registered hooks (and the diagnostic set) | any hook name below 100% presence, or a null value |
  | G6 | Turn boundary hooks | `stop` and `preCompact` carry the same value as the tool hooks of their turn in 100% of turns; `sessionStart` and `sessionEnd` values are recorded | `stop` differs from its turn's tool hooks |

- Evidence that would refute using `generation_id` even as a grouping key for the events of
  a user turn: any G1, G2, G4, G5 or G6 failure (events fall out of, or merge into, groups);
  a value that is not ID-shaped, so it cannot be stored; or values shared across worktrees
  or sessions (G4). G3 equal to the parent's value for concurrent subagents does not refute
  turn grouping, but it proves the value cannot separate agents and must not feed
  attribution (row 8).
- Criteria for `Task` linkage and session ids:

  | ID | Property | Pass | Refute |
  | --- | --- | --- | --- |
  | L1 | `Task` `tool_use_id` equals `subagentStart.tool_call_id` | for at least 10 `Task` calls (at least 5 in parallel pairs) each `preToolUse` (`Task`) id equals the `tool_call_id` of exactly one start in the conversation, and no `tool_call_id` matches two calls (`analyze.py` count equals the `Task` call count) | any `Task` call without a matching start, or one id matching two starts |
  | L2 | The matching `postToolUse` (`Task`) carries the same id | 100% | any mismatch |
  | L3 | Subagents have their own `sessionStart` and `sessionEnd` | recorded per subagent (count, and whether `session_id` differs from the parent's); informational | not applicable (a recorded absence is a result) |
  | L4 | `sessionStart.session_id` equals `conversation_id` | 100% | any mismatch |
  | L5 | `subagentStart.parent_conversation_id` equals the parent's `conversation_id` | 100% | any mismatch |

- What the results mean: L1 pass makes the `spawn_link` in ADR 0010 reliable for linking a
  start to its `Task` call, but it still does not pair `subagentStop` (no id on stop); L1
  refuted drops the link. L3 present means subagents could create extra `session.started`
  events in ADR 0003's mapping, which the reducer must not count as new sessions. L4 failure
  invalidates the `conversation_id` to `session_id` mapping for `sessionStart`.
- Artifacts: the capture, the `analyze.py` output for the secondary questions, a table of
  distinct `generation_id` values per turn (values replaced by letters in notes).
- Can change: ADR 0003 (`inferred_*` methods, field map), ADR 0010 (`spawn_link`, stop
  pairing, session counting), ADR 0001 section B.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; ADRs affected: 0001, 0003, 0010.

### 11. Permission-hook reply shape (release gate)

Question: which hook outputs and failure modes let a permission hook's action proceed, and
which block it? ADR 0008 and ADR 0007 rely on `{"permission":"allow"}` and on exit 0 being
safe; this row checks that, and checks what a broken hook (for example a missing binary) does.

Docs citations (per docs, as recorded in ADR 0001 A2 and A3; none is verified here):

- Permission hooks are those where invalid JSON or a schema-mismatching response blocks the
  action: `beforeShellExecution`, `beforeMCPExecution`, `beforeReadFile`,
  `beforeTabFileRead`, `subagentStart`, `preToolUse`.
- Exit 0: the JSON output is used. Exit 2: blocks (same as `deny`). Any other exit code
  (crash, timeout): fail open, the action proceeds.
- `failClosed: true`: crash, timeout, non-zero exit and empty output block the action.
  Permission hooks block on invalid JSON even when `failClosed` is false.
- ADR 0001 A3 notes that printing `{}` from a permission hook "is a schema risk the docs
  imply will block". The docs do not say what empty output does for a permission hook with
  `failClosed` false.
- Merge across sources: deny beats ask beats allow, so a user-, team- or enterprise-level
  hook that denies would mask an allow.

Hooks under test: `preToolUse` and `subagentStart` (the product permission hooks, ADR 0007)
and `beforeShellExecution` (**diagnostic only**: ADR 0007 does not register it).

Setup (throwaway tooling outside the repository, argv lists and no network): a scratch
stub script that takes a case id, appends one line `case-id timestamp` to a scratch marker
file (so you can tell whether the hook ran), and then emits the case's reply. Narrow each
entry with a matcher so a blocking case cannot lock the scratch session: `preToolUse` with
matcher `Read` and a scratch `probe.txt` containing the made-up string `CF-PROBE-OK`;
`subagentStart` with the matcher for a scratch `cf-probe` subagent (`readonly: true`);
`beforeShellExecution` with a matcher for the exact text `echo cf-probe-<case>`. Verify the
matcher itself first with case C1 (row 9 probes matchers on `subagentStart`).

Table 11A: cases and expectations per docs (the expectations are claims to test, not facts):

| Case | Reply | Expected, `failClosed` false | Expected, `failClosed` true |
| --- | --- | --- | --- |
| C1 | exit 0, `{"permission":"allow"}` | proceeds | proceeds |
| C2 | exit 0, `{}` | docs imply it may block (schema risk); not stated | same |
| C3 | exit 0, empty output | not stated | blocks |
| C4 | exit 0, invalid JSON (`not json`) | blocks | blocks |
| C5 | exit 1, no output | proceeds | blocks |
| C6 | exit 2, no output | blocks | blocks |
| C7 | exit 0 after exceeding the hook `timeout` (set to 1 second in the scratch file) | proceeds | blocks |
| C8 | exit 0, `{"permission":"allow"}` followed by a non-JSON line (debug noise) | not stated | not stated |
| C9 | hook command is a non-existent executable (the "missing binary" case) | proceeds (non-zero exit) | blocks |

Table 11B: observations (all OPEN). One grid per case; one cell per hook and `failClosed`
setting; record `proceeded`, `blocked`, or `other` plus the evidence in the cell:

| Case | `preToolUse` false | `preToolUse` true | `subagentStart` false | `subagentStart` true | `beforeShellExecution` false (diag.) | `beforeShellExecution` true (diag.) |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| C2 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| C3 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| C4 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| C5 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| C6 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| C7 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| C8 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| C9 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |

What to record per cell: whether the marker line appeared (the hook ran); whether the
action took effect (the agent read `CF-PROBE-OK`, the subagent started, the shell command
output appears in the Cursor transcript); any message or error shown in the UI; any Cursor
hook log entry. Repetitions: C1 and C9 for the two product hooks need N=3; every other cell
N=1, repeated 3 times if it diverges from the docs expectation.

- Artifacts: the observation grid, the exact stub reply per case, and one sanitized fixture
  of the C1 reply and Cursor's behaviour for each product hook.
- Pass (release gate): C1 proceeds for `preToolUse` and `subagentStart` with `failClosed`
  false and true, in 3 of 3 runs; C5, C7 and C9 proceed with `failClosed` false (so a
  missing or slow binary does not block users); every other cell is recorded.
- Refute: C1 blocks or errors for either product hook (the fail-open reply is wrong; do not
  ship); or any of C5, C7, C9 blocks with `failClosed` false (the "missing binary fails
  open" argument in ADR 0008 is false). A cell that differs from Table 11A is recorded as
  DIVERGES and the cited docs line is corrected in ADR 0001 A2 or A3. If C2 proceeds, the
  AGENTS.md statement about `{}` and permission hooks is stricter than reality (a doc fix,
  not a behaviour change: the code keeps printing the allow reply).
- Safety notes: scratch repository only; harmless actions only (`echo`, a Read of a scratch
  file, a read-only scratch subagent); never test `deny` or `ask` replies on real commands;
  narrow matchers before enabling any `failClosed: true` entry and remove those entries as
  soon as the cell is done; keep an out-of-band terminal to edit the scratch hooks file;
  check no user-, team- or enterprise-level hook is present that could mask the result
  (`doctor` shows what is readable on disk); `failClosed` is a test setting here and must
  not appear in the product configuration (ADR 0008).
- Can change: ADR 0001, ADR 0007 and ADR 0008 (fail-open policy and reply table),
  `hook_policy.fail_open_response`, and the AGENTS.md reply wording.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; ADRs affected: 0001, 0007, 0008.

### 12. `ask` on permission hooks

- Procedure: reuse the row 11 stub and narrowed matchers with an `ask` reply, once each for
  `preToolUse` and `subagentStart`, and for `beforeShellExecution` (diagnostic: ADR 0007
  drops it). The README has no step for this.
- Docs expectation (ADR 0001 A2, not verified): `preToolUse` accepts `ask` but does not
  enforce it; `subagentStart` does not support `ask` and treats it as `deny`;
  `beforeShellExecution` documents `allow | deny | ask`.
- Pass (informational): per hook, whether a prompt appears and whether the action proceeds
  is recorded once. Results: `preToolUse` OPEN; `subagentStart` OPEN;
  `beforeShellExecution` OPEN.
- Safety notes: as row 11; use the harmless actions only.
- Can change: ADR 0008 only (v0.2 Guard design). No effect on v0.1 support.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; ADRs affected: 0008.

### 13. Hook latency (Q6): hook process outside Cursor (A) and end-to-end (B)

Two different quantities that the earlier plan mixed. Only the Linux steady-state latency of
our own capture hook has ever been measured, outside Cursor (ADR 0001 section C; the product
hook measurement in [hook-latency](hook-latency.md) is also Linux and also outside Cursor).

**Terminology (owner decision 2026-10-04; full text in
[ADR 0001 section D](adr/0001-cursor-capabilities.md)).** This row uses exactly these four
terms and no "warm", "cold" or "cold start" without them:

- **Steady-state:** a fresh process per call with the OS/page cache warm.
- **First-run:** a fresh process with a cold or partially cold cache.
- **Hook-internal:** time measured after the process has started (the capture's own
  `latency_ms`).
- **End-to-end:** the paired hooks-on versus hooks-off user-visible overhead inside Cursor.

The earlier wording conflict ("p95 < 60 ms cold" in `hook-latency.md` versus "under 60 ms
warm" in ADR 0001) is **resolved**: the target is steady-state p95 <= 60 ms, measured as
process wall time **including interpreter startup**, which is how `hook-latency.md` already
measures it. It is not a hook-internal budget.

#### 13A. Hook process latency outside Cursor (steady-state and first-run)

What it measures: the wall time of one hook process (spawn, interpreter startup, imports,
repo discovery, normalisation, spool append), outside Cursor, on each OS claimed in
[platform-support](platform-support.md). It also records hook-internal time (from the
capture's own `latency_ms`) as an informational column.

- **Steady-state** is what `scripts/bench_hook.py` measures: repeated fresh-process samples
  with the OS file cache populated (it discards warm-up samples). **First-run** is the first
  call after the file cache for the interpreter and the package has been dropped, or after the
  machine has been idle or rebooted. Cache-drop methods differ by OS (Linux needs root, for
  example in a throwaway VM; macOS has `purge`; Windows has no simple equivalent, so a reboot
  or the first run after boot). If a first-run state cannot be produced on an OS, record
  "first-run not measured" there; do not extrapolate.
- Procedure: `python scripts/bench_hook.py -n 100` per hook name and per OS for the
  steady-state numbers (the existing tool, run by hand); for first-run, at least 20 samples,
  each after a cache drop. Use the exact command line that `cursorfleet init` would write into
  the hook entry, not only the console script. Record the interpreter version, installation
  method and whether antivirus scanning is on. Add the Windows check that
  `python .cursor/hooks/capture_hook.py <event>` works from Cursor's shell. Record `timeout`
  behaviour: is the hook killed at the limit and what does Cursor log.
- Report per OS, hook name, and steady-state or first-run: sample size, p50, p95 and max in
  milliseconds. For fewer than 100 samples label p95 as indicative (it is near the max);
  never report a p95 without the sample size.
- Target: **steady-state p95 <= 60 ms process wall time, including interpreter startup**
  ([hook-latency](hook-latency.md)). First-run has no target in v0.1: it is reported and not
  judged (a gap, recorded in [follow-ups](follow-ups.md)). Hook-internal time has no target.
- Pass: steady-state p95 <= 60 ms for every hook name of the product set, on every OS the
  docs claim. Refute: any steady-state p95 above 60 ms, or an OS claimed without a
  measurement; then that OS is not claimed, or the hot path is slimmed, or the target in
  `hook-latency.md` changes (an owner decision).

Table 13A (all OPEN; one row per OS and state):

| OS | State | Samples | p50 ms | p95 ms | max ms | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Linux | steady-state | OPEN | OPEN | OPEN | OPEN | OPEN |
| Linux | first-run | OPEN | OPEN | OPEN | OPEN | OPEN |
| macOS | steady-state | OPEN | OPEN | OPEN | OPEN | OPEN |
| macOS | first-run | OPEN | OPEN | OPEN | OPEN | OPEN |
| Windows | steady-state | OPEN | OPEN | OPEN | OPEN | OPEN |
| Windows | first-run | OPEN | OPEN | OPEN | OPEN | OPEN |

#### 13B. End-to-end overhead inside Cursor (release contract)

What it measures: the extra time a user waits for a Cursor action because hooks are
registered, including Cursor's own spawn, stdin delivery and reply handling. This is not
the same as 13A and can be much larger or smaller.

- **Release contract (owner decision 2026-10-04; replaces the earlier OWNER DECISION
  placeholder for the tolerance).** At least **3 batches of 30 paired hooks-on/hooks-off
  calls** per OS and surface (at least 90 pairs), each batch run on a fresh Cursor session
  with the Cursor version recorded.
  - *Pair:* the same scripted action once with hooks registered (C1) and once without (C0),
    adjacent in time, with the order alternated between pairs (ABBA) so drift cancels.
    A pair is one tool call when per-call times are available; otherwise one single-action
    headless run per side.
  - *Metric:* the **paired delta** `delta = T(hooks-on) - T(hooks-off)` for each pair, in
    ms. Negative deltas are kept, not clipped. Percentiles use the nearest-rank method.
  - *Aggregation:* pool all pairs from all batches and compute the median and p95 of the
    pooled deltas. Also compute each batch's median and p95. A batch that **individually
    FAILs** (by the table below) makes the overall verdict FAIL; otherwise the overall
    verdict is the pooled verdict. (A 30-pair p95 is close to the maximum, so per-batch
    figures are judged only against FAIL.)

  | Verdict | Condition on the pooled paired delta |
  | --- | --- |
  | PASS | median <= 100 ms and p95 <= 200 ms |
  | PARTIAL | not PASS, with median <= 150 ms and p95 <= 300 ms |
  | FAIL | median > 150 ms, or p95 > 300 ms, or any hook-induced failure or timeout |

  A *hook-induced failure or timeout* is any hooks-on call that fails, hangs, is blocked or
  is cut off by a hook timeout where its hooks-off partner is not. FAIL means the OS or
  surface is not claimed (or the hot path is slimmed and the run repeated, or the owner
  records a new decision). PARTIAL permits a claim only with the measured numbers
  published. This is a release gate ([release checklist](release-checklist.md)).
- Scripted task: fixed prompt for a scratch repo that triggers a known sequence (for
  example 10 sequential `Read` calls of scratch files, then 10 `echo` shell calls). Use
  headless `agent -p` (row 3) with `--output-format stream-json` where available so the
  event timestamps, if the stream carries them, give per-tool-call times; otherwise use
  single-action runs per the pair definition above.
- Conditions (interleaved, not run in blocks):
  - **C0**: no hooks file (hooks-off baseline).
  - **C1**: the product hook set (nine hooks), hooks-on. The contract compares C1 with C0.
  - **C0b**: A/A control, a second baseline run, to measure the noise floor. Diagnostic only;
    it does not enter the verdict, but a C1 delta smaller than the A/A spread is reported as
    "not detectable at this N" next to the verdict.
  - **C2**: a no-op hook that exits at once with the right reply, on the same events, to
    separate Cursor's hook mechanism from our code. Diagnostic only.
- Blocking versus non-blocking: for each hook name, register a stub that waits a fixed
  delay D (for example 500 ms and 2 s) before replying, one hook name at a time. If the
  action's per-call time grows by about D, Cursor waited for that hook; if it does not, the
  hook is non-blocking. Record this per hook name (the open question in `questions.md` Q6 is
  `postToolUse` and `afterFileEdit`). The stub is throwaway tooling outside the repository.
  Diagnostic only; not part of the verdict.
- Parallel hooks: register k = 1, 3 and 5 identical stubs (each waiting D) on one event. If
  the added time stays near D, they run in parallel; near k times D, sequentially. Record
  per hook name; ADR 0007's hook count and the sum over a tool call depend on this.
- Report per OS and surface: per batch and pooled N, median, p95 and max of the paired
  delta, the verdict, and the A/A spread.

Table 13B (all OPEN; one row per OS, surface and batch, plus a pooled row):

| OS | Surface | Batch | Pairs | Median delta ms | p95 delta ms | max delta ms | Verdict | A/A spread |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Linux | IDE | 1 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| Linux | IDE | 2 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| Linux | IDE | 3 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| Linux | IDE | pooled | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| macOS | IDE | pooled | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| Windows | IDE | pooled | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |

(Repeat the batch rows for macOS, Windows and any other surface claimed. C2 results are kept
as a separate diagnostic table with the evidence.)

Table 13C: blocking and parallel behaviour (record `waits`, `does not wait`, or `unknown`;
all OPEN):

| Hook | Blocks the action? | k=3 parallel or sequential? |
| --- | --- | --- |
| `preToolUse` | OPEN | OPEN |
| `postToolUse` | OPEN | OPEN |
| `postToolUseFailure` | OPEN | OPEN |
| `subagentStart` | OPEN | OPEN |
| `subagentStop` | OPEN | OPEN |
| `preCompact` | OPEN | OPEN |
| `stop` | OPEN | OPEN |
| `sessionStart` (fire-and-forget per docs) | OPEN | OPEN |
| `sessionEnd` | OPEN | OPEN |

- Artifacts: `spike/results/latency-<os>.json` for 13A (the repo location is a result
  file, not raw capture); 13B and 13C timing tables kept with the evidence path; the
  capture's `latency_ms` and `stdin_read_ms` from live runs (hint at how late Cursor writes
  stdin).
- Can change: ADR 0001 (Q6), [platform-support](platform-support.md),
  [hook-latency](hook-latency.md), ADR 0007 (hook count if latency or sequencing is bad),
  the latency terminology and contract of ADR 0001 section D.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; ADRs affected: 0001 Q6, 0007.

### 14. Instruction loading, tested with behavioural canaries

Question: do the files `cursorfleet init` writes (the `alwaysApply` core rule, the scoped
handoff rule, the skills, the subagent files and the nested `AGENTS.md`; see
[kit](kit.md)) actually reach the agent that needs them: the main agent, subagents, an agent
in a worktree, and a headless run?

**No self-reporting.** Asking an agent "what do your instructions say?" proves nothing: it
can guess, echo the question, or hallucinate. Instead each instruction source contains an
instruction whose compliance leaves a deterministic mark in a file, and a script (throwaway
tooling outside the repository) inspects the files. The agent is never asked about its
instructions.

Docs facts used to design the controls (per docs, unverified here): rules must be `.mdc`
with frontmatter, and a plain `.md` in `.cursor/rules` is ignored; `alwaysApply`, `globs`
and `description` decide when a rule applies; nested `AGENTS.md` files are supported; skills
live in `.cursor/skills/<name>/SKILL.md` and `disable-model-invocation` stops automatic use;
a skill can be scoped with `paths`; subagent frontmatter has `name`, `description`, `model`,
`readonly` and `is_background`.

Canary design:

- Every source gets its own **synthetic canary token**, generated fresh for each trial by the
  harness (for example `CF-CANARY-<source>-<random hex>`) and written into the instruction
  files before the trial. A token cannot be remembered from an earlier chat or guessed.
- Each source carries one instruction of the form "when you create a file here, put this exact
  token on the first line", plus a scope. The user prompt for the trial never mentions
  tokens, rules or instructions; it only asks for ordinary small files.
- An **instruction-following control** is part of every trial: the user prompt itself asks
  for a different, prompt-level token (`CF-PROMPT-<hex>`) on every file. A trial in which the
  prompt token is missing from a created file is discarded, because the agent did not follow
  instructions at all.
- A trial is **valid** only if the files were created (check the `afterFileEdit` or
  `postToolUse` Write records in the capture, not the agent's claim). Otherwise discard
  and redo, as in the ground rules.
- Record the model, Cursor version, OS and surface for every trial; behaviour differs across
  models.

Sources, scopes and what each trial type checks (the oracle is a file search for the token):

| ID | Source | Scope and trigger | Expected per docs | Oracle |
| --- | --- | --- | --- | --- |
| S1 | root `AGENTS.md` | all files | applied | token in every created file |
| S2 | nested `AGENTS.md` in `sub/` | files created under `sub/` | applied under `sub/` only | token in `sub/` files, absent elsewhere |
| S3 | `.mdc` rule, `alwaysApply: true` | all files | applied | token in every created file |
| S4 | `.mdc` rule, `globs: sub/**/*.py` | creating a matching file | applied to matching files only | token in `sub/*.py`, absent in `other/*.md` |
| S5 | `.mdc` rule with only a `description` | a task that matches the description | agent-requested, model decides | token present when the task matches |
| S6 | skill with a `description`, auto-invocable | a task matching the description | may be used | token in the output file |
| S7 | custom subagent `cf-canary-rw` | invoked by name | runs its own prompt | token in its output file |
| S8 | rules in a worktree checkout | agent working in a worktree | same files, from that checkout | as S1 to S4 |

Negative controls (each must show **zero** occurrences; a hit voids that source's result
until explained):

| ID | Control | Why it must not apply |
| --- | --- | --- |
| N1 | `.mdc` rule with `alwaysApply: false`, no `globs`, no `description` | nothing selects it |
| N2 | plain `.md` file in `.cursor/rules/` | per docs, rules must be `.mdc` |
| N3 | `globs` rule evaluated on a non-matching file (`other/*.md`) | outside its scope |
| N4 | skill with `disable-model-invocation: true` and a matching task | not auto-invocable |
| N5 | skill whose description does not match the task | unrelated |
| N6 | nested `AGENTS.md` token in a file created outside `sub/` | out of scope |
| N7 | `readonly: true` subagent told to write a file | read-only; see below |

Trial types (each uses a fresh chat; a trial type may check several sources at once):

- **Type A, files** (S1 to S5, N1 to N3, N6): "Create `notes/a.txt`, `sub/b.py` and
  `other/c.md`, each with one sentence of text, as the prompt-token rule says." Oracle: token
  matrix per file.
- **Type B, skills** (S6, N4, N5): a prompt that matches only the S6 description (for
  example a made-up "zorblat report" that S6 defines), a second made-up task for N4 and one
  that matches nothing for N5. Oracle: each skill's token in its own output file.
- **Type C, subagents** (S7, N7, and subagent inheritance): invoke `cf-canary-rw` by name,
  then `cf-canary-ro` (`readonly: true`, same body). Oracle: the S7 token file exists;
  the N7 file does **not** exist and the capture has no `afterFileEdit` for it. Also instruct
  the parent not to create files itself and discard the trial if the capture shows a Write
  outside the subagent's start and stop window (single subagent runs only, so the window is
  unambiguous). Then check the subagent's files for the S1 to S4 tokens: that is the
  inheritance result (does a subagent see root and nested `AGENTS.md` and rules?).
- **Type C2, naming**: a subagent whose filename differs from its `name`; invoke it by each
  and record which works and what `subagent_type` the capture shows (row 9).
- **Type D, surfaces**: Type A repeated in a Cursor-managed worktree (S8), in a manual
  worktree, and in headless `agent -p --force` in the scratch repo (rows 3, 5, 6).

Repetitions and thresholds (k = trials with the token, n = valid trials; report k/n for every
cell and the Wilson 95% interval):

| Surface | Required n |
| --- | --- |
| IDE main agent | 10 |
| IDE subagent, worktree, headless | 5 each |

- RELIABLE: k/n at least 0.9 for the surface with the required n (for n=5, k=5).
- UNRELIABLE: 0 < k/n < 0.9. The kit must not depend on this source; the ADR 0006 handoff
  format stays a best-effort claim.
- NOT LOADED: k = 0 with the required n, while the instruction-following control passed.
- Negative control hit (any k above 0): the source result is voided until the leak is
  explained (token echoed from a file the agent read, a wrong scope assumption, or docs
  refuted).
- Pass for the row: every source in the table has a recorded status on every surface it is
  meant to reach, all negative controls show zero, and the status on subagents and worktrees
  is stated separately from the main agent's.
- Refute: a source the kit depends on is NOT LOADED or UNRELIABLE where ADR 0006 or ADR 0012
  assumes it: the artifact format and coordinator flow cannot be relied on; revise the kit
  docs and the generated files.

Result grid (all OPEN; one status each from RELIABLE, UNRELIABLE, NOT LOADED):

| Source | IDE main | IDE subagent | Worktree | Headless |
| --- | --- | --- | --- | --- |
| S1 root `AGENTS.md` | OPEN | OPEN | OPEN | OPEN |
| S2 nested `AGENTS.md` | OPEN | OPEN | OPEN | OPEN |
| S3 `alwaysApply` rule | OPEN | OPEN | OPEN | OPEN |
| S4 `globs` rule | OPEN | OPEN | OPEN | OPEN |
| S5 description-only rule | OPEN | OPEN | OPEN | OPEN |
| S6 skill | OPEN | OPEN | OPEN | OPEN |
| S7 custom subagent | OPEN | - | OPEN | OPEN |
| N1 to N7 (must be 0) | OPEN | OPEN | OPEN | OPEN |

- Artifacts: the per-trial token matrix (token values replaced by their source ids in
  notes), the capture proving each file was created, the model and version per trial.
- Safety: synthetic tokens and files only; scratch repository; no real instructions or
  secrets in the scratch rule files.
- Can change: ADR 0006 (review trigger and the strength of the claim), ADR 0012, ADR 0009
  (what the kit installs), [kit](kit.md), [governance](governance.md).
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; ADRs affected: 0006, 0009, 0012.

### 15. Privacy-boundary release gate

**Release-blocking.** CursorFleet promises never to persist prompts, thinking or response
text, file contents, command output, environment variables, user emails or transcript paths
([privacy](privacy.md), AGENTS.md). Existing security tests plant secrets in synthetic
payloads; this gate repeats the check with planted canaries on every place data can
surface, using payloads from live runs as well as synthetic ones.

Planted canaries (synthetic; token form `CF-CANARY-<class>-<random hex>`, a fresh set per
gate run, stored in a registry file outside the repository with mode `0600`):

| Class | Planted where | Must never appear in |
| --- | --- | --- |
| P | the user prompt text of a live run | any surface below |
| F | the contents of a file the agent reads and writes | any surface |
| D | an edit's old and new strings (diagnostic `afterFileEdit` payload and synthetic payloads) | any surface |
| O | the output of a shell command the agent runs | any surface |
| C | a command-line argument (`--token CF-CANARY-C-...`) | any surface (a keyed hash and a redacted display string, if enabled, are the only allowed traces; the token itself must not remain) |
| E | an environment variable inherited by the hook (`CF_CANARY_E`) | any surface |
| M | `user_email` and `CURSOR_USER_EMAIL` in a synthetic payload | any surface |
| T | `transcript_path` and `agent_transcript_path` values in a synthetic payload | any surface |
| X | an absolute path outside the workspace (`/tmp/CF-CANARY-X-.../f.txt`) | any surface (only `<external>` is allowed) |
| R | an error message in a `postToolUseFailure` payload, and task or summary text in `subagentStart` and `subagentStop` payloads | any surface |
| H | the real account email, home directory path and user name, supplied to the scanner through environment variables and never printed or written | any surface |

The scanner (throwaway tooling outside the repository) looks for each token as raw bytes and
in these forms: JSON-escaped, URL-encoded, base64 (three alignments), hex, UTF-16LE, and
case-folded. It also looks for the unkeyed SHA-256 and MD5 of each token (ADR 0003 allows
only a keyed hash). It prints counts and file paths, never the matched text.

Surfaces scanned (every one, after a live IDE run, a CLI run, and a synthetic payload
replay):

| Surface | What is scanned |
| --- | --- |
| Spool | every file under `<git-common-dir>/cursorfleet/spool/`, including rotated segments, `.capped` markers and torn tails |
| SQLite | `state.sqlite`, its `-wal` and `-shm` files as raw bytes, and a text dump; free pages are covered by the raw scan |
| Runtime directory | everything else under `<git-common-dir>/cursorfleet/` (the `hmac.key` content is not a canary; only its permissions matter) |
| Fixtures | `tests/fixtures/cursor/**` and any candidate fixture, before commit |
| JSON outputs | `status --json`, `replay --json`, `index --json`, `validate --json`, `doctor --json` |
| Text outputs | `doctor`, `status`, `replay` and `events export --sanitized` text and files |
| TUI | the rendered text of every screen and filter state, captured with a Textual `run_test()` pilot (text only) and once from a real terminal |
| Logs and streams | stderr and stdout of hooks and commands, any log file, crash dumps |
| Repository | `git grep` over the scratch repository and this repository, committed config and generated kit files |
| Spike captures | `captures.jsonl` (the kit records key names, types and ids only; a hit is a kit bug) |

Method for validity: before scanning, run the scanner on a positive-control directory that
holds each canary in each encoding; the scanner must find every one (100% detection), or the
gate run is invalid. Also run it on an empty directory (zero hits).

- Pass: **0 occurrences** of any canary, in any encoding, on every surface, and the scanner
  self-test passed. Stored paths are workspace-relative or `<external>`; nothing else.
- Failure: any occurrence is **release-blocking**. Stop, do not publish or share the capture,
  treat it as a security bug (report privately per [SECURITY.md](../SECURITY.md)), purge the
  affected data (row 16), fix the allowlist parser at the boundary, add a regression test,
  regenerate the canaries and rerun the **entire** gate, not only the failing surface.
- When: on the final release configuration, after the live and synthetic runs, and again
  after any change to `hook_normalize`, the sanitizer, the store or the views (add to the
  [release checklist](release-checklist.md)).

Gate record (all OPEN):

| Surface | Occurrences | Scanner self-test | Result |
| --- | --- | --- | --- |
| Spool | OPEN | OPEN | OPEN |
| SQLite (db, WAL, SHM) | OPEN | OPEN | OPEN |
| Runtime directory | OPEN | OPEN | OPEN |
| Fixtures | OPEN | OPEN | OPEN |
| JSON outputs | OPEN | OPEN | OPEN |
| Text outputs and export | OPEN | OPEN | OPEN |
| TUI text | OPEN | OPEN | OPEN |
| Logs and streams | OPEN | OPEN | OPEN |
| Repository | OPEN | OPEN | OPEN |
| Spike captures | OPEN | OPEN | OPEN |

- Artifacts: scanner output (counts and file paths only) kept with the evidence path; never
  the raw captures.
- Can change: ADR 0003 (sanitization), ADR 0004 and ADR 0007 (hook set), ADR 0002
  (retention), [privacy](privacy.md), [threat-model](threat-model.md), the release.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; ADRs affected: 0002, 0003, 0004, 0007.

### 16. Raw-capture permissions, retention and cleanup

Applies to every row. "Raw captures" means anything produced by a live run that has not been
reviewed and reduced to a fixture: the spike's `captures.jsonl`, headless `stream-json`
output (which carries assistant text and tool output, so it is the most sensitive item),
screenshots, Cursor transcripts, scratch `hooks.json` files, stress-test output, scanner
output and the canary registry. The spike kit is designed to record key names, value types,
ids, enums, counters and timings only, but it has never been run, so treat every capture as
possibly sensitive until row 15 has scanned it.

Requirements:

- **Location.** Only in `<git-common-dir>/cursorfleet-spike/` (the kit default, inside
  `.git`, so git never tracks it) or in a dedicated evidence directory outside every
  repository: `$XDG_STATE_HOME/cursorfleet-evidence/<date>/` on Linux and macOS,
  `%LOCALAPPDATA%\cursorfleet-evidence\<date>\` on Windows. If anything must sit inside a
  working tree, list it in `.git/info/exclude` (not a committed `.gitignore`). Never in a
  cloud-synced folder, never attached to an issue or pull request, never pasted.
  Copying or zipping the scratch repository directory also copies `.git`, so delete captures
  first.
- **POSIX permissions.** Run with `umask 077`; directories `0700`, files `0600`. The kit
  creates its capture directory with `0700` and the file with `0600` (see
  `spike/capture_hook.py`); evidence directories rely on the umask. Verify, expecting no
  output:

  ```sh
  find "$EVIDENCE" \( -type d ! -perm 0700 \) -o \( -type f ! -perm 0600 \)
  ```

- **Windows.** The `mode` arguments the kit passes are ignored on Windows. Use a directory
  under `%LOCALAPPDATA%`, remove inherited access and grant only the current user, then
  check the listing shows only that user (plus SYSTEM and Administrators):

  ```bat
  icacls "%EVIDENCE%" /inheritance:r /grant:r "%USERNAME%:(OI)(CI)F"
  icacls "%EVIDENCE%"
  ```

  This procedure is best effort and is itself unverified; record the actual `icacls` output
  in the evidence notes. `cursorfleet doctor` reports what it could verify for its own
  runtime directory, not for evidence directories.
- **Retention limit.** At most **7 days** from creation. Record the deadline in the result
  record. Delete earlier once the reviewer has signed off.
- **Reviewed fixtures only.** Nothing from a raw capture enters the repository except a
  fixture under `tests/fixtures/cursor/` that passed this checklist:
  1. produced from the capture through the allowlist shape only, then read line by line;
  2. no prompts, responses, file contents, command text beyond argv0, output, env values,
     emails, user names, host names, home paths, repository URLs or tokens;
  3. paths workspace-relative or `<external>`; ids replaced with stable fakes;
  4. the row 15 scanner reports 0 occurrences on the candidate file (including class H);
  5. a second reviewer has read it and signed the result record;
  6. committed with a provenance note (Cursor version, OS, date) and no raw content in the
     commit message.
- **Cleanup and verification.** At the end of the run (and at the retention deadline):

  ```sh
  rm -rf "$EVIDENCE" "$(git rev-parse --git-common-dir)/cursorfleet-spike"
  test ! -e "$EVIDENCE" && echo evidence-gone
  find "$HOME" /tmp -xdev \( -path '*cursorfleet-spike*' -o -path '*cursorfleet-evidence*' -o -name 'CF-CANARY*' \) 2>/dev/null
  git status --porcelain
  git log --all --oneline -G 'CF-CANARY-[A-Za-z0-9]+-[0-9a-f]{8,}'
  ```

  Expect `evidence-gone`, then no output from the last three commands (run the last two in
  the scratch repository and in this repository). Also delete the canary registry and the
  scanner output, and check shell history, the trash folder and editor recent-file lists
  for pasted captures.
- **`shred` and `find` caveats.** `shred -u` overwrites in place, which does nothing useful
  on journaling or copy-on-write filesystems (ext4 journals, btrfs, ZFS, APFS), on SSDs with
  wear levelling, or where snapshots and backups exist; `find` only proves names, not
  content. Do not claim secure deletion. The real protections are not recording sensitive
  values in the first place, full-disk encryption, the permissions above and the 7-day
  limit.
- **Sign-off.** The result record template carries a "Raw-capture sign-off" line for every
  row: permissions checked, retention deadline, deletion date and the reviewer. A row's
  result is not final until it is filled in.

- Pass: permissions verified, nothing outside the allowed locations (the `find` checks
  above print nothing), cleanup verified, sign-off recorded. Refute: any capture found in a
  working tree, in a commit, or past 7 days; treat a committed capture as a security
  incident (SECURITY.md) and also run row 15.
- Can change: the spike README cleanup section, [release checklist](release-checklist.md),
  [privacy](privacy.md) (sharing diagnostics).
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; raw-capture sign-off: -; ADRs affected: 0002, 0003.

### 17. Non-git workspace

Question: what happens when Cursor opens a folder that is not a git repository (v0.1
requires git: ADR 0002 says hooks record nothing and exit open, and `doctor` explains)?
Three parts: what Cursor does (unverified); what our hook and read-only commands do
(designed, not live-verified); and the write-command repository-root contract (decided
2026-10-04, **implemented in code**; live verdict remains OPEN).

Cases (scratch folders only; no real project):

| Case | Setup |
| --- | --- |
| 17a | a plain folder with no `.git` anywhere above it |
| 17b | a plain folder created inside another scratch git repository (git, and our file-based `.git` walk, would find the parent) |
| 17c | an ordinary subdirectory of a scratch repository (not a nested repo) |
| 17d | the root of a genuine nested repository, and a subdirectory of that nested repo |
| 17e | the root of a linked worktree |

Part 1, Cursor behaviour (spike kit, which falls back to a temp directory when it finds no
git entry, so no git is needed for it; its capture directory is created `0700`):

- Procedure: open the folder in the IDE with the kit's `hooks.json`; run one short agent
  turn with a Shell and a Read call; repeat once with the CLI (`agent`) and once headless.
  Record whether project hooks fire at all, the `workspace_roots` and `cwd` values (as
  basenames and git kind only), and whether `sessionStart` and `sessionEnd` still arrive.
- Pass (information): the result is recorded for each case and surface. Refute of a design
  assumption: hooks do not fire, or `workspace_roots` is empty, in a way that the docs
  and ADR 0002 do not allow for (record it and update ADR 0002 and
  [platform-support](platform-support.md)).

Part 2, our hook and read-only commands (no Cursor needed; synthetic doc-derived payload
piped to the installed `cursorfleet-hook` in each folder):

| Check | Expected (design intent, unverified) |
| --- | --- |
| hook exit code | 0 |
| hook stdout | `{"permission":"allow"}` for permission hooks, `{}` otherwise |
| files created anywhere | none (no spool, no SQLite, no runtime directory) for 17a |
| `doctor` | explains that a git repository is required; does not crash; exit 1 outside Git |
| `status --json`, `tui` | report "not a git repository" as a problem; do not crash |

For 17b the **hook** expected behaviour is decided (owner, 2026-10-04;
[ADR 0002](adr/0002-storage-layout-and-runtime-directory.md) runtime-inheritance
amendment). **Implemented in code** (`test_runtime_inheritance.py`). **Not empirically
verified.** The result record stays OPEN. `init` from 17b still exits 2 and writes
nothing.

Expected (runtime, from a hook that reaches the folder via user-level hooks or a copied
`hooks.json`):

| Case | Expected |
| --- | --- |
| Ordinary nested non-git dir inside an **initialized** enclosing root (`.cursorfleet/` present at that root) | Inherit that enclosing repository. Events go to its `<git-common-dir>/cursorfleet/`. Paths are stored relative to that root. No nested `.cursorfleet/` and no nested runtime directory are created. |
| Inner `.git` directory/gitfile or submodule | New repository boundary. Does **not** inherit the outer repository. |
| Uninitialized inner repository (inner `.git`, no `.cursorfleet/` at the inner root) | Does **not** fall back to the outer repository. No event; fail open. |
| Missing CursorFleet marker at the detected root | No event; fail open (exit 0, correct reply). |
| External symlink, ambiguous multi-root workspace, or uninitialized root | No event; fail open. |

Resolution used for the expected cases: tool cwd when available, otherwise
`CURSOR_PROJECT_DIR`; realpath-resolve the anchor; nearest Git root; require the
CursorFleet installation/config marker at that root; use that root's git-common-dir and
repository identity. Inheritance is allowed only for an installation that already exists
at the resolved root.

Pass (17b, when later executed): every row of the table holds, including no nested
`.cursorfleet/` or runtime created and paths relative to the inherited root. Refute: the
hook writes to the outer runtime from an inner `.git`/submodule; falls back from an
uninitialized inner repository to the outer; records an event when the marker is missing,
or on an external symlink / ambiguous multi-root / uninitialized root; writes a nested
`.cursorfleet/` or nested runtime; stores paths relative to the nested folder rather than
the inherited root; or `init` from 17b writes anything or exits other than 2.

Part 3, `init` and `uninstall` repository-root preconditions (owner decision 2026-10-04;
[ADR 0009](adr/0009-install-uninstall-ownership.md) amendment; [ADR 0002](adr/0002-storage-layout-and-runtime-directory.md)).
**Implemented in code** (exit 2, no writes). Live Cursor verdict remains OPEN. Do not treat
a synthetic CLI run as a Cursor verification.

| Case | Decided contract |
| --- | --- |
| 17a (non-git) | `init` / `uninstall` exit **2**, change nothing, explain that Git is required. No `--allow-non-git`. |
| 17b / 17c (ordinary subdirectory of another repo) | exit **2**, change nothing, print the detected repository root, tell the user to run there. Never silently modify the parent. |
| 17d nested repository root | valid root: nearest `.git` wins; install into the inner repo only. A subdirectory of the nested repo is 17c with the **inner** root. |
| 17e linked-worktree root | valid root. Runtime stays at `<git-common-dir>/cursorfleet/`. A subdirectory of the worktree is 17c with the worktree root. |

`--dry-run` and `--yes` are judged by the same preconditions: a dry run from a non-root is
exit 2 with no diff. `--path` must itself be a repository root.

The write-command root check is implemented (`workspace_root` exit 2). Follow-ups task 15
is implemented in code: `doctor`/`validate` print the detected root and boundary type
and never write. Live row 17 stays OPEN.

- Pass: 17a part 2 matches every row of the table (exit 0, right reply, nothing written,
  clear `doctor` message); 17b matches every row of the expected table above; part 3 is
  documented in ADR 0002/0009 (init still exit 2 from 17b/17c). Refute: the hook writes
  any file in 17a, exits non-zero, prints a wrong reply, or a command crashes; or any 17b
  refute case above.
- Can change: ADR 0002 (non-git statement and runtime inheritance), ADR 0009, [kit](kit.md),
  [quickstart](quickstart.md), [follow-ups](follow-ups.md) tasks 15 and 16,
  [platform-support](platform-support.md), [architecture](architecture.md) failure table,
  `doctor` messages.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; raw-capture sign-off: -; ADRs affected: 0002, 0009.

### 18. Existing-hooks coexistence and the install round trip

Question: does `cursorfleet init --cursor` leave a user's existing hooks, `AGENTS.md` text and
formatting intact, does `uninstall` restore the tree byte for byte (ADR 0009), and do the
user's hooks and ours behave together inside Cursor? This row **describes the procedure
only**; `init` has not been run for this plan.

Pre-existing states (scratch repository, one per variant, each committed before `init`):

| Variant | `.cursor/hooks.json` | `AGENTS.md` |
| --- | --- | --- |
| V1 | valid, with a user hook on an event we also register (`preToolUse`, with a `matcher`) and one on an event we do not (`afterFileEdit`), an unknown top-level key, tab indentation, CRLF line endings, no trailing newline | existing text, no CursorFleet block |
| V2 | absent | absent |
| V3 | invalid JSON | existing text |
| V4 | valid, already containing the entry `cursorfleet-hook` from a previous install (adoption) | with an existing managed block |
| V5 | valid, with a user hook on `beforeSubmitPrompt` (content-bearing, registered by someone else) | existing text |

Round-trip procedure (planned; run in a scratch repository by a later executor):

```sh
# before: record the state of every file outside .git, and the git status
find . -path ./.git -prune -o -type f -print0 | sort -z | xargs -0 sha256sum > "$EVIDENCE/before.sha"
git status --porcelain > "$EVIDENCE/before.status"
cursorfleet init --cursor --dry-run        # read the diff; nothing is written
cursorfleet init --cursor --yes
cursorfleet validate && cursorfleet doctor
cursorfleet init --cursor --yes            # second run must report "Already up to date"
cursorfleet uninstall --yes
find . -path ./.git -prune -o -type f -print0 | sort -z | xargs -0 sha256sum > "$EVIDENCE/after.sha"
diff "$EVIDENCE/before.sha" "$EVIDENCE/after.sha" && echo round-trip-identical
```

Checks and expectations (design intent per ADR 0009, all unverified):

| Check | Expected |
| --- | --- |
| user hook entries after `init` | present, unmodified, in the original order; our entries added only for the ADR 0007 hook set, with the exact command `cursorfleet-hook`, no `matcher`, no `failClosed` |
| formatting after `init` | indentation, line endings and trailing-newline state of user content preserved |
| `AGENTS.md` | user text outside the managed block untouched |
| `init` twice | the second run is a no-op |
| `uninstall` | tree identical to the "before" state, including `hooks.json` bytes; the directories `init` created are removed |
| V3 | `init` refuses and does not rewrite the file |
| V4 | the identical entry is adopted and survives `uninstall` as it was |
| V5 | `doctor` lists the third-party hook and warns that it is content-bearing; nothing edits it |
| drift | edit a generated file after `init`: `uninstall` reports it, keeps it, exits 1; with `--force` removes it |
| user-level hooks | in a throwaway `HOME` containing a user-level `hooks.json`, `doctor` lists it and does not edit it |

Live coexistence (IDE, scratch repository, harmless actions; separate from the file checks):

- A user stub on `preToolUse` (matcher `Read`, scratch file) that writes a marker line, and
  our hook, both registered for the same event. Record that both ran (marker and capture).
- A user stub that replies `deny` for the same scratch Read, with ours replying
  `{"permission":"allow"}`. Docs say deny beats allow when sources merge, so expect the
  Read to be denied; record what happens. This tests only that our entry does not change
  the outcome, not Cursor's merge rule in general (see rows 11 and 12 for reply shapes).
- Hook order and whether an entry's failure affects the other (use row 11 case C5 on the
  user stub): record, do not assume.

- Pass: every expectation in the table holds for V1 to V5, the round trip prints
  `round-trip-identical`, and the live checks are recorded. Refute: any user byte changes
  after `uninstall`; a user hook is reordered, merged or removed; `init` rewrites invalid
  JSON; a managed entry carries `matcher` or `failClosed`; or our entry changes a user
  hook's outcome. A refute is a bug in the installer (ADR 0009) and blocks the kit release.
- Safety notes: scratch repository only; never run `init` against a real project's
  `hooks.json` for this test; keep an out-of-band terminal; the `deny` stub applies to a
  scratch file only.
- Can change: ADR 0009, ADR 0008 (no `failClosed`), [kit](kit.md), the `doctor` warnings.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; raw-capture sign-off: -; ADRs affected: 0008, 0009.

## Traceability

Question ids Q1 to Q6 are those of [`spike/questions.md`](../spike/questions.md). That file
does not number its nine "secondary questions"; this plan labels them SQ1 to SQ9 in file
order (labels local to this plan):

| Id | Secondary question |
| --- | --- |
| SQ1 | Do tool hooks fire for `Task`, and does its `tool_use_id` equal `subagentStart.tool_call_id`? |
| SQ2 | Is `generation_id` constant across a subagent's work? |
| SQ3 | Does `subagentStart.git_branch` differ for isolated subagents; is `is_parallel_worker` true for parallel runs? |
| SQ4 | Does `sessionStart.session_id` equal `conversation_id`; do subagents get their own `sessionStart` and `sessionEnd`? |
| SQ5 | Are `model`, `model_id` and `model_params` present on every hook? |
| SQ6 | Which `CURSOR_*` environment variables reach hook processes? |
| SQ7 | Does `preCompact` fire in practice, and do its `context_*` counters appear? |
| SQ8 | Is the hook process killed by `timeout`, and what does Cursor log? |
| SQ9 | Windows: does `python .cursor/hooks/capture_hook.py <event>` work from Cursor's shell, and what is the first-run latency? |

| Row | Topic | ADRs | Questions | ADR 0001 matrix row | Follow-up tasks that wait for it |
| --- | --- | --- | --- | --- | --- |
| 1 | Scenario-to-hook matrix, IDE | 0001, 0003, 0007, 0010 | SQ5, SQ6, SQ7 | IDE (desktop), main agent only | follow-ups: rows 1 and 11 |
| 2 | CLI interactive | 0001 | Q3 | CLI interactive `agent` | - |
| 3 | CLI headless, no `--force` and `--force` | 0001, 0003, 0007 | Q3 | CLI headless `agent -p` (one matrix row for both modes) | - |
| 4 | Agents Window | 0001, 0012 | Q3 | Agents Window | - |
| 5 | Cursor-managed worktree | 0001, 0002, 0012 | Q3, Q4, SQ3 | Cursor-managed worktree | follow-ups: rows 5, 6, 7 |
| 6 | Manual worktree | 0002, 0012 | Q4 | Manual worktree | follow-ups: rows 5, 6, 7 |
| 7 | Concurrency (a) real overlap, (b) synthetic stress | 0001, 0002, 0010, 0012 | Q5, SQ3 | Concurrency and parallel subagents (Q5) | follow-ups: rows 5, 6, 7 |
| 8 | Subagent identity | 0001, 0002, 0003, 0010, 0011, 0012 | Q1 | Subagent identity (Q1) | follow-ups: rows 8 and 9; row 8 |
| 9 | Custom `subagent_type` | 0001, 0003, 0012 | Q2 | Custom `subagent_type` naming (Q2) | follow-ups: rows 8 and 9 |
| 10 | `generation_id` and `Task` linkage | 0001, 0003, 0010 | SQ1, SQ2, SQ4 | `Task` linkage and ids | - |
| 11 | Permission-hook reply shape | 0001, 0007, 0008 | none (release gate) | Permission-hook fail-open reply | follow-ups: rows 1 and 11 |
| 12 | `ask` on permission hooks | 0008 | none | `ask` behaviour | - |
| 13 | Latency (A) hook process outside Cursor, (B) end-to-end | 0001, 0007 | Q6, SQ8, SQ9 | Hook latency inside Cursor (Q6) | - |
| 14 | Instruction loading canaries | 0006, 0009, 0012 | none | Rule, skill and nested `AGENTS.md` loading | follow-ups: row 14 |
| 15 | Privacy-boundary release gate | 0002, 0003, 0004, 0007 | none | none yet | - |
| 16 | Raw-capture hygiene | 0002, 0003 | none | none (applies to all) | - |
| 17 | Non-git workspace | 0002 | none | none yet | - |
| 18 | Existing-hooks coexistence and round trip | 0008, 0009 | none | none yet | - |

Rows 15 to 18 have no ADR 0001 matrix row and no follow-up task yet.

## Missing or inconsistent references

Recorded for the owner. Items marked **RESOLVED** were fixed by the architecture-owner
decisions of 2026-10-04 (documentation only; the code and the live results are unchanged).
**Resolving a wording problem does not verify any Cursor behaviour: every result field in
this plan is still OPEN.**

1. **RESOLVED (2026-10-04).** ADR 0001 matrix, Q1 row said the field "names the subagent or
   its parent", while row 8 treated a parent-only field as a refutation. The matrix, ADR 0001
   Q1 and `spike/questions.md` Q1 now ask whether tool hooks identify the *current subagent
   instance* (or link to it deterministically) and use the row 8 mapping: EXACT is CONFIRMED
   (`exact`), ROLE_ONLY is PARTIAL (`inferred`), PARENT_ONLY is REFUTED (`unknown`), UNKNOWN is
   REFUTED or, if ambiguous, OPEN (`unknown`).
2. **RESOLVED (2026-10-04).** "Warm", "cold" and "cold start" were used inconsistently (ADR
   0001 matrix and section C, `hook-latency.md`, `spike/questions.md`, `platform-support.md`,
   `architecture.md`, `product-contract.md`). They are replaced by steady-state, first-run,
   hook-internal and end-to-end (ADR 0001 section D). The per-hook target is steady-state p95
   <= 60 ms process wall time including interpreter startup. Residual wording lives only in the
   throwaway script docstrings `scripts/bench_hook.py` and `spike/bench_latency.py` ("cold
   start"), which were not edited in this documentation-only pass.
3. **RESOLVED (2026-10-04).** ADR 0003 section 2 let a role-only identity be labelled `exact`.
   Role-only is now `inferred`, never `exact`. The earlier temporal-specific label is removed from
   all documentation; the canonical enum is `exact | inferred | unknown`, temporal attribution
   uses `inferred`, and a separate optional `attribution_method` field is noted in ADR 0003 as
   a possible future addition (not implemented). Remaining code differences (reducer keeps the
   strongest value, per-value counts absent, explanatory strings) are recorded in ADR 0003 and
   `follow-ups.md` task 7; they are not fixed.
4. **RESOLVED (2026-10-04, analyzer commit).** `spike/analyze.py` now reports four buckets
   (`direct_current_identity`, `role_only_identity`, `parent_only_identity`,
   `unclassified_identity_candidates`). `parent_conversation_id` never confirms
   current-subagent identity; `parent_tool_call_id` is an unclassified link candidate,
   not EXACT. The derived verdict is a hint that still requires manual classification per
   row 8. Q1 and Q2 remain OPEN. One sequential Cursor 3.22.7 observation is UNVERIFIED
   and does not close this item. A later Cursor 3.22.7 Linux capture retained
   `parent_tool_call_id` (45/45 comparable inner events matched) but did not
   observe a parallel/background lifecycle (`subagentStop=0`, no
   `is_parallel_worker=true`, no overlapping windows, Task `run_in_background`
   missing). Formal repeated parallel classification has not run; row 8 readiness
   is BLOCKED/OPEN, not a Q1 verdict.
5. `spike/questions.md` secondary questions have no ids (SQ1 to SQ9 above are local). Open.
6. ADR 0001 has one matrix row for headless `agent -p`; row 3 tests without and with
   `--force` separately. No matrix rows exist for rows 15, 17 and 18. Open.
7. [follow-ups](follow-ups.md) says to add rows 10 and 14 to the ADR 0001 matrix "if they are
   not there"; ADR 0001 already lists both, so only rows 3, 15, 17 and 18 need adding. Open.
8. Gaps, not contradictions. **RESOLVED (2026-10-04):** the end-to-end hook overhead
   tolerance (row 13B) is now the PASS / PARTIAL / FAIL contract in ADR 0001 section D, and
   `release-checklist.md` names it as a gate. **RESOLVED (2026-10-04):** ADR 0009 amendment
   and ADR 0002 state the repository-root preconditions for `init`/`uninstall` (exit 2, no
   `--allow-non-git`; subdirectory refuses; nested and linked-worktree roots are valid).
   **RESOLVED (2026-10-04, documentation only):** 17b hook attribution inherits an already
   initialized enclosing repository (ADR 0002); `init` from 17b still exits 2. The result
   record stays OPEN until a live run. **Still open:** the release checklist does not yet
   name the row 15 gate; no first-run (cold cache) target exists.

## After the run

- Fill in `spike/questions.md` results and the ADR 0001 matrix (move the row from NOT RUN to
  PASS, FAIL or PARTIAL with the version and date). Add matrix rows for rows 3 (split by
  `--force`), 15, 17 and 18.
- Update the status of dependent ADRs (see the "Can change" lines) and
  [follow-ups](follow-ups.md): each task there names the row it waits for.
- Update README, quickstart, platform-support and product-contract so the supported-surface
  claims match the matrix exactly.
- Clean up with README "Cleanup" (`git worktree prune`) and remove the scratch repo.

## Not tested by this plan

- Cloud agents (invisible by design).
- Cursor versions other than the ones you ran.
- Enterprise or team-level hooks, beyond what `doctor` can read from disk.
- Anything that needs network access from hooks (forbidden).
- Other operating system versions, shells, and filesystems than the ones recorded in each
  result record; a result holds only for what was run.
- Models other than the ones recorded for rows 1 and 14; instruction following varies by
  model.
