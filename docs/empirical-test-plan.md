# Empirical test plan (M0a live Cursor spike)

Status: **nothing here has been run.** Every result is OPEN. This is the contract for the
live spike; it adds no code. New M2 and TUI work stays frozen until it is done
([status](status.md)).

- Procedures live in [`spike/README.md`](../spike/README.md) ("README" below, by section
  number) and the questions in [`spike/questions.md`](../spike/questions.md).
- The spike kit is not changed by this plan. Where the kit has no procedure for a row, the
  row says so and gives the manual steps; extending the kit is a follow-up.
- Never run the spike in a repository with secrets. Use a scratch repo with one commit.
- Record, for every row: Cursor version (`cursor --version` or Help > About), surface, OS,
  date, and the verdict `CONFIRMED / REFUTED / PARTIAL / OPEN`.
- Raw captures stay under `<git-common-dir>/cursorfleet-spike/`, never committed. Reviewed,
  hand-sanitized lines go to `tests/fixtures/cursor/<surface>/` stamped with `cursor_version`
  (README section 6). Verdicts go to `spike/questions.md`, then into the named ADRs.
- This is the author's plan. It is not an independent audit.

## Order of work

1. Setup and self-test (README 0, 1).
2. IDE main agent and subagents (README 2): rows 1, 8, 9, 12.
3. IDE worktrees and parallel subagents (README 3): rows 5, 6, 7, 10.
4. Agents Window (README 3, last paragraph): row 4.
5. CLI (README 4): rows 2, 3.
6. Failures, compaction, latency on each OS (README 5): rows 11, 13.
7. Instruction loading (not in the README): row 14.
8. Analysis and verdicts (README 6), then ADR updates.

## Rows

### 1. IDE (desktop), main agent only

- Procedure: README 1, then a plain agent prompt that edits a file and runs one shell
  command. Use `python3 spike/analyze.py`.
- Expected artifacts: `captures.jsonl` with one record per hook that fired; analysis
  section listing hooks seen and `cursor_versions`; fixtures in `tests/fixtures/cursor/ide/`.
- Pass: every hook registered under ADR 0007 (`sessionStart`, `sessionEnd`, `preToolUse`,
  `postToolUse`, `postToolUseFailure`, `subagentStart`, `subagentStop`, `preCompact`,
  `stop`) that the scenario can trigger fires with the documented fields; `cursor_version`
  is present.
- Fail: a hook never fires or fields are missing: record which.
- Can change: ADR 0001 section A5, the matrix row; ADR 0007 (hook set); `hook_normalize`
  field assumptions; whether the IDE claim can be made at all.

### 2. CLI interactive `agent`

- Procedure: README 4, interactive session, label `cli-interactive`.
- Artifacts: events per label; fixtures in `tests/fixtures/cursor/cli/`.
- Pass: the set of hooks that fire is recorded per hook name, each on a documented-field
  payload, and `cursor_version` is meaningful.
- Fail or partial: the README and platform docs keep "CLI not supported".
- Can change: ADR 0001 (Q3 verdict), platform-support, product-contract supported surface.

### 3. CLI headless `agent -p`

- Procedure: README 4 (`agent -p --force ...`, label `cli`).
- Artifacts: as row 2, fixtures in `tests/fixtures/cursor/cli-print/`, recorded separately.
- Pass and fail criteria as row 2.
- Can change: the same documents as row 2; whether CI or scripted agent runs can be observed.

### 4. Agents Window

- Procedure: README 3 last paragraph (label `agents-window-wt`): start an agent from the
  Agents Window into a worktree, one file edit and one shell command.
- Artifacts: fixtures in `tests/fixtures/cursor/agents-window/`; `git worktree list`
  (do not paste home paths into issues).
- Pass: hooks fire and `workspace_roots` is recorded.
- Fail or partial: not supported; the doc statement stays.
- Can change: ADR 0001 (Q3), ADR 0002 (runtime dir resolution, Q4), ADR 0012.

### 5. Cursor-managed worktree (`/worktree`, `/best-of-n`)

- Procedure: README 3 (labels `ide-worktree-cmd`, `ide-best-of-n`).
- Artifacts: Q3/Q4 `git_kind` table, `capture_dir_source`; fixtures in
  `tests/fixtures/cursor/worktree-managed/`.
- Pass: project hooks fire from the worktree; `workspace_roots` and hook cwd are recorded;
  the runtime directory under the git common dir resolves identically from the main
  checkout and the worktree (Q4).
- Fail: ADR 0002 runtime directory choice is wrong for worktrees and must be revisited.
- Can change: ADR 0002 (blocking), ADR 0012, the `worktree_id` derivation, TUI worktree view.

### 6. Manual worktree (`git worktree add`, opened in Cursor)

- Procedure: create the worktree by hand, open it in Cursor, repeat row 5's scenario. The
  README has no manual-worktree section; use README 3's analysis steps.
- Artifacts: fixtures in `tests/fixtures/cursor/worktree-manual/`.
- Pass: same criteria as row 5.
- Can change: ADR 0002, ADR 0012, platform-support.

### 7. Parallel subagents and concurrency (Q5)

- Procedure: README 3 (label `ide-parallel-wt`): two subagents concurrently, isolation
  requested in the prompt. Repeat on each OS you want to claim.
- Artifacts: Q5 section (`max_concurrent_hook_processes`, `overlapping_process_pairs`,
  `overlapping_subagent_windows`, `tool_calls_started_while_another_open`),
  `corrupt_lines_skipped`; `spike/results/`.
- Pass: overlap is observed and every appended line is intact; no torn writes.
- Fail: the ADR 0002 spool split (one file per session) must change; the Windows `O_APPEND`
  assumption is not safe.
- Also record: whether isolation was honoured (`git worktree list`, `workspace_roots`), and
  `subagentStart.git_branch` / `is_parallel_worker` values.
- Can change: ADR 0002, ADR 0010 (pairing), ADR 0012.

### 8. Subagent identity inside tool hooks (Q1)

- Procedure: README 2, then read the Q1 verdict from `analyze.py`.
- Artifacts: `tool_hook_keys_with_agent_identity`, `tool_conversation_id_relation`;
  fixtures in `tests/fixtures/cursor/subagent/`.
- Pass: tool hooks inside a subagent carry a field naming the subagent or its parent.
- Fail: attribution stays `unknown` for tool events and `inferred_temporal` at best
  (ADR 0003); per-agent cards show lifecycle only.
- Can change: ADR 0003 attribution, ADR 0010, the TUI per-agent view, the whole per-role
  story in v0.2.

### 9. Custom `.cursor/agents` `subagent_type` naming (Q2)

- Procedure: README 2 with `cf-reviewer` and `cf-writer`, plus `/cf-reviewer review README.md`.
- Artifacts: `types_seen`, `non_builtin_types`; same fixtures directory as row 8.
- Pass: the value for a custom agent is recorded verbatim for `subagentStart` and
  `subagentStop`, and a `matcher` on it is tested.
- Fail: it is `generalPurpose` or another fixed value: role mapping must come from elsewhere.
- Can change: `hook_normalize` role mapping, ADR 0003, ADR 0012, the kit's roster file names.

### 10. `Task` tool linkage and ids (secondary questions)

- Procedure: README 2 and 3; read the analysis for these secondary questions in
  `spike/questions.md`.
- Pass: whether `Task`'s `tool_use_id` equals `subagentStart.tool_call_id`, whether
  `generation_id` is stable across a subagent, and whether subagents get their own
  `sessionStart` and `sessionEnd` are each recorded.
- Can change: ADR 0003 (`inferred_*` methods), ADR 0010 (subagentStop pairing).

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

### 12. `ask` on permission hooks

- Procedure: in a scratch hooks file, return `ask` once each for `preToolUse` and
  `subagentStart` (and `beforeShellExecution` only to record, since ADR 0007 drops it).
  The README has no step for this.
- Pass (informational): whether a prompt appears is recorded once per hook.
- Can change: ADR 0008 only (v0.2 Guard design). No effect on v0.1 support.

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
