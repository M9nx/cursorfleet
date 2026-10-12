# Latency row 13B — Linux Cursor IDE (end-to-end)

Status: **OPEN** — paired hooks-on/hooks-off inside Cursor not recorded yet.

Contract ([ADR 0001 §D](../adr/0001-cursor-capabilities.md), [release-checklist §A.6](../release-checklist.md)):

- ≥3 batches × 30 paired calls
- Metric: paired delta (hooks-on minus hooks-off) per call
- PASS: pooled median ≤100 ms and p95 ≤200 ms (each batch not FAIL)
- PARTIAL: median ≤150 ms, p95 ≤300 ms (requires dated ADR amendment + narrowed claims)

## Steady-state (outside Cursor)

Recorded separately in [hook-latency.md](../hook-latency.md) (process wall time, p95 ≤60 ms target).

## 13B batches (fill in Cursor)

| Batch | median delta ms | p95 delta ms | Verdict |
| --- | ---: | ---: | --- |
| 1 | | | |
| 2 | | | |
| 3 | | | |
| **Pooled** | | | |

**Overall verdict:** PASS / PARTIAL / FAIL

Do not commit raw timing dumps; summarize here only.
