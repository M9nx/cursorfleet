# `cursorfleet init`

```bash
cursorfleet init --cursor [--dry-run] [--yes] [--path DIR]
```

Installs the observe-only Cursor kit at a Git **repository root**: roster
subagent files, coordinator skill (and optional rule), core rules, artifact
skill, managed `AGENTS.md` blocks, observe-only hook entries, and (if
absent) seed `config.toml` / `roster.toml`. Existing hook entries and
`AGENTS.md` text outside the managed block are preserved.

`--cursor` is required. Cursor is the only target.

| Option | Meaning |
| --- | --- |
| `--cursor` | Install the Cursor kit. Required. |
| `--dry-run` | Print the exact unified diff of every file and write nothing. |
| `--yes` / `-y` | Skip the confirmation prompt. The diff is still printed. |
| `--path DIR` | Repository root to install into (default: current directory). |

Without `--yes`, a prompt (default no) is required. No TTY and no input
aborts; nothing is written.

## Git is required

`init` must run from a Git repository root. There is **no `--allow-non-git`**
flag, environment variable, or config key.

| Situation | Result |
| --- | --- |
| Not inside a Git working tree | Exit **2**, nothing changed (not even `.cursorfleet/`). |
| Ordinary subdirectory (or `--path` pointing at one) | Exit **2**, nothing changed. Prints the detected root and tells you to run there. |
| Nested repository or linked worktree root | That root is accepted. A subdirectory of either is exit 2. |
| Unknown option such as `--allow-non-git` | Usage error, exit 2, nothing changed. |

`--path` names the directory to install into. It must exist, be a directory,
and be a repository root. It is not a hint to search upward.

`--dry-run` and `--yes` obey the same preconditions: a dry run from a
subdirectory is exit 2 with no diff.

A second `init` is a no-op when the lock already matches. Dirty conflicts
(an unmanaged file at a managed path, a modified managed file or block,
invalid `hooks.json`, a symlink at a managed path) abort before any write
(exit 1).

## Lockfile

`.cursorfleet/install.lock.json` records owned paths, SHA-256 hashes,
managed blocks, hook entries, and created directories. No timestamps. It is
written last. Paths must stay on an allowlist
(`.cursor/agents|rules|skills/`, `.cursorfleet/`, `AGENTS.md`), so a hostile
lock cannot widen uninstall.

## Uninstall

```bash
cursorfleet uninstall [--dry-run] [--yes] [--force] [--path DIR]
```

Removes only what the lockfile lists, and only while hashes still match.
Drifted items are reported, skipped, and stay in the lockfile (`--force`
removes them). Edited `config.toml` / `roster.toml` are kept.
`init` then `uninstall` restores the tree byte for byte, including a
pre-existing `hooks.json` and `AGENTS.md`.

`uninstall` uses the same repository-root preconditions as `init` (exit 2
when not at a Git root). It does not delete runtime data under
`<git-common-dir>/cursorfleet/`.

Next: [`doctor`](doctor.md), [`validate`](validate.md).
