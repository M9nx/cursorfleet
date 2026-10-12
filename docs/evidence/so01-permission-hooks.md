# SO-01: Permission-hook reply (live Cursor)

Status: **OPEN** — confirm on maintainer machine before PyPI publish claims.

Required hooks: `preToolUse`, `subagentStart`.

Expected stdout (exit 0):

```json
{"permission":"allow"}
```

| Hook | Cursor version | Date | Result | Notes |
| --- | --- | --- | --- | --- |
| preToolUse | | | | Action proceeded; hook exit 0 |
| subagentStart | | | | Subagent started; hook exit 0 |

Integration tests assert reply shape in CI; this record is the **live Cursor** confirmation
([security-review-v0.1.md](../security-review-v0.1.md) SO-01).

When both rows are PASS, set **SO-01** to Met in [v01-adr-truth-table.md](v01-adr-truth-table.md).
