# v0.1.0 owner runbook (post-tag)

Use this after the agent/repo prep; order matches [v01-release-ready.md](v01-release-ready.md).

## 1. Live Cursor (Linux IDE)

1. Follow [quickstart §4](../quickstart.md) two-run recipe.
2. Complete [b0-live-validation-2026-10-12.md](b0-live-validation-2026-10-12.md) scenarios 1, 2, 5.
3. Record [so01-permission-hooks.md](so01-permission-hooks.md) for `preToolUse` and `subagentStart`.
4. Run 13B paired measurement; fill [latency-13b-linux-ide.md](latency-13b-linux-ide.md).
5. Optional: add sanitized [active-run-screenshot.png](active-run-screenshot.png) and link from public docs.

Commit evidence updates on `main` (signed commits).

## 2. PyPI

1. Re-check PyPI name `cursorfleet` ([adr-0005-naming-gate.md](adr-0005-naming-gate.md)).
2. Complete [pypi-trusted-publishing-setup.md](pypi-trusted-publishing-setup.md).
3. Set repository variable `RELEASE_ENABLED=true` only when ready.

## 3. Publish

1. Open the **draft** [GitHub release for v0.1.0](https://github.com/M9nx/cursorfleet/releases).
2. Paste/edit notes from CHANGELOG `[0.1.0]`.
3. Publish the GitHub release (not draft).
4. Approve the **pypi** environment deployment for the tag workflow (or re-run publish job if needed).

## 4. Post-publish

1. Run [external alpha](../external-alpha.md); record [external-alpha-results.md](external-alpha-results.md).
2. Track [v0.1.1-backlog.md](v0.1.1-backlog.md) (attach picker, etc.).
