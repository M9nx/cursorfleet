# Hook latency

The hook hot path (`cursorfleet-hook`, `cursorfleet.adapters.cursor.hook_main`) starts a
fresh interpreter for every Cursor hook call. Target: **steady-state p95 <= 60 ms**,
measured as **process wall time including interpreter startup** (spawn to exit), outside
Cursor. It is not a hook-internal budget. The M0a spike measured the capture-only hook at
about 27.7 ms steady-state p95 (ADR 0001, section C).

Terms (owner decision 2026-10-04, defined in
[ADR 0001 section D](adr/0001-cursor-capabilities.md)):

- **Steady-state:** a fresh process per call with a warm OS/page cache.
- **First-run:** a fresh process with a cold or partially cold cache. Reported, no target.
- **Hook-internal:** time after the process has started. Reported, no target.
- **End-to-end:** paired hooks-on versus hooks-off user-visible overhead inside Cursor. It has
  its own release contract (below). Not measured yet.

## How it is measured

```
uv run python scripts/bench_hook.py -n 100 --out hook-latency.json
```

Every sample spawns a new process with a real doc-derived payload on stdin, inside a
throwaway git repo, so wall time includes process spawn, interpreter startup, imports, repo
discovery, allowlist normalization, command redaction and the spool append. It excludes
Cursor's own spawn and IPC overhead. The script discards two warm-up samples per variant first, so every
reported number is steady-state; it does not produce first-run numbers. `tests/perf/test_hook_benchmark.py` (marker `benchmark`) runs the
same script with 3 samples as a smoke test and only asserts a very generous sanity bound;
timings are never asserted tightly because they depend on the machine.

## Result (2026-10-04, steady-state, outside Cursor)

Linux 6.18 x86_64, CPython 3.12.15, uv-managed venv with an editable install, warm page
cache (steady-state), 100 samples per row, process wall time in milliseconds:

| variant | hook | p50 | p95 | max |
| --- | --- | ---: | ---: | ---: |
| `python -c pass` (floor) | none | 15.3 | 20.3 | 24.4 |
| `cursorfleet-hook` (console script) | sessionStart | 21.9 | 28.7 | 30.7 |
| `cursorfleet-hook` (console script) | preToolUse | 22.7 | 27.5 | 31.1 |
| `cursorfleet-hook` (console script) | postToolUse | 25.3 | 31.2 | 42.0 |
| `python -c "...main()"` | preToolUse | 26.0 | 30.8 | 47.7 |
| `python -I -S` with `src` on `sys.path` | preToolUse | 21.6 | 24.4 | 30.6 |

The hot path adds roughly 7 to 10 ms over an empty interpreter, so steady-state p95 is
about half the 60 ms target. First-run (cold cache), Windows, macOS and end-to-end numbers
do not exist yet; interpreter startup on Windows and macOS is typically slower, which is
why the target keeps a 2x margin.

## End-to-end release contract

The 60 ms target above does not say what a user feels inside Cursor. The release contract
for that is in [ADR 0001 section D](adr/0001-cursor-capabilities.md): at least 3 batches of
30 paired hooks-on/hooks-off calls; the metric is the paired delta
(`T(hooks-on) - T(hooks-off)`) per call; pool all pairs, and each batch must individually
not FAIL.

| Verdict | Pooled paired delta |
| --- | --- |
| PASS | median <= 100 ms and p95 <= 200 ms |
| PARTIAL | median <= 150 ms and p95 <= 300 ms |
| FAIL | median > 150 ms, p95 > 300 ms, or any hook-induced failure or timeout |

Procedure: [`empirical-test-plan.md`](empirical-test-plan.md) row 13B. Result: OPEN.

## What keeps it fast

- Stdlib only, lazy imports. `hook_main` loads no pydantic, typer, textual, sqlite3,
  socket or `typing`/`dataclasses`/`pathlib`; `tests/security/test_hook_privacy.py`
  asserts this in a subprocess for several hooks.
- No `git` subprocess: the runtime directory is found with a `.git` file walk that a
  contract test compares with `git rev-parse` (main checkout, subdirectories, linked
  worktrees, submodules, symlinks).
- One `O_APPEND` write per event; no SQLite, no locking, no fsync.
- `tomllib` is imported only when `.cursorfleet/config.toml` mentions `privacy` or
  `retention` (it pulls in `typing`, about 2 to 4 ms).
