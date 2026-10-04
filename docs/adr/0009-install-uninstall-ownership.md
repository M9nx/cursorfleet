# ADR 0009: Install and uninstall ownership

- Status: accepted (the generated content is provisional; the ownership rules are not)
- Date: 2026-10-04
- Deciders: project owner (M9nx), architecture-owner decision
- Evidence level: assumption for how Cursor treats merged hook entries and committed files; the rules themselves are verified by the integration tests
- Supersedes: none
- Superseded by: none
- Related ADRs: 0007 (the hook set the installer emits), 0008 (no `failClosed`), 0006 (artifact rules and skills it generates), 0002 (runtime data is not removed by uninstall; nested non-Git runtime inheritance), 0005 (name changes touch every owned path)
- Implementation status: Implemented-provisional for the rules below (`installer.py`, `hooksjson.py`, `blocks.py`, `lock.py`, `fsutil.py`; tests under `tests/integration/test_kit_*` and `tests/security/test_kit_installer_policy.py`). Divergent-from-code with ADR 0007: the installer emits 12 hooks and has no migration that removes the three dropped entries on re-`init`. Repository-root write-command preconditions (exit 2, no writes) are implemented; `doctor`/`validate` print the detected root and boundary type (follow-ups task 15). Runtime inheritance (ADR 0002) is implemented in the hook; `init` still refuses ordinary subdirectories. Live row 17 remains OPEN.
- Review trigger: Cursor changes how hooks.json is merged or reloaded; a user reports lost content after `uninstall`; the hook set changes (ADR 0007 follow-up)
- Release gate: round-trip guarantee (below) passes on fixture repos on all three OSes in CI; a migration for removed hook entries exists; the diff-and-consent flow is the only write path; `init` and `uninstall` enforce the repository-root preconditions of the 2026-10-04 amendment (exit 2, no changes) with the tests listed in follow-ups task 15

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

- Submodule roots (see the 2026-10-04 amendment): allow silently, warn, or refuse? OPEN.
- Does Cursor tolerate `hooks.json` reformatting by tools while open (it reloads on save)?
- Should `uninstall` offer to remove the runtime directory?

## Alternatives considered

- Overwrite generated files unconditionally: rejected, destroys user edits.
- Write hooks to the user-level `~/.cursor/hooks.json`: rejected for v0.1, hooks then
  run for every repository and are not committed.
- No lockfile, identify files by name pattern: rejected, cannot prove ownership.
- An `--allow-non-git` flag, or silently walking up to the enclosing repository: rejected in
  the 2026-10-04 amendment below; the first dilutes the Git requirement of ADR 0002, the
  second writes into a repository the user did not name.

## Amendment 2026-10-04 (repository-root preconditions for `init` and `uninstall`)

Architecture-owner decision. The write-command root check is implemented in
`workspace_root` (exit 2, no writes). `doctor`/`validate` print the detected root they
used (follow-ups task 15). Live row 17 remains OPEN. It adds a
precondition that runs before the consent-and-diff flow above and does not change any
ownership rule. `init` and `uninstall` write into a repository the user owns, so they must
never write into a repository the user did not name.

### Terms

- **Target directory:** the value of `--path` if given, else the current directory, made
  absolute and symlink-resolved (realpath).
- **Detected repository root:** the top level of the nearest enclosing Git working tree of the
  target directory (`git rev-parse --show-toplevel`, realpath-resolved). "Nearest" means the
  innermost `.git` (directory or gitfile) found walking up from the target.

### Rules (v0.1)

1. **No Git, no install.** If the target directory is not inside a Git working tree,
   `cursorfleet init` exits **2**, changes **nothing** (no file, no directory, not even
   `.cursorfleet/`), and explains that Git is required. There is **no `--allow-non-git` flag**
   and no environment variable or config key that overrides this in v0.1. Passing an unknown
   option is an ordinary usage error (exit 2, nothing changed).
2. **Repository root only.** If the target directory is inside a repository but is not that
   repository's root (an ordinary subdirectory), `init` exits **2**, changes nothing, prints
   the detected repository root and tells the user to run the command there. It must never
   silently modify the enclosing repository on the user's behalf.
3. **Nested repository.** A genuine nested repository (a directory with its own `.git`) is its
   own root. The nearest root wins and the outer repository is never consulted: `init` at the
   inner root installs into the inner repository only; from a subdirectory of the inner
   repository, rule 2 applies with the **inner** root.
4. **Linked worktree.** The root of a linked worktree (a directory whose `.git` is a gitfile
   pointing into `<common-dir>/worktrees/<name>`) is a valid root. `init` writes into that
   worktree's working tree; the runtime directory stays at `<git-common-dir>/cursorfleet/`
   (ADR 0002). A subdirectory of a linked worktree is rule 2 with the worktree root.
5. **`uninstall` follows the same preconditions** because it also writes: not in Git, or not at
   the repository root, gives exit 2 with nothing changed and the same message shape (command
   name `uninstall`). This extends the owner's `init` decision for consistency; the lockfile
   lives at the repository root, so a subdirectory has nothing of its own to remove.
6. **Read-only commands are unchanged.** `doctor` and `validate` change nothing, so they keep
   resolving the enclosing repository from a subdirectory, but they must print the detected
   root they used. Outside Git, `doctor` reports a failed `git.repo` check and exits 1 (a
   check failed, as documented in the quickstart), and `validate` keeps validating the given
   directory as-is. Exit 2 is reserved for usage and precondition errors of commands that
   would write.
7. **Hooks are a separate contract from `init`.** Rule 2 still stops `init` from installing
   a kit into a plain folder inside another repository: `cursorfleet init` invoked from an
   ordinary subdirectory exits **2** and performs no writes. There is no nested install.
   Runtime event attribution for a hook that reaches such a folder another way (user-level
   hooks, a copied `hooks.json`) is decided in
   [ADR 0002](0002-storage-layout-and-runtime-directory.md): a non-Git directory nested
   inside an already initialized Git repository inherits that enclosing repository.
   Inheritance never creates a nested `.cursorfleet/` or a nested runtime directory, and it
   never authorizes `init` at that folder. An inner `.git`/gitfile or submodule is a new
   boundary and must not fall back to the outer repository. Missing marker, external
   symlink, ambiguous multi-root and uninitialized roots produce no event and fail open.

### Order of checks

Usage errors first (`--cursor` missing, unknown option), then the target directory exists and
is a directory, then root detection, then the root comparison. Only after all of these pass
does the command read `.cursorfleet/`, the lockfile or `hooks.json`, or build a plan. The
checks apply to `--dry-run` and `--yes` exactly as without them: a dry run in a non-root
directory is exit 2 with no diff.

### Exit codes (`init` and `uninstall`)

| Code | Meaning |
| --- | --- |
| 0 | Success, "already up to date" / "nothing to remove", or a dry run with no drift |
| 1 | The operation was understood and refused or failed: conflicts, drift, the user declined the prompt, a write error |
| 2 | Usage or precondition failure: `--cursor` missing, unknown option, `--path` missing or not a directory, not inside a Git working tree, not at the repository root, `git` not found or timed out while detecting the root |

### Message requirements

All messages go to stderr, contain no traceback, and print every path through `safe_text`
(control and bidi characters neutralised). Each message must:

- say that **nothing was changed**;
- for no Git: say that **Git is required** (a Git repository, as in ADR 0002), name the
  directory that was inspected, and suggest `git init` or running the command from a
  repository root;
- for not at the root: print the **detected repository root** as an absolute path on its own
  line, and print the **suggested command** to run, exactly, with the root quoted when it
  contains spaces or shell-special characters (`cd <root>` followed by the command, or
  the command with `--path <root>`);
- for an unreadable root (bare repository, the `.git` directory itself, git missing, git
  timeout, ownership refused by git): say that no usable working tree was found and give
  git's first error line, truncated.

Illustrative text (the requirements above are normative, the wording is not):

```text
error: Git is required. /tmp/scratch is not inside a Git working tree.
Nothing was changed. Run `git init` there, or run this command from a repository root.

error: /home/me/proj/src is not the repository root.
Detected repository root: /home/me/proj
Nothing was changed. Run:  cd /home/me/proj && cursorfleet init --cursor
```

### `--path`, symlinks, bare repositories, submodules

- **`--path`** names the directory to install into; it is no longer a hint to search upward.
  It is judged by the same rules: it must exist, be a directory, and be a repository root.
  `--path <root>` from any current directory is the supported way to run elsewhere;
  `--path <subdirectory>` is rule 2. The help text must say "repository root", not
  "directory inside the repo". A relative path is resolved against the current directory.
- **Symlinks.** Both the target and the detected root are compared after realpath
  resolution (and case normalisation on Windows and macOS). A symlink that resolves to a
  root is accepted and the resolved root is what the command reports. A symlink that resolves
  to a subdirectory is rule 2 (a link is never a way around the check). A symlink to a
  non-Git directory is rule 1. Writing through symlinked managed paths stays refused by the
  ownership rules above. Windows junctions are treated as links (untested; OPEN on Windows).
- **Bare repositories and the `.git` directory.** There is no working tree, so the target is
  not a root: exit 2, nothing changed, with the unreadable-root message.
- **Submodules.** A submodule root has its own `.git` gitfile, so rule 3 applies mechanically:
  it is a valid root, and from the superproject root the superproject is the root. Whether v0.1
  should *warn* about writing generated files into a submodule, or refuse, is **OPEN** (owner
  decision).
- A `GIT_DIR` or `GIT_WORK_TREE` in the environment must not redirect root detection (the
  existing git runner drops git environment variables; keep it that way).

### Implementation status of this amendment

**Partly implemented** (`cli/commands/_common.py:workspace_root`, `init.py`, `uninstall.py`):

- Outside Git: exit **2**, nothing written, "Git is required" and "Nothing was changed".
- Ordinary subdirectory / `--path <subdirectory>`: exit 2, detected root printed, no plan.
- Nested repository root and linked-worktree root: accepted; a subdirectory of either is
  exit 2 naming that inner/worktree root.
- `--path` help text says "Repository root".
- Unknown `--allow-non-git`: ordinary usage error, exit 2.
- Bare repository / `.git` directory: exit 2, unreadable-root message.
- `doctor` and `validate` print the detected root, common dir, marker status and
  boundary type from `inspect_repository` (follow-ups task 15). They never write.
- Hooks record nothing outside Git. Nested non-Git inheritance is a hook-only contract
  (ADR 0002, implemented); `init` does not walk up.

Live row 17 remains OPEN.

## Amendment 2026-10-04 (init versus runtime for nested directories)

Owner decision. Distinguishes write commands from hook runtime so they are not
collapsed into one walk-up rule. Implemented in code; live row 17b remains OPEN.

- **Init / uninstall:** unchanged from the repository-root amendment above.
  `cursorfleet init` invoked from an ordinary subdirectory still exits **2** and performs
  no writes. There is no nested install. An inner `.git` or submodule is its own root
  (rule 3); an uninitialized inner repository is that inner root, not a fallback to the
  outer repository.
- **Runtime:** a hook running in a non-Git directory nested inside an already initialized
  enclosing repository inherits that repository for event attribution
  ([ADR 0002](0002-storage-layout-and-runtime-directory.md)). Runtime inheritance is
  allowed only for an installation that already exists at the resolved root.
- Walking up for `init` is forbidden. Walking up for runtime attribution is required when
  the marker is present and the detected root is that enclosing initialized repository.

**Implementation status of this amendment.** Init refuses ordinary subdirectories (exit 2,
no writes). Runtime inheritance is implemented in ADR 0002 (follow-ups task 16).
`doctor`/`validate` print the detected root (follow-ups task 15). Live row 17b remains OPEN.
