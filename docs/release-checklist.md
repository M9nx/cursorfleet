# Release checklist (owner steps)

Release preparation is done; **publishing is the owner's decision** and is blocked on facts that
only a live Cursor can supply. Nothing in this repository has published, tagged or pushed
anything, and `.github/workflows/release.yml` has never run.

Legend: **BLOCKING** = do not tag `v0.1.0` before this is done. *Non-blocking* = can follow
(or be skipped with a conscious decision).

## A. Establish the facts (BLOCKING for any claim about real Cursor)

1. **BLOCKING: run the spike.** Follow [`spike/README.md`](../spike/README.md) in a scratch
   repository on the IDE, the Agents Window and the CLI. Do not use a repository with secrets.
2. **BLOCKING: answer ADR 0001 questions Q1 to Q6** in [`spike/questions.md`](../spike/questions.md)
   (CONFIRMED / REFUTED / PARTIAL, with the Cursor version and surface), then move items from
   section B to section A of [`docs/adr/0001-cursor-capabilities.md`](adr/0001-cursor-capabilities.md).
3. **BLOCKING: reconcile every PROVISIONAL item** with the answers: ADR 0001 section B, ADR
   0002 (storage location, Q4/Q5), ADR 0003 (hook to kind mapping, `tool_output` shape), ADR
   0004 (permission-hook reply classification), `docs/kit.md`, `docs/architecture.md`,
   `docs/product-contract.md`, `docs/status-json.md`, `docs/threat-model.md`, `docs/tui.md`.
   Anything still unverified keeps its PROVISIONAL label; do not delete labels to look finished.
4. **BLOCKING: review captures, then add sanitized real fixtures** under `tests/fixtures/cursor/`
   stamped with `cursor_version`, and add contract tests against them. The current examples are
   doc-derived and must not be called fixtures.
5. **BLOCKING: confirm the permission-hook reply** (`{"permission":"allow"}`) is accepted by the
   real Cursor for `preToolUse`, `subagentStart` and `beforeShellExecution`
   (security review SO-01). A wrong reply shape blocks the action.
6. *Non-blocking:* run `python scripts/bench_hook.py` (or `spike/bench_latency.py`) on macOS and
   Windows and record the numbers in `docs/hook-latency.md`.
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

11. **BLOCKING: verify the PyPI name `cursorfleet` is free** (https://pypi.org/project/cursorfleet/
    should 404) and decide whether to reserve it. Re-read
    [ADR 0005](adr/0005-naming-and-trademark.md) on naming and the trademark notice; the README
    keeps the unofficial statement.
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
16. *Non-blocking:* consider a TestPyPI dry run by hand (not automated here) to check how the
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
