# PyPI Trusted Publishing setup (owner)

Status: **GitHub configured** (2026-10-12): `pypi` environment with required reviewer `M9nx`, `RELEASE_ENABLED=true`. **PyPI pending publisher** still required in UI (see below).

## PyPI project (first time) — **you must do this in the browser**

Log in at [pypi.org](https://pypi.org) as **M9nx**, then **Account settings → Publishing** (or [manage/account/publishing](https://pypi.org/manage/account/publishing/)) → **Add a new pending publisher**. Values must match GitHub OIDC exactly (from failed run `38301917759`):

| Field | Value |
| --- | --- |
| PyPI Project Name | `cursorfleet` (new project; created on first upload) |
| Owner | `M9nx` |
| Repository name | `cursorfleet` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

Save the publisher, then re-run the failed **publish to PyPI** job on the latest [Release workflow](https://github.com/M9nx/cursorfleet/actions/workflows/release.yml) for tag `v0.1.0` and approve the **`pypi`** environment again.

## GitHub repository

Done on `M9nx/cursorfleet`:

1. Environment **`pypi`** with required reviewer **M9nx**.
2. Repository variable **`RELEASE_ENABLED`** = **`true`** (kill switch in [release.yml](../../.github/workflows/release.yml)).

Optional: tag ruleset for `v*`.

## Release sequence

1. All gates in [v01-release-ready.md](v01-release-ready.md) closed.
2. Push tag `v0.1.0` matching [pyproject.toml](../../pyproject.toml) version.
3. Workflow creates **draft** GitHub release with wheel/sdist.
4. Approve **pypi** environment deployment after reviewing assets.
5. Publish GitHub release notes manually.

Do **not** enable `RELEASE_ENABLED` until SO-01 and B0 live rows are PASS.
