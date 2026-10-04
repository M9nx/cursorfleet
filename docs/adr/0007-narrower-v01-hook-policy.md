# ADR 0007: Narrower v0.1 hook policy

- Status: accepted (the nine-hook set is provisional until the spike confirms payloads and the permission-hook reply)
- Date: 2026-10-04
- Deciders: project owner (M9nx), architecture-owner decision
- Evidence level: verified-from-docs (ADR 0001 A1, A2, A3, A11); the reply shape and payload contents are unverified
- Supersedes: 0004
- Superseded by: none
- Related ADRs: 0001, 0003 (event mapping), 0004 (superseded), 0008 (fail-open, enforcement), 0009 (installer emits only this set), 0011 (evidence tiers)
- Implementation status: **Divergent-from-code.** `hook_policy.py` `ALLOWED_V01_HOOKS`, the default config, the config schema and the hook normalizer still register and handle 12 hooks, including `beforeShellExecution`, `afterShellExecution` and `afterFileEdit`. File list under "Implementation status" below. Not changed by this documentation pass.
- Review trigger: spike result on any of: permission-hook reply shape, `postToolUse` payload contents for Shell and write tools, `Task` linkage, or a Cursor release that changes hook semantics
- Release gate: the installer registers exactly the nine hooks below and no others; a test asserts the exact set; the permission-hook reply for `preToolUse` and `subagentStart` is confirmed against a live Cursor

## Context

Verified from the Cursor docs (ADR 0001, fetched 2026-10-04):

- `beforeShellExecution` and `afterShellExecution` carry the command text, and
  `afterShellExecution` carries the full command output (A11).
- `afterFileEdit` carries the file path and the old and new edit strings (A11).
- `beforeShellExecution` is a permission hook: invalid or schema-mismatching output blocks
  the action (A2, A3).
- `preToolUse` is a permission hook whose `ask` is accepted by the schema but not enforced;
  `subagentStart` treats `ask` as `deny` (A2).
- `preToolUse`, `postToolUse` and `postToolUseFailure` already fire for every tool type,
  including `Shell` and `Write` (A3, matchers).

Unverified (must be answered by the spike):

- That `{"permission":"allow"}` is the reply Cursor accepts from a hook that wants to do
  nothing (ADR 0001 section B and the release checklist).
- The contents of `postToolUse.tool_output` for Shell, and the path field in `tool_input`
  for write-class tools.

## Decision

We register **exactly nine hooks** in v0.1:

- `sessionStart`
- `sessionEnd`
- `preToolUse`
- `postToolUse`
- `postToolUseFailure`
- `subagentStart`
- `subagentStop`
- `preCompact`
- `stop`

We do **not** register, in v0.1:

- `beforeShellExecution`, `afterShellExecution`, `afterFileEdit`
- `beforeMCPExecution`, `afterMCPExecution`
- `beforeReadFile`, `beforeSubmitPrompt`, `afterAgentResponse`, `afterAgentThought`
- Tab hooks (`beforeTabFileRead`, `afterTabFileEdit`)
- `workspaceOpen`

Of those, the four content hooks (`afterAgentThought`, `afterAgentResponse`,
`beforeSubmitPrompt`, `beforeReadFile`) stay on the forbidden list exactly as in ADR 0004,
and adding any unregistered hook later needs a superseding ADR, a threat-model update and a
privacy update.

Rules that carry over from ADR 0004 unchanged:

- Every registered hook exits 0 and prints the correct fail-open reply: `{"permission":"allow"}`
  for the permission hooks (`preToolUse`, `subagentStart`) and `{}` for the rest.
- The installer may emit only the nine names; the config model cannot represent any other;
  a test asserts the exact set.
- Registered hooks still carry sensitive fields in memory (`tool_input`, `tool_output`,
  `task`, `summary`, `error_message`); the allowlist parser drops them before any write.
- The parser's other duties (no `user_email`, no `transcript_path`, never open transcripts) are
  unchanged.

### Rationale

- **Shell and file payloads carry sensitive content.** `afterShellExecution.output` and
  `afterFileEdit.edits` hand command output and file contents to our process even if we
  discard them. Dropping the hooks removes that exposure, which is stronger than parsing.
- **The permission-hook reply shape is unverified.** Fewer permission hooks means fewer
  places where a wrong reply could block an agent. `beforeShellExecution` is the third
  permission hook and the only one that was not already covered by `preToolUse`.
- **`preToolUse` and `postToolUse` cover tool use**, including Shell and write tools, with
  `tool_name`, `duration` and a result, so the shell hooks are redundant for observation.
  Having both made ADR 0003 add a de-duplication rule; that rule goes away.
- **`ask` is unsupported on `preToolUse`.** There is no v0.1 reason to register a hook for
  its approval semantics, and v0.1 does not enforce (ADR 0008).

### Consequences for what the product can show

- Cannot show: shell output; which lines or files an edit changed; per-edit events from
  `afterFileEdit`; an exit code from `afterShellExecution`.
- Reduced: `file.changed` events exist only if `postToolUse` of a write-class tool carries a
  usable path in `tool_input` (unverified). Otherwise changed files come from the read-only
  git collector (dirty count and status), not from hooks. Test and lint evidence exists only
  as `verification.observed` events (ADR 0003) built from `postToolUse` on Shell, with an
  exit code only if `tool_output` carries one (unverified); outcomes may be `unknown`.
- Unchanged: session and subagent lifecycle, tool-call counts and failures, durations,
  compactions, stop status, worktree and branch state from git.
- The TUI must therefore show "files changed" from git, label tool-derived file events as
  such, and never imply that absence of a `file.changed` event means no edit
  (best-effort telemetry, ADR 0002).

### The spike kit is allowed to be broader

`spike/hooks.json.example` and `spike/hooks.windows.json.example` may keep capturing a
broader diagnostic set, including `beforeShellExecution`, `afterShellExecution` and
`afterFileEdit`. The kit is throwaway, fail-open, runs only in a scratch repository, drops
content at its parser boundary and is documented as such in `spike/README.md`. The broader
set is how the spike learns what those hooks would have added, and it does not change the
product policy. It must still never register the four content hooks.

## Implementation status

**Divergent-from-code.** Today the code, templates and tests encode 12 hooks. A follow-up
(after the spike, see [`../follow-ups.md`](../follow-ups.md)) must change exactly these
files; this pass changes none of them.

- `src/cursorfleet/adapters/cursor/hook_policy.py`: `ALLOWED_V01_HOOKS` (12 to 9), module
  docstring, a new explicit not-registered set for the three removed hooks, and the
  `PERMISSION_HOOKS` comment (`beforeShellExecution` is no longer registrable; the fail-open
  reply for it may stay as a defensive default in `hook_main.py:_EXTRA_PERMISSION_HOOKS`).
- `src/cursorfleet/config/models.py`: `HookName` literal and the default `hooks.enabled`.
- `src/cursorfleet/adapters/cursor/hook_normalize.py`: remove the handlers for
  `beforeShellExecution`, `afterShellExecution` and `afterFileEdit`; `handled_hooks()` must
  equal the nine.
- `src/cursorfleet/adapters/cursor/hook_main.py`, `hooksjson.py`, `installer.py`: comments and
  any references; the installer must remove the three entries from an existing
  `hooks.json` on re-`init` (a repository installed before the change has them), and
  `validate`/`doctor` drift checks must expect the nine.
- `src/cursorfleet/state/reducer.py`: drop the `beforeShellExecution` counting branch
  (`before_shell_calls`) and the Shell de-duplication.
- `src/cursorfleet/events/models.py`: references to the removed hooks.
- `templates/cursor/config/config.toml`: `enabled` list and the "12 passive hooks" comment.
- `schemas/config.schema.json` and `schemas/event.schema.json`: regenerate.
- `scripts/demo.py`: synthetic payloads for the removed hooks.
- Tests: `tests/security/test_hook_policy.py` (asserts `len == 12`), `tests/unit/test_hook_normalize.py`,
  `tests/unit/test_kit_hooksjson.py`, `tests/unit/test_config_models.py`,
  `tests/security/test_kit_installer_policy.py`, `tests/integration/test_kit_init_uninstall.py`,
  `tests/integration/test_hook_main.py`, `tests/integration/test_cli_state.py`,
  `tests/unit/test_reducer.py`, `tests/security/test_hook_privacy.py`,
  `tests/tui/test_tui_privacy.py`, `tests/m2_helpers.py`, `tests/m2_strategies.py`.
- Docs that still say twelve: `docs/quickstart.md`, `docs/architecture.md` (`x12`),
  `CHANGELOG.md`, the `ALLOWED_V01_HOOKS` sentence in `docs/product-contract.md`. This
  documentation pass edits the wording that does not depend on code; remaining occurrences
  are listed in the follow-ups.

## Consequences

- Positive: no command output or edit text reaches our process; one fewer permission hook;
  a smaller hooks.json for teammates; simpler event de-duplication.
- Negative / costs: less direct evidence of file edits and shell results; `file.changed`
  and test evidence are weaker and depend on unverified `postToolUse` payloads; a repository
  that ran the old `init` carries three hook entries that a re-`init` must remove.
- Follow-ups: the implementation list above; spike rows in
  [`../empirical-test-plan.md`](../empirical-test-plan.md).

## Open questions

- Does `postToolUse.tool_output` for Shell expose an exit code? (If not, outcome is `unknown`.)
- Does `tool_input` of write-class tools expose a path we can allowlist?
- Does `preToolUse` fire for MCP tools (`MCP:<tool_name>`) so the omission of the MCP hooks
  loses nothing?
- Is `{"permission":"allow"}` the accepted reply, or does an empty `{}` also work?

## Alternatives considered

- Keep the 12 hooks of ADR 0004: rejected, it receives command output and edit strings and
  adds a third permission hook with an unverified reply shape.
- Register the shell and file hooks with narrow `matcher` values: rejected, the content
  still reaches the process for matching calls and the reply risk is unchanged.
- Drop `subagentStart` too (it is a permission hook): rejected, it is the only source of
  documented subagent identity; kept with the allow reply and flagged as a release gate.
