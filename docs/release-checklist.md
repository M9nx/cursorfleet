# Release checklist (owner steps)

Release preparation is done; **publishing is the owner's decision** and is blocked on facts that
only a live Cursor can supply. Nothing in this repository has published, tagged or pushed
anything, and `.github/workflows/release.yml` has never run.

Legend: **BLOCKING** = do not tag `v0.1.0` before this is done. *Non-blocking* = can follow
(or be skipped with a conscious decision).

## 0. Process freeze (2026-10-04)

New M2 and TUI implementation is **frozen** until the live Cursor spike has been run and the
ADR 0001 questions are answered ([`status.md`](status.md)). The existing code is
implemented, provisional and unvalidated against live Cursor. After the spike, the code is
brought in line with the accepted ADRs in the order given in [`follow-ups.md`](follow-ups.md);
only then does the rest of this checklist apply.

- **BLOCKING:** every release gate listed in the [ADR index](adr/README.md) is met or its ADR
  is explicitly weakened by a new decision.
- **BLOCKING:** the supported-surface claims in the README, quickstart and
  [`platform-support.md`](platform-support.md) match the empirical test matrix in ADR 0001
  (local Cursor IDE only unless a row passed).

## A. Establish the facts (BLOCKING for any claim about real Cursor)

1. **BLOCKING: run the spike.** Follow [`spike/README.md`](../spike/README.md) and
   [`empirical-test-plan.md`](empirical-test-plan.md) in a scratch repository on the IDE, and
   on the Agents Window, the CLI and worktrees if you want to claim them. Do not use a
   repository with secrets.
2. **BLOCKING: answer ADR 0001 questions Q1 to Q6** in [`spike/questions.md`](../spike/questions.md)
   (CONFIRMED / REFUTED / PARTIAL, with the Cursor version and surface), then move items from
   section B to section A of [`docs/adr/0001-cursor-capabilities.md`](adr/0001-cursor-capabilities.md).
3. **BLOCKING: reconcile every PROVISIONAL item** with the answers: ADR 0001 section B, ADR
   0002 (storage location, Q4/Q5), ADR 0003 (hook to kind mapping, `tool_output` shape), ADR
   0007 (nine-hook set and permission-hook reply classification), `docs/kit.md`, `docs/architecture.md`,
   `docs/product-contract.md`, `docs/status-json.md`, `docs/threat-model.md`, `docs/tui.md`.
   Anything still unverified keeps its PROVISIONAL label; do not delete labels to look finished.
4. **BLOCKING: review captures, then add sanitized real fixtures** under `tests/fixtures/cursor/`
   stamped with `cursor_version`, and add contract tests against them. The current examples are
   doc-derived and must not be called fixtures.
5. **BLOCKING: confirm the permission-hook reply** (`{"permission":"allow"}`) is accepted by the
   real Cursor for `preToolUse` and `subagentStart` (the two permission hooks left under
   [ADR 0007](adr/0007-narrower-v01-hook-policy.md); security review SO-01). A wrong reply
   shape blocks the action.
6. **BLOCKING: latency gates** ([ADR 0001 section D](adr/0001-cursor-capabilities.md), row 13 of
   the test plan), for each OS and Cursor surface you claim:
   - steady-state hook p95 <= 60 ms process wall time including interpreter startup, from
     `python scripts/bench_hook.py` (or `spike/bench_latency.py`) on that OS, recorded in
     `docs/hook-latency.md`;
   - the end-to-end contract from at least 3 batches of 30 paired hooks-on/hooks-off calls,
     metric = paired delta (hooks-on minus hooks-off) per call, all pairs pooled and each
     batch individually not FAIL: **PASS** median <= 100 ms and p95 <= 200 ms; **PARTIAL**
     median <= 150 ms and p95 <= 300 ms (publish the numbers with the claim); **FAIL**
     median > 150 ms, p95 > 300 ms, or any hook-induced failure or timeout (do not claim
     that OS or surface, or slim the hot path and re-measure).
   Neither has been measured yet.
7. **BLOCKING: set `[cursor].validated_versions`** in `templates/cursor/config/config.toml`
   (and the docs) to the Cursor versions you actually verified, or leave it empty and keep the
   `doctor` warning.

## B. Make CI real (BLOCKING)

8. **BLOCKING:** push to a branch (your decision) and get the CI matrix green: Linux, macOS,
   Windows x Python 3.11 to 3.14, lint, format, mypy, tests, and the wheel smoke job. Fix or
   narrowly skip (with a reason) any platform failure; update
   [`platform-support.md`](platform-support.md) with what the matrix actually showed.
9. *Non-blocking:* pin third-party actions to commit SHAs and enable Dependabot for them
   (security review SO-02).
10. *Non-blocking:* re-run `pip-audit` (or your scanner) on the locked dependencies.

## C. Name, accounts and settings (BLOCKING)

11. **BLOCKING: pass the naming gate** ([ADR 0005](adr/0005-naming-and-trademark.md)).
    `CursorFleet` is a working name. Choose the public name (a name without any third-party
    mark; `fleet-for-cursor` is not a fallback because it still contains the Cursor mark),
    verify PyPI, npm and GitHub availability on the day, and complete a trademark review. If
    the name changes, do the renames listed in ADR 0005 before anything is published. The
    README keeps the unofficial statement. No package, tag or public docs site before this.
12. **BLOCKING: configure PyPI Trusted Publishing** for the project (or a pending publisher):
    owner `M9nx`, repository `cursorfleet`, workflow `release.yml`, environment `pypi`. No API
    token is needed or stored.
13. **BLOCKING: create the GitHub environment `pypi`** with required reviewers (a protected
    environment), and decide who may approve. *Optional:* restrict tag creation (`v*`) with a
    tag ruleset.
14. **BLOCKING: set the repository variable `RELEASE_ENABLED=true`** only when you are ready; the
    publish job is skipped without it (kill switch). The draft-release job runs regardless.
15. *Non-blocking:* enable private vulnerability reporting (referenced by `SECURITY.md`) and
    confirm the advisory link works.
16. *Non-blocking:* publish the docs site only after item 11
    ([`docs-site-plan.md`](docs-site-plan.md)). Consider a TestPyPI dry run by hand (not automated here) to check how the
    project page renders.

## D. Cut the release

17. **BLOCKING:** on a clean `main`, run the full local gate and confirm it is green:
    ```bash
    uv sync --all-extras --locked
    uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
    uv build && python scripts/check_dist.py dist
    ```
    then install `dist/*.whl` into a fresh venv outside the checkout and run
    `python scripts/smoke_wheel.py <venv>` and `python scripts/demo.py --venv <venv>`.
18. **BLOCKING:** bump the version `0.0.1.dev0` to `0.1.0` in `pyproject.toml` (the release workflow
    refuses a tag that does not match), run `uv lock`, change the classifier
    `Development Status :: 2 - Pre-Alpha` only if you really mean it, and refresh the
    README status text to match what step A established.
19. **BLOCKING:** in `CHANGELOG.md`, rename `[Unreleased]` to `[0.1.0] - <date>`, keep the known
    limitations that remain true, and add a fresh empty `[Unreleased]`.
20. **BLOCKING:** commit, push `main`, then tag and push the tag (this is what triggers the
    workflow):
    ```bash
    git tag -s v0.1.0 -m "CursorFleet 0.1.0"     # or an unsigned annotated tag
    git push origin v0.1.0
    ```
21. The workflow then runs the checks, builds, creates a **draft** GitHub release with the sdist
    and wheel, and (if enabled and approved) publishes to PyPI. **BLOCKING:** approve the `pypi`
    environment deployment only after reading the draft release assets.
22. **BLOCKING:** edit the draft release notes from the changelog and publish it.
23. *Non-blocking, after release:* in a clean environment run `pipx install cursorfleet` /
    `uv tool install cursorfleet`, then the quickstart; update `docs/quickstart.md` to drop the
    "not on PyPI yet" wording; bump to the next `.dev0`.

## If something goes wrong

PyPI files cannot be replaced. Yank the release on PyPI, publish a fixed patch version, and
note it in the changelog. If the tag is wrong and nothing was published, delete the draft
release and the tag, fix, and tag again.
