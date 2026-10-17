# v0.1.2 release preparation baseline

Last updated: 2026-10-17. Status: **PREPARATION**. This document records the
release scope and evidence boundary for the next patch/minor pre-alpha release;
it does not authorize a tag, a publish, or a push.

## Baseline

| Item | Fact |
| --- | --- |
| Development branch | `main` |
| Baseline SHA | `8165a76c367efbc31fd02661f16c4363f93e1eb0` |
| Previous tag | `v0.1.1` (`cc3735bd5c17f3e8a33ead8bc0eb6a8ac3356383`) |
| Working version | `0.1.2.dev0` |
| Latest PyPI release | `0.1.1` |
| GitHub tags | `v0.1.0`, `v0.1.1` |
| GitHub Releases | No published release is currently visible; do not describe a tag as a published release |
| Local verification | ruff, format, strict `mypy`, pytest (recorded at baseline: `1010 passed, 1 skipped, 1 deselected`; re-verified 2026-10-17 on `main`: ruff/format clean, strict `mypy` clean, `1011 passed, 1 deselected` — one previously skipped test passes here) |
| Docs site | GitHub Pages at <https://m9nx.github.io/cursorfleet/> |

The baseline is clean and already contains the v0.1.1 attach-suggestion UX and
the v0.1.2 development-version bump. The remaining work is not yet a release:
the live Cursor evidence and external-user evidence are incomplete.

## v0.1.2 objective

Make the public pre-alpha release truthful, installable, and useful enough for
controlled external validation. The release should close evidence and
documentation gaps that affect user trust before adding new orchestration or
policy features.

## Scope

### P0 — release-blocking

1. **Evidence closure:** complete or explicitly amend the live B0 scenarios,
   SO-01 permission-hook check, and latency row 13B for every claimed surface.
2. **Public truth convergence:** make README, in-repo docs, Pages docs, ADR
   index, changelog, and status records agree with the shipped code and the
   evidence actually available.
3. **Install and package verification:** build the sdist and wheel, inspect
   their contents, install each in a clean environment, and run the synthetic
   smoke path.
4. **Privacy and uninstall regression:** rerun the no-network, secret-corpus,
   uninstall, and runtime-boundary checks on the release candidate.

### P1 — required for useful external alpha

1. Record the guided and natural external-alpha tracks in
   [`external-alpha-results.md`](external-alpha-results.md).
2. Decide whether the current explicit run start/attach flow is acceptable for
   the first external cohort; do not silently broaden membership.
3. Complete the artifact migration decision. If migration is implemented,
   provide a dry-run, safe rewrite, legacy labeling, and rollback evidence. If
   it is deferred, amend ADR 0006 and keep artifacts explicitly self-reported
   and non-authoritative.
4. Run a one-week maintainer dogfood period from the published installation
   path and record failures, friction, and whether the tool is missed when
   disabled.

### Deferred

The following remain outside v0.1.2 unless a new dated decision says otherwise:

- enforcement, allow/deny/ask policy, sandboxing, agent scheduling or spawning;
- cloud-agent visibility, raw conversation display, token/cost tracking;
- multi-IDE support, GitHub write integration, and Product Hunt execution;
- any claim that CursorFleet proves tests passed or isolates worktrees.

## Gate matrix

| Gate | Evidence required | State at baseline | Owner action |
| --- | --- | --- | --- |
| Package/version | `0.1.2` metadata, lockfile, changelog, clean build | OPEN | prepare candidate only after evidence gates |
| Live B0 | Scenarios 1, 2, 5 plus restart/archive notes and sanitized screenshot | OPEN/PARTIAL | run on maintainer Linux Cursor IDE |
| SO-01 | `preToolUse` and `subagentStart` accept `{"permission":"allow"}` | OPEN in repository record | verify on the exact Cursor version claimed |
| Latency 13B | ≥3 batches × 30 paired calls, pooled median/p95 and verdict | OPEN | record summarized numbers; no raw timing dump |
| Public docs | no stale release, key, or support claim | PARTIAL | completed by this convergence pass; recheck after code changes |
| Artifact contract | implementation or dated ADR 0006 amendment | DEFERRED | choose before external-alpha sign-off |
| External alpha | guided + natural tracks meet the documented thresholds | NOT STARTED | recruit controlled cohort after install path is stable |
| Packaging | clean wheel/sdist install and smoke evidence | OPEN | run on candidate commit |
| Release | clean tree, CI green, owner approval, immutable tag | NOT AUTHORIZED | do not tag or publish in prep |

## Required order

1. Keep this baseline and the public documentation truthful.
2. Run the owner-controlled B0, SO-01, and latency checks; amend claims when
   the measured result is PARTIAL rather than hiding it.
3. Resolve the artifact contract and update ADR 0006 before calling the alpha
   evidence complete.
4. Build and smoke-test the candidate from a clean checkout, then run the
   guided and natural external-alpha tracks.
5. Prepare release notes and a draft release only after all blocking gates are
   closed. Tagging, PyPI publishing, and Product Hunt still require explicit
   owner authorization.

## Issue sequence

| Issue | Purpose | Depends on | Exit evidence |
| --- | --- | --- | --- |
| V012-01 — Truth and release baseline | Align package, README, Pages, changelog, status, and evidence records | none | This baseline plus a clean docs build |
| V012-02 — Live evidence closure | Run B0, SO-01, and latency 13B on the claimed Cursor surface | V012-01 | Dated records, verdicts, and sanitized screenshot |
| V012-03 — Artifact contract decision | Implement safe migration or amend ADR 0006 with an explicit deferral | V012-02 | Tests/evidence or dated ADR amendment |
| V012-04 — Candidate packaging | Build, inspect, install, smoke-test, and rerun privacy/uninstall gates | V012-01 through V012-03 | Clean candidate report and CI green |
| V012-05 — External alpha | Run guided and natural tracks with at least the documented cohort metrics | V012-04 | Completed external-alpha-results.md |
| V012-06 — Release candidate decision | Reconcile all gates and prepare immutable release artifacts | V012-05 | Maintainer go/no-go; no automatic publish |

The next owner-controlled issue is **V012-02**. Owner run kit:
[`run-kit-v012-02.md`](run-kit-v012-02.md). It requires a real Cursor
session and cannot be honestly closed by synthetic fixtures or repository tests.

## Verification commands

```bash
uv sync --all-extras --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
uv build
uv run --no-project python scripts/check_dist.py dist
```

The release candidate must also be installed into a clean environment and run
through `scripts/smoke_wheel.py` and the synthetic demo. Do not use raw Cursor
spools, prompts, transcripts, secrets, or private paths as committed evidence.

## Go / no-go

**No-go** if any supported-surface claim lacks dated evidence, if package and
documentation versions disagree, if a privacy or uninstall regression appears,
or if the external-alpha thresholds are not met. A failed published candidate
is handled by yanking the affected PyPI version and publishing a corrected
patch release; published tags remain immutable.
