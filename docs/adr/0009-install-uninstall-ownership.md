# ADR 0009: Install and uninstall ownership

- Status: accepted (the generated content is provisional; the ownership rules are not)
- Date: 2026-10-04
- Deciders: project owner (M9nx), architecture-owner decision
- Evidence level: assumption for how Cursor treats merged hook entries and committed files; the rules themselves are verified by the integration tests
- Supersedes: none
- Superseded by: none
- Related ADRs: 0007 (the hook set the installer emits), 0008 (no `failClosed`), 0006 (artifact rules and skills it generates), 0002 (runtime data is not removed by uninstall), 0005 (name changes touch every owned path)
- Implementation status: Implemented-provisional for the rules below (`installer.py`, `hooksjson.py`, `blocks.py`, `lock.py`, `fsutil.py`; tests under `tests/integration/test_kit_*` and `tests/security/test_kit_installer_policy.py`). Divergent-from-code with ADR 0007: the installer emits 12 hooks and has no migration that removes the three dropped entries on re-`init`.
- Review trigger: Cursor changes how hooks.json is merged or reloaded; a user reports lost content after `uninstall`; the hook set changes (ADR 0007 follow-up)
- Release gate: round-trip guarantee (below) passes on fixture repos on all three OSes in CI; a migration for removed hook entries exists; the diff-and-consent flow is the only write path

## Context

`cursorfleet init --cursor` writes into a repository the user owns, including files the user
and other tools also edit (`.cursor/hooks.json`, `AGENTS.md`). Cursor-managed worktrees are
checkouts of the branch, so generated files must be committable. The threat model treats a
repository's committed files as untrusted data (TB4), including the lockfile.

## Decision

### What CursorFleet owns

- **Lockfile-listed files.** Whole files that `init` generated and recorded in
  `.cursorfleet/install.lock.json` with their SHA-256: `.cursor/agents/<prefix><id>.md`,
  `.cursor/rules/cursorfleet-*.mdc`, `.cursor/skills/cursorfleet-*/SKILL.md`, and the lockfile
  itself. Managed locations are an allowlist (`.cursor/agents/`, `.cursor/rules/`,
  `.cursor/skills/`, `.cursorfleet/`); the lockfile is validated against it, so a hostile
  lock cannot make `uninstall` delete anything else.
- **Managed blocks.** A delimited block (`<!-- cursorfleet:begin ... -->` to
  `<!-- cursorfleet:end -->`) inside root `AGENTS.md` and the work-directory `AGENTS.md`.
  Only the text between the markers is ours.
- **Its hook entries.** In `.cursor/hooks.json`, entries whose `command` is exactly
  `cursorfleet-hook`, with no `failClosed` and no `matcher`, registered only for the hook
  set of ADR 0007.
- **Directories it created**, recorded in the lock, removed on uninstall only if empty.

### What it must never touch

- Anything outside the managed allowlist, anything under `.git/`, anything reached through a
  symlink, and any file outside the workspace.
- Hook entries it did not write, other top-level keys of `hooks.json`, key order, and
  formatting (indent, separators, newline style, trailing newline) of user content.
- User text in `AGENTS.md` outside the managed block.
- Another source's hooks (user, team, enterprise, third-party). `doctor` lists them and
  warns about content-bearing ones; it never edits them.
- Runtime data under `<git-common-dir>/cursorfleet/`: `uninstall` leaves it; only
  `events purge` removes it.
- Invalid JSON: if `hooks.json` does not parse, `init` refuses; it never rewrites it.

### Seed files and user edits

- `.cursorfleet/config.toml` and `roster.toml` are **seeds**: written only if absent, user-owned
  afterwards. `uninstall` removes a seed only if it is still byte-identical to what `init`
  wrote; if edited, it is kept and reported.
- A generated file the user edited is **drift**: `init` refuses (tells the user to move the
  change into the roster or delete the file); `uninstall` skips it and reports it unless
  `--force`. `validate` and `doctor` report drift; nothing is overwritten silently.
- A pre-existing file with identical content is "adopted": never removed by `uninstall`.
- A file that exists and is not managed blocks `init`; CursorFleet never adopts differing
  content.
- A roster change that stops generating a file removes it on re-`init` only if it is
  unmodified; otherwise it is left and noted.

### `hooks.json` merge rules

- Our entries are identified only by the exact command; user entries are never reordered,
  merged into or removed.
- Each event key we add is recorded (`added_events`, `added_hooks_key`, `added_version`) so
  uninstall removes exactly those, including a `hooks` key or file we created.
- The original bytes are preserved in the lock (digest, and a base64 copy when the file
  cannot be reproduced) so uninstall restores them.
- When the hook set changes (ADR 0007), re-`init` must remove entries for hooks no longer
  registered. This migration is not implemented.

### Consent and diff

- `init` and `uninstall` compute a pure plan, print the exact unified diff, and write only
  after confirmation (`--yes` skips only the prompt; `--dry-run` writes nothing).
- Nothing is written without a plan; the lockfile is written last so a crash never records
  files that were not written; writes are atomic.

### Round-trip guarantee

`init` followed by `uninstall` restores the working tree **byte for byte**, including a
pre-existing `hooks.json` and `AGENTS.md`, provided the user did not edit managed content
in between. `init` twice is a no-op (the lock has no timestamps). If the user did edit, the
tool reports each item and leaves it; it never guesses.

## Consequences

- Positive: the user can see and undo everything; hostile locks and repos cannot widen the
  deletion surface; teammates without the tool get inert files.
- Negative / costs: strict refusal on conflicts is annoying; generated files must be
  committed for worktrees, which adds noise to the repository.
- Follow-ups: migration for removed hook entries; quarantine of a corrupt lockfile
  rather than aborting (not decided).

## Open questions

- Does Cursor tolerate `hooks.json` reformatting by tools while open (it reloads on save)?
- Should `uninstall` offer to remove the runtime directory?

## Alternatives considered

- Overwrite generated files unconditionally: rejected, destroys user edits.
- Write hooks to the user-level `~/.cursor/hooks.json`: rejected for v0.1, hooks then
  run for every repository and are not committed.
- No lockfile, identify files by name pattern: rejected, cannot prove ownership.
