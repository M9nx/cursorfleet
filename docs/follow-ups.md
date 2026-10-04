# Follow-ups: where the docs and ADRs are ahead of the code

Status: **none of this is done.** The 2026-10-04 documentation pass changed no code. Each
task below closes a divergence between an accepted or provisional ADR and the current
implementation. Do them **after** the live spike ([`empirical-test-plan.md`](empirical-test-plan.md)),
in this order. The freeze rules are in [`status.md`](status.md).

How to read an entry:

- **Waits for:** the spike row (by number in the test plan) whose result could change the task.
  "Nothing" means the decision does not depend on Cursor behaviour, but the task still waits
  for the freeze to lift, and should be batched with its neighbours to avoid regenerating
  schemas and the golden file repeatedly.
- **Done when:** the check that closes it, which is also the matching ADR release gate.
- Run `uv run ruff check .`, `uv run mypy src` and `uv run pytest -q` after each task.

## 1. Narrow the hook set to nine (ADR 0007)

- Waits for: rows 1 and 11 (hooks fire as documented; permission-hook reply accepted).
- Do: stop registering `beforeShellExecution`, `afterShellExecution`, `afterFileEdit`.
  - `src/cursorfleet/adapters/cursor/hook_policy.py`: `ALLOWED_V01_HOOKS`, docstring,
    explicit not-registered set, `PERMISSION_HOOKS` comment.
  - `src/cursorfleet/config/models.py`: `HookName` and default `hooks.enabled`.
  - `src/cursorfleet/adapters/cursor/hook_normalize.py`: remove three handlers;
    `handled_hooks()` equals the nine.
  - `hook_main.py`, `hooksjson.py`, `installer.py`: references; installer removes the three
    entries on re-`init` (see task 2); drift checks in `validate` and `doctor` expect nine.
  - `src/cursorfleet/state/reducer.py`: drop `before_shell_calls` and the Shell
    de-duplication. `src/cursorfleet/events/models.py`: references.
  - `templates/cursor/config/config.toml`; regenerate `schemas/config.schema.json` and
    `schemas/event.schema.json`; `scripts/demo.py`.
  - Tests: `test_hook_policy` (asserts 12), `test_hook_normalize`, `test_kit_hooksjson`,
    `test_config_models`, `test_kit_installer_policy`, `test_kit_init_uninstall`,
    `test_hook_main`, `test_cli_state`, `test_reducer`, `test_hook_privacy`,
    `test_tui_privacy`, `m2_helpers`, `m2_strategies`.
- Docs after: the "twelve" wording in `quickstart.md`, `architecture.md`, `kit.md`,
  `product-contract.md`, `CHANGELOG.md`; remove the divergence notes added to them.
- Done when: the installer registers exactly nine hooks (ADR 0007 gate).

## 2. Migration for removed hook entries (ADR 0009)

- Waits for: task 1.
- Do: on re-`init`, remove only CursorFleet-owned entries (`command == "cursorfleet-hook"`)
  for hooks no longer in the set; keep everything else; show it in the diff; make
  `uninstall` handle both old and new locks. Tests under `tests/integration/test_kit_*`.
- Done when: a repo installed with twelve hooks upgrades to nine with a visible diff, and
  round trip passes on all three OSes in CI (ADR 0009 gate).

## 3. Schema version `0.1` and schema ids (ADR 0003)

- Waits for: nothing; batch with tasks 1, 4 and 5 so schemas and the golden file are
  regenerated once.
- Do: `SCHEMA_VERSION` to `"0.1"`; ids `cursorfleet.status/0.1`, `cursorfleet.artifact/0.1`,
  `cursorfleet.doctor/0.1`, `cursorfleet.validate/0.1`, `cursorfleet.replay/0.1`; update
  `events/kinds.py`, `events/models.py`, `hook_normalize.py`, `config/models.py`,
  `config/roster.py`, `kit.py`, `templates/cursor/config/config.toml`, `schemas/*.schema.json`
  (regenerate with `scripts/gen_schemas.py`; `$id` URLs), and
  `tests/fixtures/status/status.v1.golden.json` (rename and regenerate deliberately).
- Done when: no `"1.0"` or `/1` id remains outside history (ADR 0003 gate).

## 4. Command display default OFF; classifier without display (ADR 0003 section 4)

- Waits for: nothing.
- Do: default `store_command_display` to `false` in `config/models.py` and the config
  template; change `tui/gates.py:classify_command` and `hook_sanitize.is_verify_command` to
  use `argv0` and `subcommand` only; lower classification confidence accordingly; update
  `privacy.md`, `threat-model.md` (remove divergence notes).
- Tests: `test_hook_sanitize`, `test_hook_privacy`, `test_tui_privacy`, `test_config_models`.
- Done when: a fresh install stores no display string (ADR 0003 gate).

## 5. `verification.observed` replaces `test.completed` (ADR 0003 section 3)

- Waits for: nothing for the rename; row 1 for whether `postToolUse` carries an exit code at
  all (ADR 0007 note).
- Do: remove `test.completed` from `events/kinds.py`; add `verification.observed` with the
  `classification` object (`heuristic` must be `true`, `method`, `confidence` low or medium,
  `class`); update `hook_normalize.py`, `reducer.py` (`_on_test`, `last_test`, VERIFYING
  lane), `status_doc.py` (`last_test`), the schemas and golden file.
- Tests: `test_hook_normalize`, `test_reducer`, `test_tui_gates`, `test_tui_app`.
- Done when: no `test.completed` remains (ADR 0003 gate).

## 6. Stop deriving gates from heuristics; label evidence tiers (ADR 0011, rule R1)

- Waits for: task 5.
- Do: `src/cursorfleet/tui/gates.py` must not map `verification.observed` or `gate.changed`
  to PASS or FAIL; every gate is "not evaluated" in v0.1 and the observations are listed
  beside it as "observed, heuristic" with method and confidence. Label each displayed signal
  with its tier in the TUI and `status --json` (`gates[]`, `sessions[].agents[].last_test`).
  Update `tui.md`, `governance.md`, `product-contract.md` (remove the violation notes).
- Tests: `test_tui_gates`, `test_tui_app`, `test_cli_state`, golden file.
- Done when: no gate is PASS or FAIL from tier 1 to 3 data (ADR 0011 gate).

## 7. Attribution: rename, correct the role-only case, weakest-wins (ADR 0003 section 2)

- Waits for: rows 8 and 9 (Q1, Q2); the result decides whether `exact` is reachable for
  tool events at all.
- Do: rename `Attribution.INFERRED` to `inferred_temporal` in `events/kinds.py`;
  `hook_normalize.py:_identity` must emit `exact` for a payload that carries
  `subagent_type` as an explicit role (instance unknown), and never `inferred_temporal`
  in v0.1; `reducer.py` (`_touch_agent`, `_ATTRIBUTION_RANK`) aggregates to the **weakest**
  value and exposes per-value counts; TUI shows "inferred (temporal)" in words.
- Docs after: `tui.md`, `governance.md`, `status-json.md`.
- Done when: an inferred value is never shown as exact anywhere (ADR 0003 gate).

## 8. Reducer: show lane basis everywhere; rename the `reviewed` flag (ADR 0010)

- Waits for: row 8 (lanes depend on attribution).
- Do: every lane, and every "verifying" or "reviewed" indication, in the TUI and
  `status --json` carries its basis (`lane_basis`); rename `reviewed` (set from `stop`) to a
  name that says it is an inference and keep the old key only if the contract requires.
- Tests: `test_reducer`, `test_tui_*`, golden file.
- Done when: the ADR 0010 gate holds and replay equivalence tests stay green.

## 9. Storage: fingerprints, worktree ids, locks, quarantine (ADR 0002)

- Waits for: rows 5, 6 and 7 (Q4 and Q5) for the worktree id and the lock behaviour on each
  OS; the BLAKE2s change itself does not wait.
- Do, in this order:
  - `state/spool_read.py:fingerprint_of` to `blake2s(first_line, digest_size=16)` hex;
    `files.fingerprint` column and projection layout version bump; rebuild from the spool.
  - `events/ids.py:worktree_id` to `wt-` + HMAC-SHA256 with the per-repo `hmac.key` and the
    domain label in ADR 0002; adjust callers (`git/worktrees.py`, `status_doc.py`,
    `tui/data.py`).
  - `state/lock.py`: separate `maintenance.lock`; take it in `state/retention.py` purge and
    in rebuild; distinguish contention from an unsupported filesystem; open the lock file
    with `O_NOFOLLOW` where available; fixed lock order.
  - `Projection.quarantine()` in `state/indexer.py`: never fall back to `os.remove`; leave
    the file and report. `doctor` reports a non-empty `quarantine/`.
- Tests: `test_spool`, `test_indexer`, `test_ids`, `test_retention`, `test_runtime_trust`,
  `test_runtime_resolution`, `test_hook_redos` as relevant; add lock-contention tests with
  events, not sleeps.
- Done when: BLAKE2s, HMAC ids and the maintenance lock are implemented (ADR 0002 gate).

## 10. TOML artifacts with identity, revision and digest (ADR 0006)

- Waits for: row 14 (rule, skill and nested `AGENTS.md` loading) and the TOML-from-LLM
  conformance check.
- Do: `workflow/frontmatter.py` and `workflow/artifacts.py` (`+++`, `tomllib`, `artifact_id`,
  `revision`, digest compute and compare); `state/artifact_scan.py` (dedupe by
  `artifact_id` and revision, `digest_mismatch` problem); `kit.py`, `tui/data.py`,
  `tui/views.py`; the five templates (`templates/cursor/rules/cursorfleet-handoff.mdc`,
  `templates/cursor/skills/cursorfleet-artifacts/SKILL.md`,
  `templates/cursor/skills/cursorfleet-coordinator/SKILL.md`,
  `templates/cursor/agents-md/work.md`, `templates/cursor/agents/architect.md`) as listed in
  ADR 0006; check `templates/cursor/rules/cursorfleet-core.mdc` for artifact examples too. Optional: a sealing command (`emit --seal`), not required for v0.1.
- Tests: `test_artifact_scan`, `test_kit_frontmatter`, `test_hostile_repo`, `test_tui_privacy`,
  `tui_helpers`, `test_kit_doctor_validate`.
- Docs after: `kit.md`, `tui.md`, `governance.md` (remove divergence notes).
- Done when: ADR 0006 gate, including a test that artifact events are ineligible as gate
  evidence.

## 11. `doctor` and `validate` improvements implied by the ADRs

- Waits for: tasks 1 and 9.
- Do: check that `doctor` lists each hook entry's `failClosed` (ADR 0008; not verified in
  this pass, add it if missing); optionally show the Cursor
  worktree cap if readable (ADR 0012); `doctor` states "observe only" (ADR 0008 gate).

## 12. Documentation after the code

- Waits for: the tasks above, one by one.
- Do: remove every **Divergence** note added in this pass as its task lands. Search for the
  word "Divergence" in `docs/` and `README.md`. Update `CHANGELOG.md`, `status.md` and the
  ADR "Implementation status" lines to Implemented.
- Add rows 10 (`Task` linkage) and 14 (instruction loading) to the ADR 0001 matrix if they
  are not there; set each row to PASS, FAIL or PARTIAL with version and date.
- Update the supported-surface claims in `README.md`, `quickstart.md`, `platform-support.md`
  and `product-contract.md` to match the matrix exactly.

## 13. Naming and publication (ADR 0005)

- Waits for: nothing technical; a human decision.
- Do: choose the public name, check PyPI, npm and GitHub on the day, get the trademark
  review, then perform the renames listed in ADR 0005. Only then publish a package, tag or a
  docs site ([`docs-site-plan.md`](docs-site-plan.md)).

## Not follow-ups (decided, nothing to change)

- ADR 0004 text stays as history; ADR 0007 supersedes it.
- The git-common-dir runtime directory is kept (ADR 0002) unless row 5 or 6 refutes it.
- No enforcement in v0.1 (ADR 0008).
