# PyPI Trusted Publishing setup (owner)

Status: **configure in GitHub/PyPI UI** before setting `RELEASE_ENABLED=true`.

## PyPI project (first time)

1. Create project **`cursorfleet`** on PyPI (or let first Trusted Publishing upload create it).
2. Publishing → **Add a new pending publisher**:
   - Owner: `M9nx`
   - Repository: `cursorfleet`
   - Workflow: `release.yml`
   - Environment: `pypi`

## GitHub repository

1. **Settings → Environments → New environment:** `pypi`
2. Enable **Required reviewers** (protected deployment).
3. **Settings → Secrets and variables → Actions → Variables:**
   - `RELEASE_ENABLED` = `true` **only** when ready to publish (kill switch in [release.yml](../../.github/workflows/release.yml)).
4. Optional: tag ruleset for `v*`.

## Release sequence

1. All gates in [v01-release-ready.md](v01-release-ready.md) closed.
2. Push tag `v0.1.0` matching [pyproject.toml](../../pyproject.toml) version.
3. Workflow creates **draft** GitHub release with wheel/sdist.
4. Approve **pypi** environment deployment after reviewing assets.
5. Publish GitHub release notes manually.

Do **not** enable `RELEASE_ENABLED` until SO-01 and B0 live rows are PASS.
