# ADR 0004: No chain-of-thought; never register content hooks

- Status: accepted
- Date: 2026-10-04
- Deciders: project owner (M9nx)
- Evidence level: verified-from-docs

## Context

Verified from docs (ADR 0001 A11, fetched 2026-10-04):

- `afterAgentThought` delivers thinking text, `afterAgentResponse` the assistant
  text, `beforeSubmitPrompt` the user prompt, `beforeReadFile` full file contents.
- A registered hook receives its payload in memory even if the code discards it.
- Base fields on every hook include `user_email` and `transcript_path`.
- The hooks CursorFleet needs for observation (12 passive ones) carry some
  sensitive fields too (`afterShellExecution.output`, `afterFileEdit.edits`).

## Decision

- We will never register `afterAgentThought`, `afterAgentResponse`,
  `beforeSubmitPrompt` or `beforeReadFile` in v0.1. They are listed in
  `FORBIDDEN_HOOKS` (`cursorfleet/adapters/cursor/hook_policy.py`).
- `ALLOWED_V01_HOOKS` is the only list the installer may draw from: the 12 hooks
  `sessionStart`, `sessionEnd`, `preToolUse`, `postToolUse`, `postToolUseFailure`,
  `subagentStart`, `subagentStop`, `beforeShellExecution`, `afterShellExecution`,
  `afterFileEdit`, `preCompact`, `stop`. The two sets must stay disjoint (tested).
- Also unregistered in v0.1: `beforeTabFileRead`, `afterTabFileEdit`,
  `beforeMCPExecution`, `afterMCPExecution`, `workspaceOpen`
  (`UNREGISTERED_V01_HOOKS`).
- The installer must never emit a hook outside `ALLOWED_V01_HOOKS`, and a test
  asserts generated `hooks.json` never contains a forbidden name. The config
  model cannot represent a forbidden hook, so config cannot request one.
- The event model has no thought, prompt or response kind or field, and
  `events/forbidden.py` lists payload fields that no model may declare.
- CursorFleet never opens `transcript_path` or `agent_transcript_path` and never
  ingests Cursor message text. Headless `stream-json` ingestion is deferred
  (v0.2) because it carries message text.
- `doctor` reports content-bearing hooks registered by other sources (user,
  team, enterprise, third-party) as a warning; we cannot and do not remove them.
- Adding a content hook later requires a superseding ADR, a threat-model
  update and a privacy-doc update.
- For the registered hooks that carry sensitive fields, narrow `matcher`
  values, drop fields at the parser boundary, and prefer `postToolUse`
  data (exit code, duration) where it suffices.
- Fail-open replies: `{}` for non-permission hooks and `{"permission":"allow"}`
  for `preToolUse`, `subagentStart` and `beforeShellExecution` (Cursor treats
  invalid permission-hook output as a block). PROVISIONAL: classification comes
  from the docs only. This refines the shorthand "exit 0 with `{}`" in AGENTS.md.

## Consequences

- Positive: thinking, prompts, responses and file contents never reach our
  process; the privacy claim does not depend on parser correctness.
- Negative / costs: no "why did the agent do that" view; shell output and edit
  strings still reach the hook in memory.
- Follow-ups: installer test in M1; update AGENTS.md wording on fail-open replies.

## Open questions

- Does Cursor deliver extra fields on registered hooks that the docs omit? Real
  captures decide; the allowlist ignores unknown fields regardless.

## Alternatives considered

- Register everything and allowlist: rejected, content still reaches the process.
- Opt-in thought capture: rejected for v0.1; revisit only with explicit consent design.
