# Security and privacy review, v0.1 (pre-release)

Scope: the whole `src/cursorfleet` tree at the end of M3, reviewed against
[`threat-model.md`](threat-model.md) and [`privacy.md`](privacy.md). This was a code review
plus targeted tests, **not** an external audit and **not** a test against a live Cursor
(ADR 0001 questions Q1-Q6 are still unanswered; see "Open" below). Every fixed finding has a
regression test under `tests/security/`.

## Summary

| Severity | Found | Fixed | Accepted | Open |
| --- | --- | --- | --- | --- |
| High | 1 | 1 | 0 | 0 |
| Medium | 5 | 5 | 0 | 0 |
| Low | 7 | 7 | 0 | 0 |
| Accepted risks (design) | 8 | n/a | 8 | n/a |
| Open items | 2 | n/a | n/a | 2 |

Areas reviewed with **no finding**: allowlist-based event parsing (nothing outside the
allowlist reaches disk), spool framing (CRC is integrity only; see SA-01), concurrent
appends (one writer file per process pair, `O_APPEND`), retention/purge (only files under
the runtime root, never following links), installer merge of `hooks.json` and managed
blocks, diff escaping, SQLite handling (parameterised queries only, `PRAGMA` fixed), TUI
rendering (`rich.text.Text` + `theme.safe`, never markup strings), CLI argument handling
(Typer types, no shell, no `eval`), logging (nothing logs payloads; there is no logging
configuration that writes to disk), and the dependency surface (3 direct runtime
dependencies plus one optional (`watchfiles`), none is an HTTP client; `pip-audit` on the locked set reported "No known
vulnerabilities found" when run during this review; re-run before each release).

## Findings

### SR-01 High: regex denial of service in command/text redaction (fixed)

The hook redacts secrets with regexes over the raw command and over free text. A crafted
long input (megabytes of near-matching text) made a pattern backtrack quadratically; the
hook would exceed Cursor's timeout on every call. Evidence:
`src/cursorfleet/adapters/cursor/hook_sanitize.py:28` (`_REDACT_WINDOW`), `:146` (`redact_text`),
`:165` (`redact_command`).
Fix: redaction runs on a bounded prefix window (1024 characters); the stored value is
truncated to that window anyway, so nothing beyond it is ever persisted.
Test: `tests/security/test_hook_redos.py` (adversarial inputs under a time budget,
end-to-end `run_hook` with a huge command, secret in the prefix still redacted).
Status: **fixed**.

### SR-02 Medium: runtime directory trusted without ownership/permission checks (fixed)

The runtime directory lives in `<git-common-dir>/cursorfleet/`. A hostile or shared `.git`
(for example a cloned repository that ships a pre-made `cursorfleet/` directory, a symlink,
a group-writable directory or one owned by another user) could make the hook append to an
attacker-chosen location, or make the indexer ingest forged spool files.
Evidence: `src/cursorfleet/state/runtime.py:163` (`untrusted_reason`), enforced at
`state/spool.py:136`, `state/spool_read.py:189`, `state/indexer.py:186,219,238`,
`adapters/cursor/hook_main.py:207` (HMAC key), `adapters/cursor/diagnostics.py:194` (doctor).
Fix: one `lstat`; refuse symlinks, non-directories, Windows reparse points, a different
owner and group/other-writable directories. The hook then drops the event (fail open), the
indexer raises `UntrustedRuntime`, `doctor` fails with remediation.
Test: `tests/security/test_runtime_trust.py`. Status: **fixed**.

### SR-03 Medium: tools resolved from the current directory (fixed)

On Windows, `CreateProcess` and `shutil.which` can resolve `git` or `cursor` from the
current directory, and an empty or relative `PATH` entry does the same on POSIX. In a
hostile repository `git.exe`/`git.cmd` would run with the user's privileges when the
collector, `init` or `doctor` ran.
Evidence: `src/cursorfleet/safeexe.py:49` (`find_executable`), used at `git/runner.py:85`,
`adapters/cursor/workspace.py:35`, `adapters/cursor/diagnostics.py:174`.
Fix: only absolute `PATH` entries that are not the current directory are searched; the
absolute result is what gets executed. Doctor also warns about files named
`cursorfleet-hook*` in the repo root (see SA-04).
Test: `tests/security/test_hostile_repo.py::test_find_executable_*`,
`::test_a_git_shim_in_the_repository_is_never_run`. Status: **fixed**.

### SR-04 Medium: NTFS junctions were not treated as links (fixed)

`Path.is_symlink()` is false for junctions, so the installer's "never through symlinks"
rule and the validators' symlink skipping did not apply on Windows.
Evidence: `adapters/cursor/fsutil.py:26` (`is_link_like`), used at `fsutil.py:78,108,149`,
`validation.py:215,249,316,331`. Fix: a reparse-point check on `st_file_attributes`.
Test: `test_reparse_points_count_as_links` (simulated; real junctions are CI-only on
Windows, see `platform-support.md`). Status: **fixed**.

### SR-05 Medium: git invoked without hostile-repo hardening in the workspace resolver (fixed)

`adapters/cursor/workspace.py` ran `git` with an inherited environment and without
`core.fsmonitor=false`/`--no-optional-locks`, while the collector already had both. A
hostile `.git/config` (`core.fsmonitor`) or inherited `GIT_DIR`/`GIT_SSH_COMMAND` could
execute a program or redirect the repository during `init`.
Evidence: `git/runner.py:25-36,64` (shared hardening) now used by
`adapters/cursor/workspace.py:35+`. Test: `test_hostile_git_config_never_executes_anything`
(fsmonitor, sshCommand, pager, editor, askpass, hooksPath, external diff, credential helper,
aliases, repository hooks) and `test_inherited_git_environment_*`. Status: **fixed**.

### SR-06 Medium: committed config/lock could name paths inside `.git` (fixed)

`work.dir` in `.cursorfleet/config.toml` and the paths in `.cursorfleet/install.lock.json`
are committed, hence attacker-controlled in a cloned repository. They were checked to be
relative and inside the workspace, but `.git/hooks` is inside the workspace. Creating files
or directories there (or removing "managed" files) is a code-execution primitive.
Evidence: `events/pathcheck.py:36`, `config/models.py:54`, `adapters/cursor/lock.py:31,40,125`.
Fix: any `.git` segment (case-insensitive) is rejected. Test:
`test_lockfile_cannot_name_git_internals`, `test_config_work_dir_cannot_target_git_or_escape`.
Status: **fixed**.

### SR-07 Low: a planted projection row could wedge the indexer (fixed)

A valid-looking SQLite file with a row that fails model validation raised on every sync.
Evidence: `state/indexer.py:195-204`. Fix: validation failures quarantine the database and
rebuild from the spool (the spool is the source of truth). Test:
`test_planted_projection_row_is_quarantined_and_rebuilt`. Status: **fixed**.

### SR-08 Low: Typer printed local variables in tracebacks (fixed)

An unexpected exception made Typer print the failing frame's locals, which can include
event payload fields. Evidence: `cli/main.py:39` (`pretty_exceptions_show_locals=False`).
Test: `test_cli_apps_do_not_print_local_variables_in_tracebacks` (subprocess). Status: **fixed**.

### SR-09 Low: terminal escapes through error and doctor output (fixed)

Exception messages and `hooks.json` keys/commands (attacker-controlled in a cloned repo)
were echoed raw by `events`, `replay`, `index` and `doctor`. Evidence:
`cli/commands/events.py:94,99,166`, `replay.py:41,46`, `index.py:31,36`,
`diagnostics.py:157,395,459`. Fix: `safe_text` on all of them. Test:
`tests/security/test_terminal_injection.py` (status text and JSON, TUI literal display of
`[bold red]`, ESC/OSC/bidi controls, doctor output). Status: **fixed**.

### SR-10 Low: artifact read followed a link swapped in after the scan (fixed)

Evidence: `state/artifact_scan.py:273-277` now opens with `O_NOFOLLOW` after the `lstat`
filter. Test: `test_artifact_reader_refuses_a_symlink_swapped_in_after_the_scan`.
Status: **fixed** (POSIX; on Windows the junction check in SR-04 applies).

### SR-11 Low: a FIFO at the spool path could hang the hook (fixed)

Evidence: `state/spool.py:41` (`O_NONBLOCK`; a FIFO without a reader fails with ENXIO).
Test: `test_a_fifo_planted_as_a_spool_file_does_not_hang_the_hook`. Status: **fixed**.

### SR-12 Low: drive-letter refs accepted by the HEAD reader (fixed)

`ref: refs/heads/C:/x` could join to an absolute Windows path. Evidence:
`adapters/cursor/hook_main.py:131`. Test: `test_hook_head_reader_refuses_drive_letter_refs`.
Status: **fixed**.

### SR-13 Low: `mysql -psecret` passwords were persisted (fixed)

Attached short-option passwords and `sshpass -p` were not redacted. Evidence:
`hook_sanitize.py:96,193`. Test: `test_hook_redos.py` (mysql family, sshpass, other `-p`
flags untouched). Status: **fixed**. Display redaction stays best effort (SA-06).

### Verified: no network access (test added)

`tests/security/test_no_network.py`: (1) no module under `src/` imports a networking
library, (2) with `socket.connect`, `connect_ex`, `sendto`, `create_connection`,
`getaddrinfo` and `gethostbyname` patched to fail, every CLI command (init dry-run and
real, doctor, validate, index, status, replay, events export/purge, uninstall), the hook
and the TUI run clean, (3) the git verbs the collector uses are a read-only, local-only
allowlist. Note this is a test of CursorFleet, not of Cursor or git itself.

## Accepted risks (rationale)

- **SA-01 CRC is not authentication; same-user forgery.** Spool lines carry a CRC32 to
  detect truncation and torn writes. Any process running as the same user can write
  well-formed events (the hook has no secret that the user's own tools lack). Defence is
  the directory trust check (SR-02) and the fact that v0.1 enforces nothing: forged events
  can mislead the dashboard, not change what agents may do. Status in the UI: observed vs
  self-reported are labelled apart (`governance.md`).
- **SA-02 Hostile lockfile.** A hostile `install.lock.json` can at most make `uninstall`
  propose removing files under the managed prefixes whose recorded hash matches their
  content, after printing a diff and asking for confirmation (`--yes` is explicit). `.git`
  and escapes are rejected (SR-06).
- **SA-03 `original_b64` in the committed lockfile.** To restore `hooks.json` byte for byte
  the lockfile stores the pre-install text. If that file contained secrets (for example in
  another tool's hook command) they are copied into a second committed file. The file is
  already in the repository when it is project-level; the user sees the diff before
  confirming. Mitigation to consider later: store only a hash and a patch of CursorFleet's
  own entries.
- **SA-04 Windows resolves `cursorfleet-hook` via `cmd.exe`, which searches the current
  directory first.** A hostile repo could ship `cursorfleet-hook.cmd`. The command cannot be
  made absolute without breaking a committed `hooks.json` across machines. `doctor` warns
  when such a file exists (`diagnostics.py:249`). Open to revisit once the spike shows how
  Cursor spawns hook commands.
- **SA-05 Path edge cases fail safe.** Case-insensitive filesystems and `MAX_PATH` on
  Windows can make a path compare unequal or an open fail; the result is `<external>` or a
  dropped event (fail open), never a wider write.
- **SA-06 Display redaction is best effort.** Patterns catch common token shapes and
  option names, not arbitrary secrets in free text. Therefore command text is stored
  redacted-and-truncated, command output is never stored, and `hash_commands` exists for
  dedupe without text.
- **SA-07 No Windows ACLs.** On Windows the runtime directory relies on the user profile's
  default ACLs; `0700/0600` are applied on POSIX only. Do not point the runtime at a
  shared or synced location.
- **SA-08 Same-user local attacker is out of scope**, as in the threat model: they can
  already read the repository and the user's files.

## Open

- **SO-01 (blocking for v0.1.0 claims) Real payloads unverified.** The event allowlist and
  the permission-reply contract come from Cursor's documentation. If a real payload differs,
  the likely failure is a dropped field, not a leak (unknown fields are discarded), but a
  wrong reply shape for a permission hook would block an action. Needs the spike
  (`spike/README.md`) before 0.1.0.
- **SO-02 (non-blocking) GitHub Actions are pinned by major version**, not by commit SHA.
  Pin and enable Dependabot for actions after the repository settings are the owner's call.
