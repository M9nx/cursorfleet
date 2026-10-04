# Empirical test plan (M0a live Cursor spike)

> **NOTHING IN THIS PLAN HAS BEEN EXECUTED OR VERIFIED.** No live Cursor session, CLI run,
> stress test or benchmark described here has been performed. Every result is **OPEN**.
> Statements about Cursor behaviour are quoted from the Cursor documentation ("per docs") or
> are questions to answer; none is a verified fact. The only measured number anywhere near
> this plan is the Linux cold-start latency of our own hook, measured outside Cursor
> (ADR 0001 section C).

This is the contract for the live spike. It adds no code. New M2 and TUI work stays frozen
until it is done ([status](status.md)). It is the author's plan, not an independent audit.

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
| 13 | Latency: hook-internal and end-to-end (Q6) | 13 (split) |
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
  the surface; whether the Hooks output channel logged errors.
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

Question (ADR 0001 Q1): when a subagent calls a tool, does the hook payload say *which
subagent instance* made the call? Per docs only `subagentStart` documents `subagent_id`,
`subagent_type` and `parent_conversation_id`; `subagentStop` documents `subagent_type` but no
id; tool hooks document no subagent identity.

**Result vocabulary** (the only four allowed; classify per hook name, by hand):

| Outcome | Definition |
| --- | --- |
| EXACT | Tool hooks inside the subagent carry an id that uniquely identifies the *current subagent instance*, and that id equals `subagentStart.subagent_id` of exactly one start (so it is linkable to a role and a lifecycle). |
| ROLE_ONLY | Tool hooks carry only the subagent type or role (for example `subagent_type`). It names the kind of agent, not the instance: two concurrent subagents of one type are indistinguishable. |
| PARENT_ONLY | Tool hooks carry only the parent's conversation id (for example `parent_conversation_id`, or a `conversation_id` equal to the parent's). It says who spawned the work, not which subagent did it. |
| UNKNOWN | None of the above, or the evidence is ambiguous or inconsistent (a field present on some hooks or runs only, a value shared where it should be unique, an id that never matches a `subagentStart`). |

Rules for classification:

- **Parent identity is not current-subagent identity.** `parent_conversation_id`, or the
  parent's `conversation_id` appearing on a tool hook, must never be reported as EXACT. It
  can at most produce PARENT_ONLY.
- If several fields are present, the outcome is the strongest level that holds in 100% of
  valid runs; a field that is present only part of the time counts as absent for that level
  (so the outcome drops, usually to UNKNOWN) and its rate is recorded.
- If role and parent are both present but no instance id, the outcome is ROLE_ONLY; note
  that the parent field was also present.
- A per-subagent unique value that never equals any `subagentStart.subagent_id` cannot be
  linked to a start: classify UNKNOWN and note "unlinked discriminator".
- Do not use the `analyze.py` Q1 verdict string. It prints "LIKELY YES" when any tool-hook
  key contains `parent_`, which would turn PARENT_ONLY into a pass. Use its raw outputs
  (`tool_hook_keys_with_agent_identity`, `tool_conversation_id_relation`) and classify by
  hand with the definitions above. (The kit is not changed in this pass.)

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
- Pass (hypothesis "tool hooks identify the subagent instance"): EXACT for every tool hook
  name tested, in all valid runs of R8.1 and R8.2 (zero mismatches against ground truth).
  PARTIAL: EXACT for some hook names only (list them). Refuted: ROLE_ONLY, PARENT_ONLY or
  UNKNOWN, with the outcome recorded. Fixtures: `tests/fixtures/cursor/subagent/` (row 16
  review).

What each outcome means for the ADRs (all consequences are OPEN until a result exists):

| Outcome | ADR 0003 attribution (`exact`, `inferred_temporal`, `unknown`) | ADR 0010 reducer and ADR 0002 |
| --- | --- | --- |
| EXACT | tool events may be `exact` with `agent_instance_id` and `agent_id` `role#instance` | the unattributed `main` accumulation shrinks; lanes can rest on observed activity per instance; writer = instance id becomes viable (topology T1, row 7); stop-to-start pairing still needs an id on `subagentStop` |
| ROLE_ONLY | ADR 0003 section 2 would let a role-only claim be `exact` with `agent_instance_id` absent. This plan flags that wording as an OWNER DECISION: with concurrent same-type subagents a role claim cannot name the instance, so it must never be displayed or exported as instance attribution | tool events attach to a role at most, never to an instance entry; writer stays `main` (topology T2 matters); pairing unchanged (role plus start time against `stop_ts - duration_ms`, preference 2) |
| PARENT_ONLY | `unknown` for the current subagent; never `exact`. The parent id only groups under the parent session, which `session_id` already does | tool events accumulate on `main` with `attribution: unknown`; `inferred_temporal` stays reserved and is not emitted in v0.1 |
| UNKNOWN | `unknown` | as PARENT_ONLY; per-agent cards show lifecycle only (`lifecycle_only` basis). Worktree or `workspace_roots` identity could only ever be a heuristic (ADR 0011 tier 2), never `exact`, and only if isolation is honoured |

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
  the per-role story in v0.2, and the wording of the ADR 0001 Q1 matrix row, which today
  says "names the subagent or its parent".
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence path: -;
  reviewer sign-off: -; ADRs affected: 0001 Q1, 0002, 0003, 0010, 0011, 0012.

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

### 10. `Task` tool linkage and ids (secondary questions)

- Procedure: README 2 and 3; read the analysis for these secondary questions in
  `spike/questions.md`.
- Pass: whether `Task`'s `tool_use_id` equals `subagentStart.tool_call_id`, whether
  `generation_id` is stable across a subagent, and whether subagents get their own
  `sessionStart` and `sessionEnd` are each recorded.
- Can change: ADR 0003 (`inferred_*` methods), ADR 0010 (subagentStop pairing).
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence: -;
  reviewer sign-off: -; ADRs affected: 0003, 0010.

### 11. Permission-hook fail-open reply shape (release gate)

- Procedure: the kit already prints `{"permission":"allow"}` for permission hooks
  (`spike/capture_hook.py`), so rows 1, 8 and 9 exercise it. Additionally, once, set
  a permission hook to print `{}` and then empty output in a scratch hooks file and note
  whether the action proceeds. The README has no step for this.
- Artifacts: written notes plus a fixture of the exact reply and Cursor's behaviour.
- Pass: `{"permission":"allow"}` is accepted for `preToolUse` and `subagentStart` and the
  action proceeds. Record behaviour for `{}` and empty output.
- Fail: the fail-open reply is wrong and could block users; do not ship the hook until fixed.
- Can change: ADR 0001, ADR 0007 and ADR 0008 (fail-open policy), `hook_policy.fail_open_response`.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence: -;
  reviewer sign-off: -; ADRs affected: 0001, 0007, 0008.

### 12. `ask` on permission hooks

- Procedure: in a scratch hooks file, return `ask` once each for `preToolUse` and
  `subagentStart` (and `beforeShellExecution` only to record, since ADR 0007 drops it).
  The README has no step for this.
- Pass (informational): whether a prompt appears is recorded once per hook.
- Can change: ADR 0008 only (v0.2 Guard design). No effect on v0.1 support.
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence: -;
  reviewer sign-off: -; ADRs affected: 0008.

### 13. Hook latency inside Cursor (Q6) on Linux, macOS, Windows

- Procedure: README 0 and 5 (`python3 spike/bench_latency.py -n 40` on each OS), plus the
  capture's own `latency_ms` and `stdin_read_ms` from live runs.
- Artifacts: `spike/results/latency-<os>.json`; Q6 section.
- Pass: p95 in-Cursor delay with the stdlib hook is under 60 ms warm on each OS claimed;
  note whether Cursor waits for `postToolUse`.
- Fail: the OS is not claimed or the hot path is slimmed; budgets in
  [hook-latency](hook-latency.md) change.
- Also record: `timeout` behaviour (is the hook killed, what does Cursor log), and on Windows
  whether `python .cursor/hooks/capture_hook.py <event>` works from Cursor's shell.
- Can change: ADR 0001, platform-support, hook-latency, ADR 0007 (hook count if latency is bad).
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence: -;
  reviewer sign-off: -; ADRs affected: 0001 Q6, 0007.

### 14. Rule, skill and nested `AGENTS.md` loading

- Procedure: not in the README. In the scratch repo run `cursorfleet init --cursor` output
  or hand-copy files from `templates/cursor/`, then start a fresh agent chat and ask it
  (with no other context) to state its coordinator instructions, the artifact format and
  what the nested `.cursorfleet/work/AGENTS.md` says. Repeat in a subagent and in a
  worktree. Check rule scoping (`globs`) by editing a matching file.
- Artifacts: written notes of what was loaded and where.
- Pass: the generated rule, skills and nested `AGENTS.md` are loaded where ADR 0006 and
  ADR 0012 assume, in the main agent and (separately recorded) in subagents.
- Fail: instructions do not reach subagents or worktrees: the artifact format and
  coordinator flow cannot be relied on; revise the kit docs.
- Can change: ADR 0006 (review trigger), ADR 0012, ADR 0009 (what the kit installs),
  [kit](kit.md), [governance](governance.md).
- Result record: OPEN; date: -; Cursor version / OS / surface: -; evidence: -;
  reviewer sign-off: -; ADRs affected: 0006, 0009, 0012.

## After the run

- Fill in `spike/questions.md` results and the ADR 0001 matrix (move the row from NOT RUN to
  PASS, FAIL or PARTIAL with the version and date).
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
