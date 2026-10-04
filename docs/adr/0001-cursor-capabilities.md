# ADR 0001: Cursor capabilities and limits that CursorFleet builds on

- Status: provisional (docs-verified; empirical spike NOT yet run). Remains provisional until the empirical test matrix below is complete.
- Date: 2026-10-04
- Deciders: project owner (M9nx)
- Evidence level: verified-from-docs for section A; unverified for section B
- Supersedes: none
- Superseded by: none
- Related ADRs: 0002 (storage, needs Q4/Q5), 0003 (identity fields, needs Q1/Q2), 0007 (hook list, needs permission-hook reply check), 0008 (enforcement boundaries), 0012 (worktree ownership)
- Implementation status: Implemented-provisional (the hook, kit and doctor code encode section A; nothing was validated against live Cursor). The Decision's 12-hook list is narrowed by ADR 0007 and is Divergent-from-code until the follow-up lands.
- Review trigger: the first live spike capture on any surface, or any Cursor release that changes hook payloads or worktree behaviour
- Release gate: Q1 to Q6 answered (CONFIRMED / REFUTED / PARTIAL with `cursor_version` and surface), section B moved to section A or struck, sanitized real fixtures committed under `tests/fixtures/cursor/`, and the permission-hook reply shape confirmed

CursorFleet is an unofficial tool and is not affiliated with Anysphere.

## Supported surface for v0.1 (stated before the facts)

- The **local Cursor IDE (desktop) is the only supported v0.1 surface**, and only once the
  spike has run on it.
- The Cursor CLI (`agent`), the Agents Window, Cursor-managed worktrees, manual
  worktrees, subagent identity, concurrent and parallel subagents, `ask` behaviour and
  hook latency inside Cursor are **not** supported and not claimed until the empirical
  test matrix below passes for each.
- Cloud agents and cloud subagents are out of scope for v0.1 regardless of the matrix.
- No README, quickstart, `doctor` message or platform page may claim support for an item
  that is not marked PASS in the matrix.

## Read this first: what this ADR is and is not

- Section A records what the Cursor documentation says. Sources, all fetched on
  2026-10-04 and subject to change without notice:
  - https://cursor.com/docs/hooks
  - https://cursor.com/docs/subagents
  - https://cursor.com/docs/configuration/worktrees
  - https://cursor.com/docs/cli/headless
- Section B lists claims the docs do not settle. They are **UNVERIFIED-PENDING-EMPIRICAL-SPIKE**.
- **No empirical capture from a live Cursor session was performed by the author
  of this ADR.** The agent that wrote it could not and did not run Cursor. A
  capture kit exists in `spike/` and has been self-tested with synthetic
  payloads only. The user must run `spike/README.md` and then update this ADR.
- `spike/doc_examples/` contains payloads hand-built from the docs. They are
  not captured data and are not evidence of real behaviour.
- The only empirical data in this ADR is the Linux cold-start latency of our
  own stdlib hook, measured on the author's machine, not inside Cursor
  (section C).
- No `cursor_version` is recorded anywhere yet, because nothing was captured.

## A. VERIFIED-FROM-DOCS

### A1. Hook inventory

- Agent hooks (fire during an agent session): `sessionStart`, `sessionEnd`,
  `preToolUse`, `postToolUse`, `postToolUseFailure`, `subagentStart`,
  `subagentStop`, `beforeShellExecution`, `afterShellExecution`,
  `beforeMCPExecution`, `afterMCPExecution`, `beforeReadFile`, `afterFileEdit`,
  `beforeSubmitPrompt`, `preCompact`, `stop`, `afterAgentResponse`,
  `afterAgentThought`.
- Tab hooks (inline completions only): `beforeTabFileRead`, `afterTabFileEdit`.
- App lifecycle hook (outside any agent session): `workspaceOpen`. It omits
  `conversation_id`, `generation_id`, `model`, `session_id` and `transcript_path`,
  and runs in the desktop app and in the CLI.
- Hooks are spawned processes that speak JSON over stdio. Two types exist:
  command (default) and prompt (LLM-evaluated, returns `{ok, reason?}`). Cloud
  agents run command hooks only.

### A2. Permission hooks and the `ask` enforcement matrix

- Permission hooks (the docs list them as the hooks where invalid JSON or a
  schema-mismatching response blocks the action): `beforeShellExecution`,
  `beforeMCPExecution`, `beforeReadFile`, `beforeTabFileRead`, `subagentStart`,
  `preToolUse`.
- Observational (non-permission) hooks: `sessionStart`, `sessionEnd`,
  `postToolUse`, `postToolUseFailure`, `subagentStop`, `afterShellExecution`,
  `afterMCPExecution`, `afterFileEdit`, `beforeSubmitPrompt` (can only block
  via `continue: false`, a different schema), `preCompact`, `stop`,
  `afterAgentResponse`, `afterAgentThought`, `afterTabFileEdit`,
  `workspaceOpen`.
- `ask` handling per the docs:
  - `preToolUse`: `ask` is accepted by the schema but **not enforced today**.
    Only `allow` and `deny` are meaningful.
  - `subagentStart`: `ask` is **not supported** and is treated as `deny`.
  - `beforeShellExecution` and `beforeMCPExecution`: the documented output
    schema is `allow | deny | ask`, and the docs' own example uses `ask` for
    `gh` commands. These are the only hooks whose documented schema offers
    `ask` as a working option. (Whether the user prompt actually appears is in
    section B.)
  - `beforeReadFile` and `beforeTabFileRead`: schema is `allow | deny` only.
  - `beforeSubmitPrompt`: uses `continue` true/false, not `permission`.
- Other output fields: `preToolUse` may return `updated_input`; `postToolUse`
  may return `additional_context` and (MCP only) `updated_mcp_tool_output`;
  `stop` and `subagentStop` return `followup_message`; `sessionStart` may
  return `env` and `additional_context`. The `sessionStart` schema accepts
  `continue`/`user_message` but they are not enforced.

### A3. Exit codes, failure semantics, `failClosed`

- Exit `0`: use the JSON output. For permission hooks, invalid JSON or a
  schema-mismatching response blocks the action.
- Exit `2`: block the action (same as `permission: "deny"`; Claude Code compatible).
- Any other exit code (crash, timeout): fail open, the action proceeds.
- `failClosed: true` on a hook definition makes crash, timeout, non-zero exit
  and empty output block the action. Permission hooks block on invalid JSON
  even when `failClosed` is false.
- Observability hooks in CursorFleet must therefore always exit 0 and print
  `{}` (non-permission) or `{"permission":"allow"}` (permission hooks).
  Printing `{}` from a permission hook is a schema risk the docs imply will block.
- Per-script options: `command`, `type`, `timeout` (seconds, platform default),
  `loop_limit` (stop/subagentStop, default 5, `null` for unlimited),
  `failClosed`, `matcher` (regex; empty or `*` matches all).
- Matchers: `preToolUse`/`postToolUse`/`postToolUseFailure` match tool type
  (`Shell`, `Read`, `Write`, `Grep`, `Delete`, `Task`, `MCP:<tool_name>`);
  `subagentStart`/`subagentStop` match subagent type; the shell hooks match the
  command text; `afterFileEdit` matches the value `Write`; `stop` matches `Stop`.

### A4. Configuration sources and merge order

- Sources, highest priority first: Enterprise (MDM; Linux `/etc/cursor/hooks.json`,
  macOS `/Library/Application Support/Cursor/hooks.json`, Windows
  `C:\ProgramData\Cursor\hooks.json`), Team (cloud-distributed, Enterprise
  plan), Project (`.cursor/hooks.json`, requires a trusted workspace), User
  (`~/.cursor/hooks.json`).
- All matching hooks from every source run. Responses merge: any `deny` beats
  `ask` beats `allow`, regardless of source. `user_message` and `agent_message`
  are concatenated. For other fields (such as `followup_message`) the last
  response wins, and the docs say a lower-priority source overrides a
  higher-priority one for those fields.
- Working directory: project hooks run from the project root (use
  `.cursor/hooks/x.py`, not `./hooks/x.py`); user hooks run from `~/.cursor/`.
- Cursor watches `hooks.json` and reloads on save. There is a Hooks tab in
  Customize and a Hooks output channel for debugging.
- Cursor can also load hooks from third-party tools such as Claude Code (details
  in the docs' Third Party Hooks page, not read for this ADR). `doctor` should
  assume extra hooks may be active.
- Hook environment variables: `CURSOR_PROJECT_DIR`, `CURSOR_VERSION`,
  `CLAUDE_PROJECT_DIR` (always); `CURSOR_USER_EMAIL`, `CURSOR_TRANSCRIPT_PATH`
  (conditional); `CURSOR_CODE_REMOTE` (remote workspaces).

### A5. Documented payload fields (basis for the allowlist)

- Base fields on every hook: `conversation_id`, `generation_id`, `model`,
  `model_id`, `model_params`, `hook_event_name`, `cursor_version`,
  `workspace_roots`, `user_email`, `transcript_path`.
- Tool hooks add `tool_name`, `tool_input`, `tool_use_id`, `cwd`. `postToolUse`
  adds `tool_output` and `duration`; `postToolUseFailure` adds `error_message`,
  `failure_type` (`error | timeout | permission_denied`), `duration`,
  `is_interrupt`.
- `subagentStart`: `subagent_id`, `subagent_type`, `task`,
  `parent_conversation_id`, `tool_call_id`, `subagent_model`,
  `is_parallel_worker`, optional `git_branch`.
- `subagentStop`: `subagent_type`, `status`, `task`, `description`, `summary`,
  `duration_ms`, `message_count`, `tool_call_count`, `loop_count`,
  `modified_files`, `agent_transcript_path`. **The docs list no `subagent_id`
  here**, so a stop cannot be matched to a start by id from documented fields
  alone.
- `sessionStart`: `session_id` (same as `conversation_id` per the docs),
  `is_background_agent`, `composer_mode`. `sessionEnd`: `session_id`, `reason`,
  `duration_ms`, `is_background_agent`, `final_status`, `error_message`.
  `sessionStart` is fire-and-forget; `sessionEnd` response is ignored.
- `stop`: `status`, `loop_count`. `preCompact`: `trigger`,
  `context_usage_percent`, `context_tokens`, `context_window_size`,
  `message_count`, `messages_to_compact`, `is_first_compaction`.
  `preCompact` is observational and cannot block.

### A6. `stop` and `subagentStop` cannot block completion

- `stop` can only submit a `followup_message` as the next user message, capped
  by `loop_limit` (default 5 per script). `subagentStop` follow-ups are
  consumed only when `status` is `completed` and share the same limit.
- Therefore "done cannot be declared while gates fail" is not enforceable
  inside Cursor. Real gating has to live outside (CLI exit code, git hook, CI).

### A7. Subagents

- Custom subagent files live in `.cursor/agents/` (also `.claude/agents/`,
  `.codex/agents/`, and the `~/` equivalents). `.cursor/` wins name conflicts;
  project wins over user.
- Frontmatter fields are exactly: `name` (optional, defaults to filename),
  `description`, `model` (`inherit` or a model ID, optionally with
  `[param=value]` options), `readonly` (boolean), `is_background` (boolean).
  There is **no** per-agent tool allowlist, path scope, network or git capability
  field. `readonly: true` is the only permission-like switch and is coarse
  (no file edits, no state-changing shell commands).
- Built-in subagents: Explore, Bash, Browser. Hook `subagent_type` examples in
  the docs: `generalPurpose`, `explore`, `shell`.
- Nesting: since Cursor 2.5, subagents can launch child subagents. The docs say
  the main agent and its **direct** subagents can launch subagents, but a
  subagent launched by another subagent cannot launch further ones. Nested
  launches also need Task tool access in the current mode, and hooks or tool
  policies can block spawning. (See A7 caveat below.)
- Subagents inherit the parent's tools including MCP tools; cloud subagents
  use team MCP config from cursor.com/agents instead.
- Each subagent has its own context window; the docs say five parallel subagents
  use roughly five times the tokens. Docs advise starting with 2 to 3 subagents
  and writing sharp descriptions.
- Model can be pinned per subagent. Cursor falls back to a compatible model
  if the model is blocked by team admin, unavailable on the plan, or needs Max
  Mode on a legacy plan. So a "reviewer on a different model family" setting
  can be silently overridden.
- Resuming: each execution returns an agent ID; background subagents write
  state under `~/.cursor/subagents/`.
- **Caveat on the plan's inference.** The plan concludes that the Coordinator
  "cannot be a subagent". The docs do not literally say that. They allow
  main agent to subagent to child subagent (two levels of subagent), with the
  child unable to spawn more. A coordinator that is a direct subagent could
  therefore still launch workers. The decision to make the Coordinator the main
  agent (driven by a rule or skill) stands as a design choice, but its
  justification is "avoid the depth limit and the unproven identity of hooks
  inside subagents", not "impossible".

### A8. Worktree isolation is requested, not configured

- Subagents share the parent agent's checkout by default and can overwrite each
  other's changes. Isolation is obtained by **asking for it in the prompt**
  ("each in its own environment"). There is no frontmatter field for it.
- When isolated, each subagent gets its own branch, either as a Git worktree on
  the same machine or as a cloud environment (own VM and clone). Changes stay on
  that branch until the parent merges them.
- `subagentStart` carries an optional `git_branch` and an `is_parallel_worker`
  boolean. The docs do not say these change under isolation (section B).
- UI-native worktrees are Agents Window only. In the IDE, `/worktree`,
  `/best-of-n`, `/apply-worktree` and `/delete-worktree` are skills. The CLI
  also honors worktree setup.
- `.cursor/worktrees.json` configures setup (`setup-worktree`,
  `setup-worktree-unix`, `setup-worktree-windows`); it is looked up in the
  worktree path, then the project root. Setup commands receive
  `$ROOT_WORKTREE_PATH`.
- Cursor (3.5 and later) discovers worktrees by re-scanning, and cleans old
  ones: `cursor.worktreeMaxCount` (default cap 25 per machine across all
  workspaces) and `cursor.worktreeCleanupIntervalHours`. Worktrees created by
  `git worktree add` or the skills are also eligible for deletion.
- Consequence: CursorFleet must treat worktrees as externally managed and
  ephemeral, and must never assume they persist.
- The docs give no information on where Cursor places worktrees or what hook
  payloads contain inside them.

### A9. No token or cost data in hooks, except `preCompact`

- Across all documented payloads, token-like data appears only in `preCompact`
  (`context_tokens`, `context_window_size`, `context_usage_percent`). Base fields
  `model`, `model_id`, `model_params` identify the model, not usage.
  `subagentStop` offers duration, message count and tool-call count only.
- Consequence: agent "budget" in the TUI must be elapsed time, tool-call count
  and compaction events, and the UI must say token use is unknown.
- Nothing in any hook payload reports which rules, skills or AGENTS.md files
  were loaded. `beforeReadFile.attachments` lists attachments for one read and
  is not that signal (and the hook is on the never-register list).

### A10. Cloud agents

- Cloud agents run command-based hooks from the repo's `.cursor/hooks.json`.
  Enterprise adds team and enterprise-managed hooks. User-level
  `~/.cursor/hooks.json` is **not** available. Prompt-based hooks do not run.
  Early read-only turns run no hooks.
- Supported in cloud agents: `beforeShellExecution`, `afterShellExecution`,
  `beforeReadFile`, `afterFileEdit`, `preToolUse`, `postToolUse`,
  `postToolUseFailure`, `subagentStart`, `subagentStop`, `beforeSubmitPrompt`,
  `preCompact`, `afterAgentResponse`, `afterAgentThought`, `stop`.
- Not available in cloud agents: `sessionStart`, `sessionEnd`,
  `beforeMCPExecution`, `afterMCPExecution`, `beforeTabFileRead`,
  `afterTabFileEdit`, `workspaceOpen`.
- Self-hosted workers (Pools, My Machines) run the same project hooks, and
  `sessionStart`/`sessionEnd` fire when a session claims and releases the
  worker.
- Hooks in a cloud VM never reach a local spool. v0.1 sees local sessions only.
- Cloud subagents (started with `/in-cloud`) run on their own VM and branch
  and are invisible to local hooks beyond what the parent session reports.

### A11. Hook payloads containing sensitive content: what CursorFleet registers

- **Never register in v0.1** (the payload would reach our process even if we
  discard it). Add an installer unit test that asserts none of these appear in
  generated `hooks.json`:
  - `afterAgentThought`: full thinking text.
  - `afterAgentResponse`: assistant final text.
  - `beforeSubmitPrompt`: user prompt text.
  - `beforeReadFile`: full file contents.
- Also not registered in v0.1 because they carry content and are not needed:
  `beforeTabFileRead` (file contents), `afterTabFileEdit` (old/new lines),
  `beforeMCPExecution` (tool input), `afterMCPExecution` (full result JSON).
  `workspaceOpen` is not needed for the roadmap either.
- **Registered, but they carry sensitive fields in memory that the allowlist
  parser must drop before anything is written:**
  - `preToolUse`: `tool_input` (commands, paths), `agent_message`.
  - `postToolUse`: `tool_input`, `tool_output`.
  - `postToolUseFailure`: `tool_input`, `error_message`.
  - `beforeShellExecution`: `command`. `afterShellExecution`: `command` and full `output`.
  - `afterFileEdit`: `file_path` and `edits` (old and new strings).
  - `subagentStart`: `task`. `subagentStop`: `task`, `description`, `summary`,
    `modified_files`, `agent_transcript_path`.
  - `sessionEnd`: `error_message`.
  - Base fields on every hook: `user_email`, `transcript_path`, and the
    `CURSOR_USER_EMAIL` and `CURSOR_TRANSCRIPT_PATH` environment variables.
- A hook that observes `afterShellExecution` unavoidably receives full command
  output. Narrow `matcher` values, drop fields at the parser boundary, and
  prefer `postToolUse` data (exit code, duration) where it suffices.
- Headless CLI (`agent -p --output-format stream-json`) emits message text and
  tool arguments including file paths; ingesting it needs the same allowlist.
  It is a v0.2 non-goal for v0.1.

### A12. Headless CLI facts

- `agent -p` (`--print`) is non-interactive; it proposes changes only unless
  `--force` (or `--yolo`) is given. Output formats: `text` (default), `json`,
  `stream-json` (plus `--stream-partial-output`). Auth via `CURSOR_API_KEY`.
- `stream-json` events seen in the docs' example: `system`/`init` (model),
  `assistant`, `tool_call` (`started`/`completed`, with args such as `path`),
  `result` (`duration_ms`).
- The headless page says nothing about hooks. Whether hooks fire under
  `agent -p` is section B.

## B. UNVERIFIED-PENDING-EMPIRICAL-SPIKE

None of the following has been observed. Each maps to `spike/questions.md`.

- Q1 agent identity: whether tool hooks fired inside a subagent carry any
  subagent id, type or parent id. The docs document identity fields only on
  `subagentStart` (and `subagent_type` on `subagentStop`).
- Q2 custom subagent names: whether `subagent_type` shows the custom `name`
  (for example `cf-reviewer`), the filename, or only `generalPurpose`; whether
  `matcher` works on custom names.
- Q3 CLI and Agents Window: which hooks fire under `agent -p`, interactive
  `agent`, and Agents Window worktrees; whether `cursor_version` is present.
- Q4 `workspace_roots` in Cursor-managed worktrees, and hook process cwd; whether
  `.git` is a gitfile there; whether `<git-common-dir>/cursorfleet-spike/`
  resolves identically from every worktree.
- Q5 parallel interleaving: whether hook processes overlap; whether concurrent
  `O_APPEND` writes stay intact; whether Cursor serializes hooks.
- Q6 latency inside Cursor: spawn and IPC overhead on top of section C numbers;
  whether Cursor waits for non-permission hooks; Windows and macOS numbers.
- Whether the `ask` prompt actually appears for `beforeShellExecution` and
  `beforeMCPExecution` (the docs offer it in the schema; behaviour unobserved).
- Whether the `Task` tool's `tool_use_id` equals `subagentStart.tool_call_id`
  (the only documented candidate for linking a subagent to its spawn).
- Whether `generation_id` is stable across a subagent's work or changes.
- Whether `git_branch` differs and `is_parallel_worker` is true for isolated,
  parallel subagents.
- Whether subagents emit their own `sessionStart`/`sessionEnd`.
- Whether `model`, `model_id`, `model_params` are present on every hook, and
  whether all documented fields are present in practice (docs and product can
  drift).
- Hook behaviour on `timeout` expiry, and what Cursor logs.
- Whether a repo-committed hook that is missing a dependency produces visible
  noise to teammates without the tool.
- Behaviour on Cursor versions other than the one used for the spike.

## C. Measured on this machine (not Cursor-measured)

Measured with `python3 spike/bench_latency.py -n 60` on Linux 6.18 x86_64,
CPython 3.14.7, 24 CPUs, warm page cache, run unsandboxed on 2026-10-04.
Each run is a fresh process (cold interpreter start) with a doc-derived
`preToolUse` payload on stdin. Wall time is measured by the parent and includes
fork/exec, interpreter start, imports, work and exit. It excludes Cursor's own
spawn and IPC overhead. Raw data: `spike/results/latency-linux.json`.

- Interpreter floor, `python3 -c pass`: p50 14.4 ms, p95 20.4 ms.
- Interpreter floor, `python3 -I -S -c pass`: p50 10.6 ms, p95 15.1 ms.
- Capture hook, `python3 capture_hook.py preToolUse`: p50 24.2 ms, p95 27.7 ms,
  max 30.5 ms (n=60).
- Capture hook with `-I -S`: p50 22.9 ms, p95 26.4 ms (n=60).
- In-process time recorded by the hook itself (excludes interpreter startup):
  p50 7.7 ms, p95 8.7 ms. Most of it is `import json`, `import re`, regex
  compilation and a git-dir walk, so a production hook can trim it.
- An earlier sandboxed run of the same script gave capture p95 32.8 ms: expect
  a few ms of noise between runs and environments.
- Reading: the plan's budget (p95 under 60 ms warm) is met on this Linux
  machine with margin for a stdlib-only hook. This says nothing yet about
  Windows, macOS, antivirus-scanned paths, or Cursor's own overhead.

## Empirical test matrix

Every row is **NOT RUN** today. A surface or behaviour is supported in v0.1 only when its
row is PASS. Procedure for each row: [`docs/empirical-test-plan.md`](../empirical-test-plan.md)
and [`spike/README.md`](../../spike/README.md). Raw captures stay under
`<git-common-dir>/cursorfleet-spike/` (never committed). Reviewed, hand-sanitized subsets go
to `tests/fixtures/cursor/<surface>/` stamped with `cursor_version`; verdicts go to
`spike/questions.md` and then into this ADR.

- **IDE (desktop), main agent only.** Pass: every hook registered under ADR 0007 fires with
  a payload matching section A5 fields; `cursor_version` present. Evidence:
  `tests/fixtures/cursor/ide/`.
- **CLI interactive `agent`.** Pass: the list of hooks that fire is recorded per hook name
  and each fired hook is on a documented-field payload. Fail or partial: README says "CLI
  not supported". Evidence: `tests/fixtures/cursor/cli/`.
- **CLI headless `agent -p`.** Pass: same as above, recorded separately. Evidence:
  `tests/fixtures/cursor/cli-print/`.
- **Agents Window.** Pass: hooks fire for an agent started from the Agents Window into a
  worktree, and `workspace_roots` is recorded. Evidence: `tests/fixtures/cursor/agents-window/`.
- **Cursor-managed worktree (IDE `/worktree`, `/best-of-n`).** Pass: project hooks fire
  from the worktree, `workspace_roots` and hook cwd are recorded, and the common dir
  resolves identically to the main checkout (Q4). Evidence:
  `tests/fixtures/cursor/worktree-managed/`.
- **Manual worktree (`git worktree add` opened in Cursor).** Pass: same criteria as the
  managed row. Evidence: `tests/fixtures/cursor/worktree-manual/`.
- **Subagent identity (Q1).** Pass: tool hooks fired inside a subagent carry a field that
  names the subagent or its parent, shown by `spike/analyze.py` Q1 verdict. Fail: attribution
  stays `unknown` for tool events (ADR 0003). Evidence: `tests/fixtures/cursor/subagent/`.
- **Custom `subagent_type` naming (Q2).** Pass: the value for `.cursor/agents/cf-reviewer.md`
  is recorded verbatim for `subagentStart` and `subagentStop`. Evidence: same directory.
- **Concurrency and parallel subagents (Q5).** Pass: two parallel subagents produce intact
  appended lines with no torn writes in the capture file and overlap is recorded, on each
  OS tested. Fail: ADR 0002 spool split must change. Evidence: `spike/results/`.
- **`ask` behaviour.** Pass: the prompt does or does not appear for `ask` on
  `beforeShellExecution`, `preToolUse` and `subagentStart`, observed once per hook. This
  is informational for v0.2 and does not affect v0.1 support. Evidence: spike notes.
- **Permission-hook fail-open reply.** Pass: `{"permission":"allow"}` is accepted for
  `preToolUse` and `subagentStart` and the action proceeds; behaviour for `{}` and for
  empty output is recorded. This is a release gate. Evidence: spike notes plus a fixture.
- **Hook latency inside Cursor (Q6).** Pass: p95 of the in-Cursor delay with the stdlib hook
  is under 60 ms warm on each OS claimed, measured by `spike/bench_latency.py` and by the
  capture's own timings. Evidence: `spike/results/latency-<os>.json`.

## Decision

We record the verified facts in section A as constraints on the v0.1 design:

- Observe-first: no enforcement claim in v0.1. `ask` and `stop`-based "gates"
  are not relied on. Per-agent least privilege is documentation only.
- Register only the passive hooks in the plan (`sessionStart`, `sessionEnd`,
  `preToolUse`, `postToolUse`, `postToolUseFailure`, `subagentStart`,
  `subagentStop`, `beforeShellExecution`, `afterShellExecution`,
  `afterFileEdit`, `preCompact`, `stop`) and never register the four hooks in
  A11. Every registered hook always exits 0 with the correct empty or allow
  response. **Amended 2026-10-04 by [ADR 0007](0007-narrower-v01-hook-policy.md):** the
  registered set is narrowed to nine hooks; `beforeShellExecution`,
  `afterShellExecution` and `afterFileEdit` are no longer registered. The list in this
  bullet is the original plan and is kept for the record.
- Drop `user_email`, `transcript_path` and all content fields at the parser
  boundary, before any write.
- Local sessions only; state that cloud agents and cloud subagents are not seen.
- No token budgets in the UI.

### Decisions that are PROVISIONAL until the spike is run

- Runtime directory at `<git-common-dir>/cursorfleet/` shared across worktrees
  (needs Q4; the kit's own capture dir is the first test of this).
- Event schema mapping `subagent_id` to `agent_instance_id`, `subagent_type`
  to `agent_role`, `agent_id` derived (needs Q1 and Q2; if tool hooks carry no
  subagent identity, per-agent timelines in v0.1 can only be derived from
  temporal windows, worktree identity or self-reported artifacts).
- Pairing `subagentStop` to `subagentStart` (docs list no `subagent_id` on
  stop; pairing may need type plus ordering or a transcript reference).
- Coordinator as the main agent driven by a rule or skill (section A7 caveat).
- Hot-path latency budget and the per-OS claim (Linux cold start measured;
  macOS, Windows and in-Cursor overhead not).
- Spool layout: one append file versus per-conversation or per-subagent files
  (needs Q5).
- Any statement that hooks work under the Cursor CLI or in Agents Window
  worktrees (Q3). README and `doctor` must not claim it until confirmed.
- Using `ask` on `beforeShellExecution` in v0.2 (behaviour unobserved).
- Contract-test fixtures: none exist. Only doc-derived examples; real fixtures
  must come from a reviewed capture stamped with `cursor_version`.

## Consequences

- Positive: v0.1 scope is bounded by what Cursor documents, privacy exposure is
  minimised by not registering content-bearing hooks, and a ready capture kit
  can turn the unknowns into evidence in one session per surface.
- Negative: M0b schemas for `agent_instance_id`, `agent_role` and the worktree
  collector should stay draft until the spike results are recorded here.
- Follow-ups (owner: project owner): run `spike/README.md` on IDE, Agents
  Window and CLI; run `bench_latency.py` on macOS and Windows; update this ADR
  (move items from B to A with `cursor_version`, or supersede with ADR 0002);
  commit reviewed, sanitized fixtures.

## Alternatives considered

- Register every hook and rely on allowlisting: rejected, because the content
  would still reach our process (plan section 2).
- Hand-write fixtures from the docs: rejected for contract tests, because docs
  and real payloads drift; allowed only as clearly labelled doc-derived examples.
- Make the Coordinator a subagent: not adopted, see A7 caveat; revisit after Q1.
