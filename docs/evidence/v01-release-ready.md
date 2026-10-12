# v0.1.0 tag readiness

Last updated: 2026-10-12 (post CI fix `2b0debf`).

## Ready in repository

- Green CI on `main` (lint, matrix, wheel smoke)
- Privacy hot-path default OFF + regression test
- Run-scoped git fields for linked sessions
- ADR amendments 2026-10-12; truth table; quickstart two-run recipe
- Sanitized post-M2.5 spool fixture
- ADR 0005 naming record ([adr-0005-naming-gate.md](adr-0005-naming-gate.md))
- PyPI setup checklist ([pypi-trusted-publishing-setup.md](pypi-trusted-publishing-setup.md))

## Still OPEN before `RELEASE_ENABLED` + PyPI approve

1. **B0 live** — [b0-live-validation-2026-10-12.md](b0-live-validation-2026-10-12.md) scenarios 1, 2, 5 + optional screenshot
2. **SO-01** — [so01-permission-hooks.md](so01-permission-hooks.md)
3. **Latency 13B** — [latency-13b-linux-ide.md](latency-13b-linux-ide.md) or dated PARTIAL amend
4. **GitHub `pypi` environment** + Trusted Publishing (owner UI)
5. Day-of PyPI name re-check at tag time

## Tag `v0.1.0`

May be pushed when CI is green and version/changelog commit is on `main`. PyPI publish remains
gated by `RELEASE_ENABLED` and the OPEN items above.

After tag: draft GitHub release from workflow; external alpha post-tag per [status.md](../status.md).
