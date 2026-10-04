# ADR 0006: Agent-declared events via Markdown artifacts

- Status: provisional (amended 2026-10-04: TOML frontmatter, artifact identity and digest)
- Date: 2026-10-04
- Deciders: project owner (M9nx)
- Evidence level: verified-from-docs for the gap; assumption for agent compliance
- Supersedes: none (the YAML-subset parser design in this ADR's first version is replaced in place while the ADR is provisional)
- Superseded by: none
- Related ADRs: 0003 (event model, `source=self_reported`), 0009 (the kit writes the rule and skill that teach this format), 0011 (evidence tiers), 0010 (how artifact events enter the reducer)
- Implementation status: **Divergent-from-code.** The code parses a strict YAML subset between `---` fences (`workflow/frontmatter.py`), validates `schema: cursorfleet.artifact/1` (`workflow/artifacts.py`), has no `artifact_id`, `revision` or `digest`, dedupes by path plus a SHA-256 of the frontmatter (`state/artifact_scan.py`), and the templates teach the YAML form. `cursorfleet emit` is not implemented. The self-reported labelling and the model's rejection of observed or self-reported mixups are implemented.
- Review trigger: evidence that agents ignore the convention, a spike result on rule/skill loading (the rule, skill and nested `AGENTS.md` loading test in the empirical test plan), or any proposal to let an artifact count as evidence
- Release gate: TOML frontmatter parsed with `tomllib`, `artifact_id`, `revision` and digest implemented and tested; templates and docs describe the TOML format; artifact events verified ineligible as gate evidence in code (ADR 0011); `schema` id on the 0.1 versioning rule (ADR 0003)

## Context

Verified from docs (ADR 0001 A9): hooks give tool telemetry only. Nothing reports plans,
handoffs, blockers or which rules, skills or AGENTS.md files were loaded. These need a
producer, and anything an agent says about itself is unverified.

## Decision

- **Primary: Markdown plus TOML-frontmatter artifacts** under `.cursorfleet/work/<task>/`,
  written by agents following the generated rules and skills. They are git-friendly and
  human-editable, so manual contribution works. File kinds: `plan`, `handoff`, `blocker`,
  `context`, each with a frontmatter `kind` of `plan.created`, `handoff.created`,
  `blocker.raised` or `context.loaded`. File name:
  `<NN>-<kind>-<author_role>.md`.
- **Frontmatter is TOML**, delimited by `+++` lines at the very top of the file, parsed
  with the standard library `tomllib` (Python 3.11+, already the project minimum). This
  replaces the home-grown YAML-subset parser design: a maintained stdlib parser, no
  duplicate-key or quoting special cases of our own, no YAML features. The body is free
  Markdown and is never copied into events.
  ```
  +++
  schema = "cursorfleet.artifact/0.1"
  kind = "handoff.created"
  task = "add-login-form"
  artifact_id = "handoff-add-login-form-01"
  revision = 1
  digest = "blake2s:<64 hex>"
  author_role = "implementer-alpha"
  created = 2026-10-04T12:00:00Z
  to_role = "reviewer"
  issue_ref = "#123"
  context_refs = ["src/app/login.py", "tests/test_login.py"]
  +++
  Free-form Markdown body.
  ```
- **Fields.** Required: `schema`, `kind`, `task`, `artifact_id`, `revision`, `author_role`,
  `created`. Optional: `digest`, `to_role`, `issue_ref`, `context_refs` (workspace-relative
  paths, at most 50). Flat keys only (no tables, no inline tables of tables). Unknown keys
  fail validation. Frontmatter is capped at 16 KiB and the file at 64 KiB. Strings are
  validated as printable and bounded before display.
- **`artifact_id`** is a stable identifier chosen once at creation (SafeId pattern, unique
  within a task) that does not change across revisions. Two files with the same
  `artifact_id` are revisions of one artifact.
- **`revision`** is an integer starting at 1, incremented on each substantive edit. The
  indexer shows the highest revision per `artifact_id`. Two files with the same
  `artifact_id` and `revision` but different digests are reported as a conflict.
- **`digest`** is `blake2s:` plus 64 lower-case hex characters. Algorithm: BLAKE2s with a
  32-byte digest over, in order, the ASCII tag `cursorfleet.artifact.digest/0.1` and a NUL
  byte; the canonical frontmatter (all keys except `digest`, as UTF-8 JSON with sorted
  keys, `,` and `:` separators and `ensure_ascii`), preceded by its length as 8 bytes
  big-endian; then the body as UTF-8 with CRLF and CR normalised to LF. The digest must be
  recomputed on **every** edit to the body or any frontmatter field other than `digest`,
  together with the `revision` bump.
  - The indexer always computes the digest itself and uses it for deduplication, whether or
    not the file declares one. A declared digest that does not match the computed one is
    a `digest_mismatch` problem: the artifact is still shown (as self-reported) with
    the problem flagged, because hand edits are the supported way to correct a file.
  - The digest is an integrity and de-duplication aid. It is **not authentication**: anyone
    who can edit the file can recompute it. Agents cannot compute BLAKE2s reliably, so
    sealing a file is meant to be done by tooling (`validate` printing the expected digest
    and a planned `--seal` option); until that exists the field is optional.
- **Indexing:** the indexer (not a hook) scans the work directory read-only, validates size,
  frontmatter and paths, then emits events with `producer=work_artifact`,
  `source=self_reported`, `attribution=unknown`, deduplicated by
  `(artifact_id, revision, computed digest)`. `cursorfleet validate` runs the same checks.
- **Fallback: `cursorfleet emit <kind> ...`** for agents that cannot write files sensibly.
  It appends a `producer=emit_cli`, `source=self_reported` event to the spool. Allowed
  kinds: `plan.created`, `handoff.created`, `blocker.raised`, `context.loaded`,
  `status.changed`. Free-text options do not exist. **Not implemented**; v0.2 candidate.
- **MCP server deferred to v0.2** (typed tools, optional install).
- **All artifact events are self-reported and ineligible as gate evidence.** The TUI
  marks them "self-reported". The event model rejects a self-reported tool, file or subagent
  event and an observed `plan.created`, `handoff.created`, `blocker.raised` or
  `context.loaded`. Neither `revision` nor `digest` changes that: a forged artifact with a
  valid digest is still a forgery (evidence tiers: ADR 0011).
- Untrusted: artifacts can be forged by a malicious or prompt-injected agent, including
  `author_role` and `artifact_id`.

### Schema id and versioning

- The schema id moves from `cursorfleet.artifact/1` to `cursorfleet.artifact/0.1`, in line
  with the 0.1 versioning rule of ADR 0003: no compatibility promise before the first
  public release. Files written with `/1` become invalid and must be rewritten; there are
  no users yet. A migration note belongs in the first release's changelog, not before.

### What stays YAML

Cursor's own file formats keep Cursor's frontmatter: `.cursor/agents/*.md`,
`.cursor/rules/*.mdc` and `SKILL.md` use YAML frontmatter, which the kit generates and
`validate` checks with the existing small YAML-subset reader. That reader is no longer used
for artifacts. Artifacts are CursorFleet's own files under `.cursorfleet/work/`; Cursor does
not load them as rules, so the choice of TOML does not affect Cursor tooling.

### Documentation and templates

This decision changes how artifacts are described in `docs/kit.md`, `docs/governance.md`
and `docs/tui.md` (updated in the docs pass) and in the generated templates
(`templates/cursor/skills/cursorfleet-artifacts/SKILL.md`,
`templates/cursor/skills/cursorfleet-coordinator/SKILL.md`,
`templates/cursor/rules/cursorfleet-handoff.mdc`, `templates/cursor/agents-md/work.md`,
`templates/cursor/agents/architect.md`). The templates are **described here, not edited**;
they still teach the YAML form until the follow-up.

## Implementation status

**Divergent-from-code.** The code and templates implement the first version of this ADR.
A follow-up (after the spike, see [`../follow-ups.md`](../follow-ups.md)) must change:

- `src/cursorfleet/workflow/frontmatter.py` and `workflow/artifacts.py`: `+++` fences,
  `tomllib`, new required fields, new schema id, digest computation and comparison.
- `src/cursorfleet/state/artifact_scan.py`: dedupe key and revision handling (today the
  fingerprint is a SHA-256 of path plus frontmatter text).
- `src/cursorfleet/adapters/cursor/kit.py`, `src/cursorfleet/tui/data.py`,
  `src/cursorfleet/tui/views.py`: references to fields and the schema id.
- The five template files listed above.
- Tests: `tests/unit/test_artifact_scan.py`, `tests/unit/test_kit_frontmatter.py`,
  `tests/security/test_hostile_repo.py`, `tests/tui/test_tui_privacy.py`,
  `tests/tui_helpers.py`, `tests/integration/test_kit_doctor_validate.py`.

## Consequences

- Positive: no new dependency or server; a stdlib parser; auditable in git; works without
  hooks; revisions and duplicates are distinguishable.
- Negative / costs: agents may ignore or misuse the convention; role claims are spoofable;
  agents cannot compute a digest, so it is optional until tooling exists; two frontmatter
  syntaxes exist in the repository (YAML for Cursor files, TOML for artifacts).
- Follow-ups: the implementation list above; sealing tooling.

## Open questions

- Do agents reliably follow the artifact convention without enforcement?
- Does `tomllib` cope with TOML written by an LLM (quoting, dates)? A conformance check on
  real agent output belongs in the spike.
- Is a `--seal` option enough, or do artifacts need a `cursorfleet artifact` command group?

## Alternatives considered

- Strict YAML-subset frontmatter with our own parser (the first version of this ADR):
  replaced; it is more code to maintain and review than `tomllib`.
- Full YAML via a library: rejected, dependency and unsafe features.
- JSON frontmatter: rejected, hostile to hand editing and quoting for LLMs.
- `cursorfleet emit` as primary: needs the binary on PATH inside Cursor's shell and quoting
  care on Windows. Kept as fallback.
- Local MCP server first: typed and robust but heavy and an extra moving part. v0.2.
- Parse agent responses or transcripts: forbidden by ADR 0007 and the privacy rules.
