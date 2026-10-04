# Platform support

CursorFleet is written to behave the same on Linux, macOS and Windows, but only one of them has
been exercised by a human, and **none has been verified against a live Cursor**. Be sceptical of
anything stronger than the table.

| OS | Level | What that means |
| --- | --- | --- |
| Linux | **Tested** | Developed and run here: full test suite, hook latency benchmark (27.7 ms p95 cold start, `spike/results/latency-linux.json`), the demo, the built wheel smoke-tested in a clean venv. Not verified against live Cursor. |
| macOS | **CI-tested only** | The CI matrix runs the whole suite and the wheel smoke test on `macos-latest`. Nobody has run it by hand; hook latency is unmeasured. Not verified against live Cursor. |
| Windows | **CI-tested only, least certain** | The CI matrix runs the suite and wheel smoke test on `windows-latest`. Several Windows behaviours below are reasoned about from documentation, not observed. Not verified against live Cursor. |

"CI-tested" is a claim about the workflow in `.github/workflows/ci.yml`, which has not run on
GitHub yet at the time of writing. Treat a green matrix, once it exists, as the evidence, and
a red cell as a known gap rather than a surprise.

## Cursor surfaces

Operating system and Cursor surface are different questions. The table above is about the
OS. For Cursor itself ([ADR 0001](adr/0001-cursor-capabilities.md)):

- **Local Cursor IDE (desktop): the only supported v0.1 surface**, and only after the live
  spike confirms it. Today it is untested against a live Cursor.
- **Not claimed, not supported:** Cursor CLI (`agent`, interactive and `-p`), the Agents
  Window, Cursor-managed worktrees, manual worktrees opened in Cursor, parallel subagents,
  cloud agents and cloud subagents. Hooks may or may not fire there; nothing here says they do.
- A surface moves into the supported list only when its row in the empirical test matrix
  passes ([`empirical-test-plan.md`](empirical-test-plan.md)).
- Git worktrees as a **git** feature are read by the collector, but that does not mean the
  hooks work inside Cursor-managed worktrees.

Python 3.11 to 3.14 are in the matrix. The `watch` extra (`watchfiles`) is optional; without it
the TUI polls.

## What was audited for portability

| Area | Approach | Status |
| --- | --- | --- |
| File locking | `fcntl.flock` on POSIX, `msvcrt.locking` on Windows (`state/lock.py`); imported lazily, never on the hook path. Covers the indexer only; the maintenance lock for purge and the contention-versus-unsupported check in [ADR 0002](adr/0002-storage-layout-and-runtime-directory.md) are not implemented. | Partly written; Windows unverified |
| Permissions | `0700`/`0600` via `os.chmod`/`os.fchmod` guarded by `os.name == "posix"`. Windows gets the default ACL of the user profile, nothing more. | Documented gap (see below) |
| Atomic appends | One spool file per writer, opened `O_APPEND`; lines are at most 8 KiB with a CRC, so a torn or interleaved write is detected and skipped on read. | Tested on Linux; Windows append semantics unverified (ADR 0002 Q5) |
| Symlinks and junctions | `O_NOFOLLOW` where it exists; `is_link_like` also treats Windows reparse points (junctions) as links. Creating symlinks on Windows needs a privilege, so the symlink tests are skipped there with an explicit reason. | Junction check simulated on Linux only |
| Executable lookup | `safeexe.find_executable` never searches the current directory and handles `PATHEXT`. | Unit-tested with synthetic directories |
| Paths | Stored paths are workspace-relative with `/`; anything outside is `<external>`; drive-letter refs are refused. | Tested on Linux |
| Line endings | Generated files use `\n`; `hooks.json` indent, separators and line ending are detected and reproduced on write, so a CRLF file stays CRLF. Git's `autocrlf` can still rewrite managed files; `validate` reports drift rather than hiding it. | Tested on Linux with synthetic CRLF input |
| Case-insensitive file systems | A path that differs only by case from the workspace root compares unequal and is stored as `<external>` (fails safe). | Accepted |
| Console script shim | The wheel installs `cursorfleet` and `cursorfleet-hook` as console scripts (`.exe` launchers on Windows). `hooks.json` contains the bare command `cursorfleet-hook`. | Wheel smoke-tested in CI on all three OSes |
| `python` vs `python3` | The generated `hooks.json` does **not** call Python directly, so the Windows `python` and POSIX `python3` split does not apply. The spike kit (`spike/`) does, and ships a separate Windows example. | n/a |

## Known gaps and honest caveats

- **Windows ACLs are not set.** The runtime directory sits in `<git-common-dir>/cursorfleet/`
  and inherits the permissions of the repository. `doctor` reports the POSIX modes only. Do not
  put the repository on a shared or synced directory with a loose ACL (threat model).
- **Windows hook command resolution.** Cursor starts hook commands through the platform shell;
  `cmd.exe` searches the current directory before `PATH`, so a hostile repository could shadow
  `cursorfleet-hook` with `cursorfleet-hook.cmd`. `doctor` warns when such a file exists
  (security review SA-04). The command stays bare because an absolute path cannot be committed.
- **`MAX_PATH`.** A deep repository path can exceed 260 characters; the hook may then fail to
  open its spool and silently drop the event (it fails open by design).
- **Hook latency on macOS and Windows is unmeasured.** Interpreter start-up there is slower than
  on Linux, especially with antivirus scanning. The 60 ms p95 budget is only evidenced on Linux
  (`docs/hook-latency.md`). Run `python scripts/bench_hook.py` or `spike/bench_latency.py` on
  each OS to get a number before relying on it.
- **Terminals.** The TUI uses Textual. Windows Terminal, iTerm2 and modern Linux terminals are
  expected to work; legacy `conhost` rendering, unusual locales and non-UTF-8 code pages are not
  tested. Redirected output on Windows consoles may need `PYTHONUTF8=1` if you see encoding errors.
- **Cursor itself.** Where Cursor keeps `hooks.json` per OS, how it spawns hooks, and whether
  the CLI and Agents Window fire hooks are the open questions in ADR 0001 (Q1 to Q6); no
  support is claimed for them. Enterprise
  paths in `doctor` come from documentation only.

## Test policy for platform differences

Platform-sensitive tests are skipped only with an explicit `reason=` that names the missing
capability (POSIX permissions, non-root user, symlink privilege, shell scripts). Core modules
are never guarded by `importorskip`. If a Windows or macOS CI cell fails, fix the code or add a
narrow skip with the reason; do not widen skips to get green.
