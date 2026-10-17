# SO-01: Permission-hook reply (live Cursor)

Status: **OPEN** — live confirmation on the maintainer machine is part of the v0.1.2
live-evidence closure (V012-02; procedure in [run-kit-v012-02.md](run-kit-v012-02.md)).
The wheel smoke test and CI tests assert the reply bytes; neither is a live Cursor
confirmation. The minimum gate below is case C1 of the broader row-11 case matrix
([empirical-test-plan.md](../empirical-test-plan.md) row 11).

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
