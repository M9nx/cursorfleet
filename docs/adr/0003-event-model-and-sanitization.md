# ADR 0003: Event model and sanitization allowlist

- Status: provisional (agent identity fields depend on the spike)
- Date: 2026-10-04
- Deciders: project owner (M9nx)
- Evidence level: verified-from-docs for payload fields; assumption for identity behavior

## Context

Verified from docs (ADR 0001 section A5 and A11): base hook fields are
`conversation_id`, `generation_id`, `model*`, `cursor_version`, `workspace_roots`,
`user_email`, `transcript_path`. Only `subagentStart` documents `subagent_id`,
`subagent_type` and `parent_conversation_id`; `subagentStop` documents
`subagent_type` but no `subagent_id`. Registered hooks carry sensitive content
fields in memory.

Unverified (ADR 0001 Q1, Q2): whether tool hooks inside a subagent identify it;
how custom subagent names appear in `subagent_type`.

## Decision

The Pydantic models in `cursorfleet.events.models` are the source of truth;
`schemas/event.schema.json` is generated from them. Event `schema_version` is
`"1.0"`. Readers skip and count events with an unknown version instead of failing.

**Field map**

- `conversation_id` to `session_id`; `generation_id` kept.
- `subagent_id` to `agent_instance_id` (optional).
- `subagent_type` to `agent_role` (optional): the roster id when the type is the
  prefixed Cursor name or bare id of a roster agent, else the raw value
  (for example `generalPurpose`).
- `agent_id` derived as `role#instance`, `role`, or absent; if supplied it must
  equal the derived value.
- `attribution` (`exact | inferred | unknown`, default `unknown`) records how
  firmly the event is tied to an agent. Added beyond the plan to degrade
  gracefully if Q1 is refuted.
- `cursor_version`, `producer_version` stamped on every event so `doctor` can
  warn about unvalidated Cursor versions.
- `source`: `observed` (hook payload), `self_reported` (agent artifact or emit
  CLI), `derived` (computed by CursorFleet). `plan.created`, `handoff.created`,
  `blocker.raised` and `context.loaded` must be `self_reported`; only those plus
  `status.changed` may be.

**Kinds (v0.1, closed enum):** `session.started`, `session.stopped`,
`status.changed`, `tool.started`, `tool.completed`, `tool.failed`, `file.changed`,
`test.completed`, `subagent.started`, `subagent.stopped`, `context.compacted`,
`plan.created`, `handoff.created`, `blocker.raised`, `gate.changed`,
`context.loaded`. There is no thought, prompt or response kind.

**Hook to kind mapping (PROVISIONAL, finalized in M2):** `sessionStart` and
`sessionEnd` to `session.started`/`stopped`; `stop` to `status.changed`;
`preToolUse` to `tool.started`; `postToolUse` to `tool.completed`;
`postToolUseFailure` to `tool.failed`; `subagentStart`/`subagentStop` to
`subagent.started`/`stopped`; `afterFileEdit` to `file.changed`; `preCompact` to
`context.compacted`. Shell hooks refine `tool.*` with a command; which of
`preToolUse` and `beforeShellExecution` is canonical for Shell is decided in M2
to avoid duplicates. `test.completed` and `gate.changed` are `derived`.

**Allowlist.** Each registered hook has an explicit list of payload fields the
parser reads; everything else is dropped, never copied through (no `**payload`).
Never read or persisted: `user_email`, `transcript_path`,
`agent_transcript_path`, `workspace_roots` (used only to relativize paths),
`cwd`, `tool_input`, `tool_output`, `output`, `edits`, `task`, `summary`,
`description`, `error_message`, `modified_files`, env. The list is in
`events/forbidden.py` and no model field may share a name with it.

**Commands** become `SanitizedCommand`:

- `argv0`: executable basename.
- `subcommand`: first non-flag word for known multi-command tools, else absent.
- `exit_code`, `duration_ms`.
- `display`: single-line, at most 200 characters, redacted then truncated
  (`display_truncated` set). Redaction covers `KEY=value` assignments, URL
  userinfo, values after secret-looking flags (`--token`, `--password`,
  `--api-key`) and long high-entropy tokens. Best effort, optional via config.
- `command_hash`: HMAC-SHA256 over the normalized argv with the per-install key
  (`hmac.key`), truncated; for dedupe, not identification across installs.

**Paths** become `SanitizedPath`: resolve symlinks, make relative to the matching
workspace root with `/` separators; anything outside every root, or not
representable (backslashes, non-printable characters), becomes `<external>`.
Case folding on Windows/macOS is applied only for root matching.

**Strictness.** All models use `extra="forbid"` and are immutable; strings are
pattern-bound, printable (control and bidi-override characters rejected) and
length-capped; counters are strict non-negative integers; timestamps are
timezone-aware. `event_id` is a stdlib ULID-style id (48-bit ms + 80 random bits).

**Beyond the plan (flagged):** `producer` enum, `risk` (informational, default
`none`), `outcome`, `status`, `tool_name`, `gate`, `metrics`. No free-text
fields exist, so a blocker or plan is referenced by artifact `paths` and
`issue_ref`, not copied.

**Versioning.** Any field change bumps `schema_version`; readers keep upcasters
for earlier versions. The hot path re-implements validation with the stdlib and
is contract-tested against the models.

## Consequences

- Positive: forbidden data has no field to live in; schema is generated and
  drift-tested.
- Negative / costs: two validators (models and hot path) must be kept in sync;
  no free text limits TUI richness for plans and blockers (artifacts hold it).
- Follow-ups: finalize identity fields and the hook mapping after Q1/Q2; real
  fixtures stamped with `cursor_version`.

## Open questions

- Q1/Q2 outcomes may drop or reshape `agent_instance_id`, `agent_role`, `attribution`.
- How to pair `subagentStop` with `subagentStart` without `subagent_id`.
- Whether `Task`'s `tool_use_id` equals `subagentStart.tool_call_id` (a linkage candidate).

## Alternatives considered

- Pass-through dict payloads with a deny-list: rejected, new Cursor fields would leak by default.
- Free-text `message`/`label` on events: rejected, invites prompt and secret leakage.
- Store raw commands in an encrypted column: rejected, adds key management for little value.

## Addendum (M2, implemented)

- **Two additive optional fields**, `tool_use_id` (opaque SafeId) and `hook` (the Cursor
  `hook_event_name`), were added to `Event`. They let the reducer pair started/completed
  tool events, keep the candidate `Task` to `subagentStart` link, and de-duplicate
  overlapping hooks. `schema_version` stays `"1.0"` because the change is additive and
  optional and no release has shipped; after the first release a field change bumps it.
- **Hook to kind mapping (final):** `sessionStart` to `session.started`; `sessionEnd` to
  `session.stopped`; `stop` to `status.changed` (`waiting` when `status` is `completed`,
  `idle` on `aborted`, `error` on `error`, otherwise `unknown`); `preToolUse`, `postToolUse`, `postToolUseFailure`
  to `tool.started`/`completed`/`failed`; `beforeShellExecution`/`afterShellExecution` to
  `tool.started`/`completed` with tool `Shell`; `afterFileEdit` to `file.changed`;
  `preCompact` to `context.compacted`; `subagentStart`/`subagentStop` to
  `subagent.started`/`stopped`.
- **Shell de-duplication (decided).** `preToolUse`/`postToolUse` are canonical for every
  tool including Shell. The shell hooks are still recorded (they carry `hook`) and the
  reducer counts a Shell call once: `tool_call_count` uses the `beforeShellExecution`
  count only when no `preToolUse` Shell call was seen.
- **`test.completed`** is emitted as `derived` by the normalizer next to a
  `postToolUse`/`postToolUseFailure` of a Shell command that looks like a test, lint or
  type-check run (`is_verify_command`, a heuristic over argv0/subcommand).
- **Exit code.** Only an integer `exitCode` in a Shell `tool_output` JSON string is read;
  nothing else of `tool_output` is. PROVISIONAL: the shape is documented by example only.
- **Redaction order** (`hook_sanitize`): PEM private keys; `Authorization`/cookie/API-key
  headers; JSON secret keys; URL userinfo and secret query parameters; known token
  formats; e-mail addresses (except `git@`); then per token: `NAME=value`, secret-looking
  flags and the next word, `-u user:pass` for curl-like tools, the word after `Bearer`, and
  long high-entropy strings. 40 and 64 hex characters are kept (commit ids, digests).
  Unknown formats can still slip through: that is why the display can be switched off and
  why the whole command is never stored.
- **Privacy knobs read by the hot path:** `[privacy] store_command_display`,
  `hash_commands`, `command_display_max_chars` and `[retention] max_session_mb`. Any parse
  problem turns the display off (it fails toward storing less).
- **Still PROVISIONAL:** Q1 (tool hooks identifying the subagent), Q2 (`subagent_type`
  naming), pairing `subagentStop` with `subagentStart` by role then start time versus
  `duration_ms`, `workspace_roots` inside worktrees, and `session_id` equal to
  `conversation_id` for subagents.
