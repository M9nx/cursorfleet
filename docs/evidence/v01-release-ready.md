# v0.1.0 tag readiness

Last updated: 2026-10-12.

## Ready in repository

- Privacy hot-path default OFF + regression test
- Run-scoped git fields for linked sessions
- ADR amendments 2026-10-12 (0002, 0003, 0006, 0007) and truth table
- Sanitized post-M2.5 spool fixture + contract test
- Product-facing doc convergence (see [`v01-doc-allowlist.json`](v01-doc-allowlist.json))
- B1 engineering sign-off; B0 table updated (live re-run items marked)

## Owner must complete before `git tag v0.1.0` + `RELEASE_ENABLED`

1. **ADR 0005** — public name, day-of registry check, trademark note
2. **SO-01 / checklist A.5** — live permission-hook reply on claimed Cursor surface
3. **Checklist A.6** — latency evidence or dated PARTIAL amendment + narrowed platform claims
4. **Checklist C** — PyPI Trusted Publishing, `pypi` environment, `RELEASE_ENABLED=true`
5. **Screenshot** — optional for tag; required for Product Hunt gate

After the above: bump `0.0.1.dev0` → `0.1.0`, CHANGELOG date section, signed tag, approve PyPI job.
