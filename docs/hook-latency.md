# Hook latency

The hook hot path (`cursorfleet-hook`, `cursorfleet.adapters.cursor.hook_main`) starts a
fresh interpreter for every Cursor hook call. Budget from the plan: **p95 < 60 ms cold**.
The M0a spike measured the capture-only hook at about 27.7 ms (ADR 0001, section C).

## How it is measured

```
uv run python scripts/bench_hook.py -n 100 --out hook-latency.json
```

Every sample spawns a new process with a real doc-derived payload on stdin, inside a
throwaway git repo, so wall time includes process spawn, imports, repo discovery,
allowlist normalization, command redaction and the spool append. It excludes Cursor's own
spawn and IPC overhead. `tests/perf/test_hook_benchmark.py` (marker `benchmark`) runs the
same script with 3 samples as a smoke test and only asserts a very generous sanity bound;
timings are never asserted tightly because they depend on the machine.

## Result (2026-10-04)

Linux 6.18 x86_64, CPython 3.12.15, uv-managed venv with an editable install, warm page
cache, 100 samples per row, milliseconds:

| variant | hook | p50 | p95 | max |
| --- | --- | ---: | ---: | ---: |
| `python -c pass` (floor) | none | 15.3 | 20.3 | 24.4 |
| `cursorfleet-hook` (console script) | sessionStart | 21.9 | 28.7 | 30.7 |
| `cursorfleet-hook` (console script) | preToolUse | 22.7 | 27.5 | 31.1 |
| `cursorfleet-hook` (console script) | postToolUse | 25.3 | 31.2 | 42.0 |
| `python -c "...main()"` | preToolUse | 26.0 | 30.8 | 47.7 |
| `python -I -S` with `src` on `sys.path` | preToolUse | 21.6 | 24.4 | 30.6 |

The hot path adds roughly 7 to 10 ms over an empty interpreter, so p95 is about half the
budget. Windows and macOS were not measured; interpreter startup there is typically
slower, which is why the budget keeps a 2x margin.

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
