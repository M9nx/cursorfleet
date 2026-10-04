# A2 contract decision matrix

Date: 2026-10-05. Decider: project owner. Evidence: [live-validation-index.md](live-validation-index.md),
maintainer Termchat smoke (Linux Cursor IDE 3.22.7, product hooks).

## Summary

| Area | Decision | ADR action |
| --- | --- | --- |
| Hook surface (9 vs 12) | **Keep 12** registered observe hooks for v0.1 alpha | **Amend ADR 0007** — nine core + three observe refiners |
| Event `schema_version` | **Retain `1.0`** as canonical emit value | **Amend ADR 0003** — no numerical rollback to `0.1` |
| Event kind `test.completed` | Add **`verification.observed`**; dual-read legacy kind in indexer/reducer | Amend ADR 0003 section 3 |
| Command display | **Default OFF** (`store_command_display = false`) | Implement ADR 0003 |
| Gate / evidence UI | **Observations only**; no PASS/FAIL from tiers 1–3 | ADR 0011 unchanged |
| Attribution aggregate | **Weakest-wins** + per-value counts | Implement ADR 0003 |
| Artifacts | **TOML `cursorfleet.artifact/0.1`** canonical; **YAML `/1` legacy read** | Implement ADR 0006 |

## 1. Hook surface (9 vs 12)

### Options

- **Nine:** ADR 0007 original set; fewer permission surfaces; no `afterFileEdit` / shell pair.
- **Twelve:** current code — adds `beforeShellExecution`, `afterShellExecution`, `afterFileEdit`.

### Live smoke evidence

- `afterFileEdit` → `file.changed` events useful for “what changed” without file contents.
- Shell hooks refine `tool.*` with exit status for verification **observations** (not gates).
- `afterShellExecution` receives output in memory but sanitizer does not persist it (privacy OK).
- Steady-state hook latency outside Cursor within budget ([hook-latency.md](../hook-latency.md)); in-Cursor row 13B still OPEN.

### Decision

**Keep twelve hooks** for v0.1 alpha. Update ADR 0007 text to list twelve as the v0.1 observe set;
nine remains the historical narrow policy document, superseded by this amendment for alpha.

### Non-goals

- Do not register forbidden/content hooks (prompt, thought, beforeReadFile).

## 2. Event schema version

### Options

A. Retain `1.0` emit  
B. New version + dual-read  
C. Normalize in memory only  

### Evidence

Existing spools and code emit `"1.0"` ([`events/kinds.py`](../../src/cursorfleet/events/kinds.py)).

### Decision

**Option A:** canonical **`1.0`**. Reader accepts unknown future versions by skip-count, never drop `1.0`.
Amend ADR 0003 “0.1 until release” language — release versioning applies to package semver, not event line schema.

## 3. Verification kind

### Decision

Emit **`verification.observed`** for heuristic command classification. Indexer and reducer **accept both**
`test.completed` (legacy spool) and `verification.observed` (new lines). Spool lines are never rewritten.

## 4. Command display

### Decision

Default **`store_command_display = false`**. Classifier uses `argv0` + subcommand only; confidence lower where needed.

## 5. Gates / observations

### Decision

Remove PASS/FAIL gate tiles. Show **Observations** list with heuristic flag, method, confidence, commit, stale.

## 6. Attribution

### Decision

Reducer aggregates **weakest** `exact` < `inferred` < `unknown`. Role-only remains `inferred`.

## 7. Artifacts

### Decision

Implement TOML `+++` frontmatter per ADR 0006. Continue reading YAML `---` legacy as **Legacy declared**.
Templates and skills teach TOML. `cursorfleet migrate artifacts --dry-run` in A3.

## Sign-off

All rows decided; **A3 may proceed**.
