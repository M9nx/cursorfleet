# ADR 0003: Event model and sanitization allowlist

- Status: provisional (agent identity fields depend on the spike; amended 2026-10-04 by the architecture owner)
- Date: 2026-10-04
- Deciders: project owner (M9nx)
- Evidence level: verified-from-docs for payload fields; assumption for identity behavior
- Supersedes: none
- Superseded by: none
- Related ADRs: 0001 (Q1, Q2), 0006 (self-reported events), 0007 (which hooks feed events), 0010 (reducer), 0011 (evidence tiers)
- Implementation status: Divergent-from-code. Event schema is `"1.0"` not `"0.1"`; the reducer aggregates `attribution` to the strongest value instead of the weakest (the role-only to `inferred` mapping in the normalizer already matches the amended rule); `test.completed` exists and feeds TUI gates; command display defaults to ON. Details in "Amendment 2026-10-04" below. The hook to kind mapping for shell and file-edit hooks is narrowed by ADR 0007.
- Review trigger: Q1 or Q2 answered; the first real fixture is committed; any change to the closed kind list
- Release gate: schema version `0.1` in code and schemas; `verification.observed` replaces `test.completed`; no gate derived from heuristic events; command display default OFF; attribution never shows an inferred value as exact; privacy and forbidden-field tests green against real fixtures

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
`"1.0"` (**amended: it becomes `"0.1"` until the first public release, see below**).
Readers skip and count events with an unknown version instead of failing.

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
  gracefully if Q1 is refuted. The meanings are fixed in "Amendment 2026-10-04",
  section 2: a role-only identity is never `exact`.
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

**Hook to kind mapping (PROVISIONAL, finalized in M2; the shell and file-edit rows are
removed by ADR 0007):** `sessionStart` and
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

## Amendment 2026-10-04 (architecture-owner decisions)

These decisions override the text above where they conflict. The divergences from the code
are real and are not fixed by this documentation pass; see
[`../follow-ups.md`](../follow-ups.md).

### 1. Schema version is 0.1 until the first public release

- `schema_version` is `"0.1"` for events, and the same rule applies to every
  CursorFleet-owned versioned document (config, roster, artifact, and the `status`,
  `doctor`, `validate` and `replay` output ids, written `cursorfleet.<name>/0.1`).
- No breaking-change promise exists before the first public release: fields may be added,
  removed or retyped without upcasters. The project owner decides at release whether the
  first public version is `1.0` or stays `0.x`, and records a migration note then.
- Readers still skip and count events with an unknown version. Local spools written with
  `"1.0"` become `unknown_version` after the change; they are pre-release scratch data and
  the projection rebuilds.
- Implementation status: **Divergent-from-code.** `"1.0"` appears in
  `events/kinds.py:SCHEMA_VERSION`, `events/models.py`, `adapters/cursor/hook_normalize.py`,
  `config/models.py`, `config/roster.py`, `schemas/*.schema.json`,
  `templates/cursor/config/config.toml`, `adapters/cursor/kit.py`, and the `/1` ids
  (`cursorfleet.status/1`, `cursorfleet.artifact/1`, `cursorfleet.doctor/1`,
  `cursorfleet.validate/1`, `cursorfleet.replay/1`), pinned by
  `tests/fixtures/status/status.v1.golden.json`.

### 2. Attribution never overstates identity

- The canonical `attribution` enum is exactly `exact | inferred | unknown`, with these
  meanings. No other value exists in docs, schemas or code:
  - `exact`: a **unique current agent instance** is directly identified by the event's own
    payload (for example `subagent_id` on a tool hook inside that subagent), or is
    deterministically linked to the event through an ID relationship that has been
    empirically verified (for example a tool-hook id that equals exactly one
    `subagentStart.subagent_id`, once the spike has shown that it does).
  - `inferred`: the identity is a best guess from something weaker than a unique instance
    id: a **role only** (`subagent_type` with no instance id), timing or a window ("this
    tool call happened while subagent X was open"), worktree, branch, ordering, or
    self-report.
  - `unknown`: parent-only identity (`parent_conversation_id`, or the parent's
    `conversation_id` on a tool hook) or no defensible association with a child agent. This
    is the default.
- **A role-only identity is NEVER `exact`.** Two concurrent subagents of one type are
  indistinguishable by role, so a role claim cannot name an instance. It is `inferred`, with
  `agent_role` set and `agent_instance_id` absent. (This replaces the earlier wording that
  let `subagent_type` count as `exact` with the instance left absent.)
- **Parent identity never makes a child `exact`.** It can at most support `unknown`.
- Temporal attribution uses `attribution = inferred`. CursorFleet v0.1 does not emit
  temporal attribution: the reducer never attributes unattributed events to a running
  subagent by timing (ADR 0010). There is no temporal-specific enum value anywhere; the enum has exactly three members.
- **Possible future field (not implemented, not part of v0.1):** if a consumer ever needs to
  tell role-only from temporal from worktree inference, add a **separate** optional
  `attribution_method` field (a closed enum such as `role | temporal | worktree | ordering |
  self_report`) next to `attribution`. The `attribution` enum itself must not grow.
- An `inferred` value is never rendered as exact in the TUI, in `status --json` or in
  `events export`. JSON carries the literal enum value. Wherever the TUI explains an
  `inferred` value in words it must say which basis applies; in v0.1 the only emitted basis
  is "role only; instance not identified".
- Aggregation takes the **weakest** value an agent entry has absorbed (order from weakest:
  `unknown`, `inferred`, `exact`) and the JSON also exposes per-value counts; it never
  upgrades an entry to the strongest value seen.
- How ADR 0001 Q1 outcomes map onto this enum: CONFIRMED gives `exact`, PARTIAL (role only)
  gives `inferred`, REFUTED (parent only or nothing) gives `unknown`, and OPEN (ambiguous or
  undocumented fields) gives `unknown` until classified. All of that is unobserved today.
- Implementation status: **Partly implemented, partly divergent-from-code.** The enum is
  `exact | inferred | unknown` (`events/kinds.py:Attribution`), as required. The hook
  normalizer (`hook_normalize.py:_identity`) sets `exact` when the payload has a
  `subagent_id` and `inferred` when it has only a `subagent_type`; the role-only case now
  matches this rule. It does not read `parent_conversation_id` at all, so parent identity
  cannot make an event `exact`. Remaining divergences:
  - `_identity` marks any payload with a `subagent_id` as `exact` for every hook it runs on.
    That is right for `subagentStart` (the id names the instance that started) but whether a
    `subagent_id` on a tool hook is the *current* instance is exactly Q1, and is unverified.
  - The reducer keeps the **strongest** rank seen (`reducer.py:_touch_agent`,
    `_ATTRIBUTION_RANK`), so one exact `subagentStart` can make an agent entry read `exact`
    while its tool events are `unknown`. The rule above requires weakest-wins and per-value
    counts, which are not implemented.
  - Words and comments still describe the old model: the `Attribution` docstring and comment
    on `INFERRED` (`events/kinds.py`: "temporal window, worktree or `tool_use_id` linkage"),
    and `tui/views.py:_attr_explain` ("linked by tool_use_id or worktree"), neither of which
    mentions role-only.
  - `status.json` and the TUI print the bare enum value without per-value counts.
  Q1 and Q2 may change all of this. Tracked as task 7 in [`../follow-ups.md`](../follow-ups.md).

### 3. `verification.observed` replaces `test.completed`; heuristic events never satisfy gates

- The kind `test.completed` is removed from the closed enum. It is replaced by
  `verification.observed`: CursorFleet observed a shell tool call that **looks like** a
  verification step (tests, lint, type check, security scan) and records what happened.
- Fields on the event: `command` (class and hash only by default, see 4), `outcome`, and a
  `classification` object with `heuristic` (always `true` in v0.1; the model rejects
  `false`), `method` (the classifier name and version, for example `argv0-subcommand-v1`),
  `confidence` (`low | medium`; never `high` for a heuristic) and `class` (`unit_tests`,
  `integration_tests`, `type_check`, `lint`, `security_checks`, or `unknown_verification`).
  `source` is `derived`.
- **Rule R1: heuristic events never satisfy gates.** A gate may only be satisfied by
  evidence from a deterministic runner bound to a commit SHA, planned for v0.3 (ADR 0011,
  tier 4). In v0.1 no gate can be PASS or FAIL from CursorFleet data. The UI may list
  `verification.observed` events as "observed, heuristic" next to a gate named "not
  evaluated".
- A heuristic may still colour a display hint such as the VERIFYING lane, provided the lane
  basis is shown as heuristic (ADR 0010).
- Reduced by ADR 0007: `afterShellExecution` is no longer registered, so the only source of
  an exit code is `postToolUse` `tool_output`, whose shape is documented by example only and
  is unverified. Where the code is absent, the outcome is `unknown`.
- Implementation status: **Divergent-from-code, and the TUI is in violation of R1.**
  `hook_normalize.py` emits `test.completed` (around the `is_verify_command` call) with
  `source=derived`; `events/kinds.py` lists the kind; `reducer.py` has `_on_test`,
  `last_test` and uses `is_verify_command` for the VERIFYING lane; `status_doc.py` exports
  `last_test`; **`tui/gates.py` turns `test.completed` and `gate.changed` events into PASS,
  FAIL and STALE gate states and the Evidence screen lists them.** That is a gate derived
  from a heuristic and must be fixed in a follow-up. Until then [`../tui.md`](../tui.md)
  labels gate display as heuristic and non-authoritative. Affected tests include
  `tests/unit/test_hook_normalize.py`, `tests/unit/test_reducer.py`,
  `tests/tui/test_tui_gates.py`, `tests/tui/test_tui_app.py` and the status golden file.

### 4. Command display defaults OFF

- By default an event stores only `argv0` (executable basename), `subcommand` (first
  non-flag word for known multi-command tools), `exit_code`, `duration_ms` and `command_hash`
  (HMAC-SHA256 with the per-repo key, with a domain label, truncated; for deduplication).
  No `display` string is stored.
- The redacted, truncated (at most 200 characters) `display` string is **opt-in**:
  `[privacy] store_command_display = true`. Redaction stays best-effort and the docs say so.
  Config can only reduce what is stored from this default, never add content-bearing fields.
- Without display, classification uses `argv0` and `subcommand` only, which lowers
  `classification.confidence`.
- Implementation status: **Divergent-from-code.** `config/models.py` defaults
  `store_command_display` to `True`, `templates/cursor/config/config.toml` writes `true`, and
  `docs/privacy.md` and `docs/threat-model.md` describe display storage as the default.
  `tui/gates.py:classify_command` and `hook_sanitize.is_verify_command` read the display
  string; they must be reworked to run without it.
