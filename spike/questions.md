# M0a open questions

Each question comes from the CursorFleet v0.1 plan (section 2 and the M0a
spike list). Status as of this writing: **Q1 and Q2 remain OPEN.** One sequential Cursor
3.22.7 observation exists and is UNVERIFIED; do not treat it as a result.
Fill in the "Result" lines only after row-8 repetitions and review.

Result values: `CONFIRMED`, `REFUTED`, `PARTIAL`, `OPEN`. Always record the
`cursor_version` and the surface (IDE, Agents Window, CLI) with the result.

## Q1. Identity of the current subagent inside its tool hooks

- Question: when a subagent calls a tool (Shell, Read, Write, ...), do the
  `preToolUse` / `postToolUse` / `beforeShellExecution` / `afterFileEdit`
  payloads identify the **current subagent instance**, or can they be
  deterministically linked to it (an id relationship verified empirically, for
  example an id on the tool hook that equals exactly one
  `subagentStart.subagent_id`)? Or do they carry only a role, only the parent,
  or nothing, looking identical to main-agent tool hooks?
- Outcome mapping (owner decision 2026-10-04; method in
  `docs/empirical-test-plan.md` row 8):
  unique current instance (EXACT) = CONFIRMED (attribution `exact`);
  role only (ROLE_ONLY) = PARTIAL (`inferred`);
  parent only (PARENT_ONLY) or nothing (UNKNOWN) = REFUTED (`unknown`);
  ambiguous or undocumented fields = OPEN (`unknown` until classified).
  A parent identity never confirms a child identity.
- Docs say: base fields are `conversation_id` and `generation_id`;
  `subagent_id`, `subagent_type`, `parent_conversation_id` are documented only
  on `subagentStart`. `subagentStop` documents `subagent_type` but **no**
  `subagent_id`. Nothing documents identity on tool hooks. One unverified
  Cursor 3.22.7 sequential run observed optional `subagent_id` and
  `child_conversation_id` on `subagentStop`; treat those as optional, not
  guaranteed. The same run saw `parent_tool_call_id` on inner tool hooks
  (a deterministic-link *candidate*, not EXACT and not parent-only until
  row 8 repetitions verify it).
- Why it matters: per-agent timelines, the `agent_instance_id` field mapping,
  and attribution of edits/commands to roles in v0.1 and any v0.2 per-role guard.
- Evidence in `analyze.py`: the four separate categories `direct_current_identity`,
  `role_only_identity`, `parent_only_identity` (`parent_conversation_id` or the parent's
  `conversation_id` only ever lands here) and `unclassified_identity_candidates`
  (undocumented or unlinked id-like keys, or `parent_tool_call_id` as a link candidate;
  never auto-promoted); the "Q1" VERDICT, which is a hint requiring manual classification
  per row 8 (CONFIRMED only from direct, PARTIAL for role only, REFUTED for parent only or
  nothing found, OPEN for unclassified candidates or no data); the relationship counters
  (`Task.tool_use_id` / `parent_tool_call_id` / stop `subagent_id` / child
  `conversation_id` equalities); the raw `tool_hook_keys_with_agent_identity` and
  `tool_conversation_id_relation`; the share of in-window tool events with the same
  conversation+generation as the main agent. Temporal inner-tool association is never
  treated as exact.
- Fallbacks if the instance is NOT identifiable (all would be `inferred`): temporal
  attribution (unsafe with parallel subagents), worktree/`workspace_roots` as the identity (only with isolation),
  `tool_use_id` linkage of the `Task` call to `subagentStart.tool_call_id`,
  agent self-reported artifacts (plan section 3, item 4).
- Result: OPEN

## Q2. How custom subagent names appear in `subagent_type`

- Question: for a custom subagent `.cursor/agents/cf-reviewer.md`, is
  `subagent_type` `cf-reviewer`, the frontmatter `name`, the filename, or just
  `generalPurpose`? Same for `subagentStop` and for the `matcher` on
  `subagentStart`/`subagentStop`.
- Docs say: the type is `generalPurpose`, `explore`, `shell`, "etc.". Custom
  agents are not mentioned in the hooks reference.
- Why it matters: the role mapping (`subagent_type` to `agent_role`) and
  whether hook `matcher` can target roles.
- Evidence: "Q2" section: `types_seen` and `non_builtin_types`.
- Result: OPEN

## Q3. Do hooks fire in the Cursor CLI and in Agents Window worktrees?

- Question: which hooks fire under `agent -p`, interactive `agent`, and agents
  started from the Agents Window into a worktree? Do user, project and
  worktree-local `.cursor/hooks.json` all load? Is `cursor_version` set and
  meaningful for the CLI?
- Docs say: `workspaceOpen` runs in the desktop app and CLI; worktree setup
  (`.cursor/worktrees.json`) is honored in Agents Window, IDE and CLI. The
  hooks page does not state per-hook CLI support.
- Evidence: events per `label`; `cursor_versions`.
- Result: OPEN

## Q4. `workspace_roots` in Cursor-managed worktrees

- Question: inside a Cursor-created worktree, is `workspace_roots` the worktree
  path or the main checkout? Does the hook process cwd match? Is
  `<root>/.git` a gitfile (linked worktree)? Does
  `<git-common-dir>/cursorfleet-spike/` resolve to the same directory from the
  main checkout and every worktree (the storage-layout decision in plan
  section 3, item 1)?
- Docs say: nothing about hook payloads in worktrees; project hooks "run from
  the project root".
- Evidence: "Q3/Q4" git_kind table per source (`workspace_roots`,
  `payload.cwd`, `process_cwd`, `CURSOR_PROJECT_DIR`), `capture_dir_source`,
  and whether events from several worktrees land in one file.
- Result: OPEN

## Q5. Parallel subagent hook interleaving

- Question: with two subagents running concurrently, do hook processes overlap
  in time, do their tool events interleave, and are appends to one capture file
  intact (no torn lines)?
- Docs say: parallel subagents run "simultaneously"; hooks are "spawned
  processes"; nothing about hook serialization.
- Why it matters: spool design (single `O_APPEND` file vs one file per
  conversation/subagent), per-line CRC, torn-tail handling on Windows.
- Evidence: "Q5" section (`max_concurrent_hook_processes`,
  `overlapping_process_pairs`, `overlapping_subagent_windows`,
  `tool_calls_started_while_another_open`) and `corrupt_lines_skipped`.
- Result: OPEN

## Q6. Hook latency

- Question: what is the real cost of a stdlib-only Python hook, measured by
  Cursor's own spawn (not only by our wall clock), on Linux, macOS and Windows?
  Does Cursor wait for `postToolUse`/`afterFileEdit` hooks before continuing?
- Terms (ADR 0001 section D): steady-state = fresh process, warm OS/page cache;
  first-run = fresh process, cold or partly cold cache; hook-internal = time after
  process start; end-to-end = paired hooks-on versus hooks-off user-visible overhead.
- Targets: per hook, steady-state p95 <= 60 ms process wall time including
  interpreter startup. End-to-end (paired delta, hooks-on minus hooks-off, at least 3
  batches of 30 pairs, pooled, each batch not FAIL): PASS median <= 100 ms and p95
  <= 200 ms; PARTIAL median <= 150 ms and p95 <= 300 ms; FAIL above that or on any
  hook-induced failure or timeout.
- Measured so far (this repo, Linux only, steady-state process wall time on our
  clock, not Cursor-measured): see `spike/results/latency-linux.json` and ADR 0001.
- Evidence: `bench_latency.py` on each OS; hook-internal `latency_ms` and
  `stdin_read_ms` in "Q6" from live captures (`stdin_read_ms` hints at how
  late Cursor writes stdin); the paired end-to-end batches of row 13B.
- Result: PARTIAL (Linux steady-state measured; first-run, macOS, Windows and
  end-to-end OPEN)

## Secondary questions worth answering in the same sessions

- Do tool hooks fire for the `Task` tool itself, and does `Task`'s
  `tool_use_id` equal `subagentStart.tool_call_id`?
- Is `generation_id` constant across a subagent's work, or does it change?
- Does `subagentStart.git_branch` differ for isolated worktree subagents, and
  is `is_parallel_worker` true for parallel runs?
- Does `sessionStart.session_id` equal `conversation_id`? Do subagents get their
  own `sessionStart`/`sessionEnd`?
- Are `model`, `model_id`, `model_params` actually present on every hook?
- Which `CURSOR_*` env vars are present in hook processes (`env_names_seen`)?
- Does `preCompact` fire in practice, and do its `context_*` counters appear?
- Does the hook process get killed by `timeout`, and what does Cursor log?
- Windows only: does `python .cursor/hooks/capture_hook.py <event>` work from
  the shell Cursor uses, and what are its steady-state and first-run latencies there?
