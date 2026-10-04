# Worktrees

Subagents share the parent agent's checkout by default and can overwrite each
other's changes. **Isolation is requested, not configured.** There is no
subagent frontmatter field for a worktree. Isolation is obtained by asking
for it in the prompt ("each in its own environment"). When Cursor honours
that, each subagent gets its own branch, either as a Git worktree on the
machine or as a cloud environment.

CursorFleet can **detect** worktrees from read-only Git. It does **not**
create, delete, or enforce them in v0.1. Cursor creates, discovers, and
cleans worktrees itself (including ones created by `git worktree add` or
Cursor skills). Treat them as external and ephemeral.

Cursor-managed worktrees, manual worktrees, and the Agents Window are **not
claimed** as supported surfaces until the live spike marks those rows PASS.
Cloud environments never appear in the local dashboard.

## Runtime inheritance

Write commands (`init`, `uninstall`) require a Git **repository root**. An
ordinary subdirectory exits 2 and writes nothing. See [`init`](../cli/init.md).

Hooks are a different contract. A non-Git directory nested inside an
**already initialized** enclosing repository inherits that repository for
runtime event attribution:

- The nearest Git root is found from the tool working directory (or
  `CURSOR_PROJECT_DIR` if there is no usable cwd).
- That root must already have `.cursorfleet/config.toml` as a regular file.
- Paths are stored relative to that root.
- No nested `.cursorfleet/` and no nested runtime directory are created.

An inner `.git` directory, gitfile, or submodule is a new boundary. The hook
does not fall back to an outer repository. A missing marker, an uninitialized
root, an external symlink, or an ambiguous multi-root workspace records
nothing and fails open.

Linked worktree roots are valid install roots. Runtime data still lives at
`<git-common-dir>/cursorfleet/`, so one dashboard sees every worktree of the
repo.

Whether Cursor-managed worktrees resolve that common directory the same way
(ADR 0001 Q4) is not yet verified.

## What the dashboard shows

The worktrees screen lists branch, HEAD, dirty files, ahead/behind (no
`git fetch`, so remotes can be stale), stale or prunable flags, owning
agent, and last activity. `r` only re-reads. See
[TUI overview](../tui/overview.md).
