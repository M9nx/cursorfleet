# v0.1.0 tag readiness

Last updated: 2026-10-12 (`main` at `df919a4`, tag `v0.1.0` → `626db23`).

## Shipped

| Item | Status |
| --- | --- |
| CI on `main` | Green ([workflow](https://github.com/M9nx/cursorfleet/actions/workflows/ci.yml)) |
| Tag `v0.1.0` | Pushed; Release workflow green ([run](https://github.com/M9nx/cursorfleet/actions/runs/38298997744)) |
| Draft GitHub release | [CursorFleet v0.1.0](https://github.com/M9nx/cursorfleet/releases) (wheel + sdist attached) |
| `main` development | `0.1.1.dev0` |
| Code/docs prep | Privacy default, run-scoped git, quickstart runs, ADR amendments, fixtures |

## Before `RELEASE_ENABLED=true` and PyPI approve

1. **B0 live** — [b0-live-validation-2026-10-12.md](b0-live-validation-2026-10-12.md) scenarios **1, 2, 5** + optional [active-run-screenshot.png](active-run-screenshot.png)
2. **SO-01** — [so01-permission-hooks.md](so01-permission-hooks.md) on live Cursor
3. **Latency 13B** — [latency-13b-linux-ide.md](latency-13b-linux-ide.md) or dated PARTIAL + platform narrow
4. **PyPI** — [pypi-trusted-publishing-setup.md](pypi-trusted-publishing-setup.md) (`pypi` env, Trusted Publishing, day-of name check)
5. **Publish** — Edit draft release notes from [CHANGELOG 0.1.0](../CHANGELOG.md); publish release; approve `pypi` job

External alpha remains **post-PyPI** ([status.md](../status.md), [v0.1.1-backlog.md](v0.1.1-backlog.md)).
