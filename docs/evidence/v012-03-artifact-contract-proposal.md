# V012-03 proposal — artifact contract decision (ADR 0006)

Status: **DRAFT PROPOSAL for owner decision**, prepared 2026-10-17 — not decided, not
implemented, closes no gate. The v0.1.2 baseline
([`v012-baseline.md`](v012-baseline.md), gate "Artifact contract") requires either a safe
migration implementation or a dated ADR 0006 amendment with an explicit deferral, before
external-alpha sign-off. This memo inventories the shipped truth, lays out the options
with costs, and provides ready-to-fold amendment text so the decision is one signature.

## Code-truth inventory (verified 2026-10-17, `0.1.2.dev0` @ `701b27b`)

| # | Fact | Where |
| --- | --- | --- |
| 1 | The scanner reads **both** syntaxes: `+++` TOML fences via `tomllib` when present, else the `---` strict YAML subset | `workflow/frontmatter.py` (`parse_frontmatter` fence detection) |
| 2 | Both schema ids validate; `cursorfleet.artifact/0.1` additionally requires `artifact_id` (SafeId pattern) and `revision`; legacy `cursorfleet.artifact/1` needs only the original five fields; an optional `digest` key is accepted | `workflow/artifacts.py` (`ARTIFACT_SCHEMAS`, `REQUIRED_KEYS*`) |
| 3 | Deduplication is still `sha256(path + frontmatter)[:16]`; **no** digest verification, **no** revision-based dedupe, no `digest_mismatch` problem | `state/artifact_scan.py` |
| 4 | `cursorfleet emit` is **not implemented** | `cli/commands/` (no command) |
| 5 | The shipped templates teach the **legacy format** (`---` YAML subset, schema `cursorfleet.artifact/1`, five fields) | `templates/cursor/skills/cursorfleet-artifacts/SKILL.md`, `rules/cursorfleet-handoff.mdc` |
| 6 | ADR 0006 contains an internal contradiction: its 2026-10-12 amendment claims "Generated kit templates teach TOML frontmatter", which was **never executed** (item 5); the ADR body's own note says templates "still teach the YAML form until the follow-up" | ADR 0006 vs item 5 |
| 7 | The full implementation (identity, revision, digest, dedupe, template switch) is follow-up task 10, waiting on empirical-test-plan row 14 (rule/skill loading) and a TOML-from-LLM conformance capture | [`follow-ups.md`](../follow-ups.md) task 10 |
| 8 | `.cursorfleet/work/` artifacts are **agent-owned** files; the kit writes only its generated files, so a `migrate artifacts --yes` would create a new write surface the tool deliberately lacks today (ADR 0009 ownership model) | ADR 0009 |
| 9 | Artifact events are self-reported, non-authoritative and never gate evidence; identity and digest would not change that trust tier (tier logic implemented and tested) | ADR 0011, `tui/gates.py` |

Item 6 matters regardless of the decision: a shipped-scope amendment currently asserts a
template state that does not exist. Any v0.1.2 closure must correct it with its own dated
record — either by switching templates (Option C) or by a dated correction of record.

## What the baseline requires of the decision

- **If migration is implemented:** dry-run, safe rewrite, legacy labeling, and rollback
  evidence (baseline P1-3). Practical addition from ADR 0009: user-invoked only, exact
  diff surfaced, per-file atomicity, restore path documented — because the files are
  agent-owned.
- **If deferred:** a dated ADR 0006 amendment, and artifacts explicitly remain
  self-reported and non-authoritative.

## Options

### Option A — implement `cursorfleet migrate artifacts` in v0.1.2

Rewrite existing `.cursorfleet/work/` files from legacy YAML `/1` to TOML `/0.1`
(derive `artifact_id` from kind+task+sequence, `revision = 1`, tool-computed `digest`,
legacy-label any file that fails conversion).

- Guarantees to build: `--dry-run` default with exact diff; `--yes` prompt; per-file
  atomic writes; `.legacy.md` labeling on conversion failures; backup plus documented
  restore (worktrees may not commit `work/`, so git is not assumed as the rollback).
- Cost: parser/scanner/TUI/tests churn (~6 source files, 5 templates, 6 test modules per
  task 10), a new CLI command group (`cli/commands/migrate.py`), packaging evidence
  (dry-run transcript, rewrite proof, rollback proof) — all before V012-04 packaging and
  the privacy/uninstall re-verification of the same release window.
- Benefit: only cosmetic today — dedupe/relation correctness of data that is
  non-authoritative by design, with zero external users (v0.1.2 cohorts start after).
- Risk: the rewrite is the only write the product would ever do into agent-owned files;
  an error here is a data-integrity incident exactly when trust is being established.

### Option B — dated deferral amendment (recommended)

Fold the amendment text below into ADR 0006; annotate follow-up task 10; record the gate
as decided in the baseline matrix and this memo. No code changes, no template changes, no
new write surface. Includes a dated correction of the 2026-10-12 template claim (item 6),
recording the consistent legacy state (templates ↔ taught files ↔ scanner) as the
accepted v0.1.x deviation. Revisit triggers go on record: row-14 result, TOML-from-LLM
conformance in the spike, or the first external-alpha artifact friction.

### Option C — templates switch without migration (optional add-on to B)

Switch the five templates and kit docs to teach the TOML `/0.1` format now, leaving
existing files untouched; scanner support already exists (items 1–2). Content-only
change, but it ships a format agents will start writing in alpha before digest/sealing
tooling exists (`digest` stays deliberately optional per the ADR). It also satisfies the
existing amendment instead of correcting it. Acceptable either as B (correction) or B+C
(switch); recommend deciding explicitly, not silently.

## Recommendation

**Option B** for v0.1.2 (dated amendment + correction of record; artifacts stay
self-reported, non-authoritative, never gate evidence), declining Option A for this
release because its marginal value is zero-user-benefit while its cost lands on the same
window as packaging and privacy re-verification, and it would add an
agent-owned-file rewrite surface ahead of trust. Option C is left as an explicit owner
add-on; if declined, the amendment's correction of record keeps the plain truth. The
migration question returns after the external evidence (post-V012-05) or earlier via a
recorded trigger — with the baseline's safety requirements intact.

## Draft amendment text (fold into ADR 0006 as "Amendment 2026-10-17 (v0.1.2 scope)" on decision)

```markdown
Decision (owner): the artifact migration (`cursorfleet migrate artifacts --yes`,
artifact_id and revision dedupe, digest computation/sealing) remains **deferred** in
v0.1.2. No rewrite of agent-owned `.cursorfleet/work/` files is performed or scheduled;
a future migration must be user-invoked, dry-run-first, legacy-labeled and
rollback-safe (v0.1.2 baseline P1-3) and needs a new dated decision.

Facts recorded as shipped:

- The scanner reads both syntaxes: `+++` TOML fences (`tomllib`) when present, else the
  `---` strict YAML subset (`workflow/frontmatter.py`).
- Both schema ids validate: `cursorfleet.artifact/0.1` (requires `artifact_id`,
  `revision`) and legacy `cursorfleet.artifact/1` (`workflow/artifacts.py`).
- Deduplication stays SHA-256 over path plus frontmatter (`state/artifact_scan.py`); no
  digest verification and no revision handling. A declared `digest` key is accepted and
  ignored.
- `cursorfleet emit` stays unimplemented.

Correction of record: the 2026-10-12 amendment's sentence "Generated kit templates teach
TOML frontmatter" was not executed; the shipped templates teach the legacy format (YAML
subset, `cursorfleet.artifact/1`). Until the template switch tied to task
10 ([follow-ups](../follow-ups.md)), templates, files produced with them and the scanner
are mutually consistent; that consistent legacy state is the **recorded, accepted
deviation** for v0.1.x.

Unchanged invariants: artifacts remain self-reported, non-authoritative and never gate
evidence ([ADR 0011](../adr/0011-evidence-trust-model.md)); the TUI labels them
"self-reported"; identity and digest would not change the trust tier.

Revisit triggers: empirical-test-plan row 14 result; a TOML-from-LLM conformance capture
in the spike; or external-alpha artifact friction. Any revisit supersedes this amendment
with a new date and must satisfy the v0.1.2 baseline's migration-safety requirements.
```

## If the owner decides

Implementation of B is one commit: fold the amendment into ADR 0006, annotate follow-up
task 10 ("waits also for the post-alpha reconsideration per v012-03"), add a dated note
to the baseline gate row and `status.md`, and a CHANGELOG entry. Decision record:

| Field | Value |
| --- | --- |
| Decision (A / B / B+C) | |
| Date / by | |
| Amendment text approved as drafted? | |

Until that record exists, the gate stays DEFERRED and this memo stays honest about it.
