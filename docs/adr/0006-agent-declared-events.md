# ADR 0006: Agent-declared events via Markdown artifacts

- Status: provisional
- Date: 2026-10-04
- Deciders: project owner (M9nx)
- Evidence level: verified-from-docs for the gap; assumption for agent compliance

## Context

Verified from docs (ADR 0001 A9): hooks give tool telemetry only. Nothing
reports plans, handoffs, blockers or which rules, skills or AGENTS.md files were
loaded. These need a producer, and anything an agent says about itself is
unverified.

## Decision

- **Primary: Markdown plus frontmatter artifacts** under
  `.cursorfleet/work/<task>/`, written by agents following the generated rules and
  skills (M1). They are git-friendly and human-editable, so manual contribution
  works. Planned file kinds: `plan`, `handoff`, `blocker`, `context`, each with a
  frontmatter `kind` of `plan.created`, `handoff.created`, `blocker.raised` or
  `context.loaded`.
- **Frontmatter:** a strict YAML subset (flat scalar keys and lists of
  scalars) parsed by our own small stdlib parser, to avoid a YAML dependency and
  its unsafe features. Fields: `schema`, `kind`, `task`, `author_role`,
  `created`, optional `to_role`, `issue_ref`, `context_refs` (workspace-relative
  paths). Unknown keys fail validation. The body is free Markdown and is never
  copied into events.
- **Indexing:** the indexer (not a hook) scans the work directory, validates
  size (capped), frontmatter and paths, then emits events with
  `producer=work_artifact`, `source=self_reported`, `attribution=unknown` or
  `inferred`, deduplicated by path plus frontmatter hash. `cursorfleet validate`
  runs the same checks, and editing files is the supported way to correct them.
- **Fallback: `cursorfleet emit <kind> ...`** for agents that cannot write files
  sensibly. It appends a `producer=emit_cli`, `source=self_reported` event to the
  spool. Allowed kinds: `plan.created`, `handoff.created`, `blocker.raised`,
  `context.loaded`, `status.changed`. Free-text options do not exist; it takes
  ids, a role, an artifact path and an optional `issue_ref`.
- **MCP server deferred to v0.2** (typed tools, optional install).
- **Labelling:** every such event has `source=self_reported`; the TUI marks it
  "self-reported" and never counts it as evidence for a gate. The event model
  rejects a self-reported tool, file or subagent event, and an observed
  `plan.created`/`handoff.created`/`blocker.raised`/`context.loaded`.
- Untrusted: artifacts can be forged by a malicious or prompt-injected agent,
  including `author_role`. Frontmatter strings are validated as printable and
  bounded before display.

## Consequences

- Positive: no new dependency or server; auditable in git; works without hooks.
- Negative / costs: agents may ignore or misuse the convention; role claims are
  spoofable; needs a custom frontmatter parser.
- Follow-ups: parser and validator in M1/M2; rule and skill templates telling
  agents where and how to write artifacts.

## Open questions

- Do agents reliably follow the artifact convention without enforcement?
- Is a YAML subset acceptable to Cursor rule/agent tooling, or should artifacts
  use TOML frontmatter?

## Alternatives considered

- `cursorfleet emit` as primary: needs the binary on PATH inside Cursor's shell and
  quoting care on Windows. Kept as fallback.
- Local MCP server first: typed and robust but heavy and an extra moving part. v0.2.
- Parse agent responses or transcripts: forbidden by ADR 0004.
