# Quickstart

**Unofficial and pre-alpha.** CursorFleet is not affiliated with or endorsed by
Anysphere or Cursor. v0.1 only *observes* local Cursor agent sessions: no
enforcement, no forced approvals, no cloud-agent visibility. Q1 and Q2 remain
**OPEN**. Parallel-identity classification is **BLOCKED/OPEN** on tested Cursor
3.22.7 Linux.

## 1. Install

Follow [Installation](installation.md). Confirm `cursorfleet --version` and
that `cursorfleet-hook` is on `PATH`.

## 2. Install the kit in a repository

Run from the **root** of the git repository you work on with Cursor. Git is
required; there is **no `--allow-non-git`**.

```bash
cursorfleet init --cursor --dry-run   # print the exact diff, write nothing
cursorfleet init --cursor             # show the diff again and ask before writing
```

`--cursor` is required. Cursor is the only target.

| Option | Meaning |
| --- | --- |
| `--cursor` | Install the Cursor kit. Required. |
| `--dry-run` | Print the unified diff and write nothing. |
| `--yes` / `-y` | Skip the confirmation prompt. The diff is still printed. |
| `--path DIR` | Repository root (default: current directory). |

Without `--yes`, a prompt (default no) is required. No TTY and no input aborts;
nothing is written.

A non-git folder, or an ordinary subdirectory of a repository, exits **2** and
writes nothing. `--path` must itself be a repository root. A genuine nested
repository and a linked-worktree root are valid roots.

This adds observe-only hook entries (merged with yours), a small roster of
subagent files, rules and skills, an `AGENTS.md` block, and `.cursorfleet/`
configuration. Hooks record sanitized metadata only. Details:
[`cursorfleet init`](../cli/init.md).

The installed hook set in the current checkout is twelve; the accepted
decision is nine. That change is not applied yet.

Commit the generated `.cursor/` and `.cursorfleet/` files if you want them in
worktrees that check out your branch.

CursorFleet never creates or deletes worktrees.

## 3. Check health

```bash
cursorfleet doctor
cursorfleet doctor --no-probe-cursor
cursorfleet validate
```

`doctor` checks Python, the hook binary on `PATH`, git, the runtime directory
and its permissions, the config, drift between installed files and the
lockfile, and lists the hooks Cursor would merge. It can run `cursor --version`
(argv list, 5s timeout) unless you pass `--no-probe-cursor`. Exit code 1 means
a check *failed*; warnings exit 0.

`validate` checks config, roster, generated files, and work artifacts. Exit
code 1 if any error is found; warnings do not fail the command.

See [`doctor`](../cli/doctor.md) and [`validate`](../cli/validate.md).

## 4. Use Cursor as usual, then inspect locally

Open the repository in Cursor, trust the workspace (project hooks only run in
trusted workspaces), and start agents. Hooks append sanitized events under the
repository's Git common directory (inside `.git`, never in the working tree).

```bash
cursorfleet status                    # the same data as plain text
cursorfleet status --json             # stable machine-readable snapshot
cursorfleet tui                       # dashboard; needs an interactive terminal
```

`status --json` uses schema `cursorfleet.status/1`. Silence is reported as
stale or offline, never as idle. See [`status`](../cli/status.md).

The TUI is **under development** and unvalidated against live Cursor. It
refuses non-interactive terminals (exit 2); use `status` or `status --json` in
scripts. See [TUI overview](../tui/overview.md).

## 5. Uninstall

Same repository-root rule as `init`:

```bash
cursorfleet uninstall --dry-run
cursorfleet uninstall
```

This removes only what the install lockfile lists, while hashes still match.
Files you edited are reported and left alone (`--force` removes them).
`init` followed by `uninstall` restores the tree byte for byte, including a
pre-existing `hooks.json` and `AGENTS.md`. Runtime data stays under the Git
common directory until you purge events.

## If something looks empty

- Run `cursorfleet doctor`. Typical causes: `cursorfleet-hook` not on the
  `PATH` Cursor sees (GUI apps do not inherit your shell profile), the
  workspace is untrusted, or hooks were not reloaded.
- A runtime-directory refusal means the directory under the Git common path is
  a symlink, owned by someone else, or group-writable. CursorFleet will not use
  a directory it cannot trust.
- The hook cannot block Cursor: it always exits 0 and answers `{}` or
  `{"permission":"allow"}` on any internal failure.
