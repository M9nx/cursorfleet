# Quickstart

> **Unofficial and pre-alpha.** CursorFleet is not affiliated with or endorsed by Anysphere or
> Cursor. v0.1 only *observes* local Cursor agent sessions: no enforcement, no forced
> approvals, no cloud-agent visibility. It has not yet been verified against a live Cursor
> (see [status](status.md)), so treat what the dashboard shows as provisional.
>
> **Supported surface:** the local Cursor IDE (desktop) only, once the live spike has
> confirmed it. The Cursor CLI, the Agents Window, worktrees opened by Cursor or by hand,
> parallel subagents and cloud agents are not claimed to work.

## 1. Install

CursorFleet needs Python 3.11 or newer and `git`. It is **not on PyPI yet**; until the owner
publishes it, install from a checkout or a built wheel.

```bash
# from a checkout (needs uv: https://docs.astral.sh/uv/)
git clone https://github.com/M9nx/cursorfleet && cd cursorfleet
uv tool install .          # or: pipx install .

# once published (see docs/release-checklist.md), this will be:
#   uv tool install cursorfleet     # or: pipx install cursorfleet
```

Check it is on your `PATH`; the hooks call `cursorfleet-hook` by name, so Cursor must be able to
find it (restart Cursor after installing):

```bash
cursorfleet --version
echo '{}' | cursorfleet-hook     # prints a safe reply ({"permission":"allow"}) and exits 0
```

Optional: `uv tool install ".[watch]"` adds `watchfiles` so the dashboard reacts to changes
instead of polling.

## 2. Install the kit in a repository

Run from the **root** of the git repository you work on with Cursor (not a
subdirectory). Git is required; there is no `--allow-non-git` flag
([ADR 0009](adr/0009-install-uninstall-ownership.md)).

```bash
cd /path/to/your/repo                 # the repository root
cursorfleet init --cursor --dry-run   # print the exact diff, write nothing
cursorfleet init --cursor             # show the diff again and ask before writing
```

A non-git folder, or an ordinary subdirectory of a repository, must refuse: exit 2,
change nothing, and (from a subdirectory) print the detected repository root.
`--path` must itself be a repository root. A genuine nested repository and a
linked-worktree root are valid roots. **Divergence:** today's command walks up to the
enclosing repository from a subdirectory and exits 1 (not 2) outside Git.

This adds passive hooks to `.cursor/hooks.json` (yours are preserved and merged), a
small roster of subagent files under `.cursor/agents/`, rules and skills, an `AGENTS.md`
block, and `.cursorfleet/` configuration. Nothing is written without a visible diff and
confirmation (`--yes` skips only the prompt). Hooks never read prompts, model thinking, file
contents or command output; see [privacy](privacy.md).

The installed hook set is currently twelve; the accepted decision is nine
([ADR 0007](adr/0007-narrower-v01-hook-policy.md)), and the code will be changed after the
live spike. Hook behaviour inside worktrees is unverified.

Commit the generated `.cursor/` and `.cursorfleet/` files: Cursor-managed worktrees are
checkouts of your branch, so untracked hook files would not exist there.

Worktree caution: Cursor creates and deletes its own worktrees and, by default, cleans up
beyond 25 per machine (`cursor.worktreeMaxCount`), which can remove a worktree that still
holds unmerged work. CursorFleet never creates or deletes worktrees. Commit and push what
you care about ([ADR 0012](adr/0012-roster-and-worktree-ownership.md)).

## 3. Check health

```bash
cursorfleet doctor            # runs `cursor --version` to report the Cursor version
cursorfleet doctor --no-probe-cursor
```

`doctor` checks Python, the hook binary on `PATH`, git, the runtime directory and its
permissions, the config, drift between installed files and the lockfile, and lists the hooks
Cursor would merge. A warning that your Cursor version is not in `[cursor].validated_versions`
is expected until you have verified one yourself. Exit code 1 means a check *failed*; warnings
exit 0. `cursorfleet validate` checks config, roster, generated files and work artifacts.

## 4. Use Cursor as usual, then watch

Open the repository in Cursor, trust the workspace (project hooks only run in trusted
workspaces) and start agents. Hooks append small sanitized events to
`<git-common-dir>/cursorfleet/` (inside `.git`, never in the working tree).

```bash
cursorfleet tui               # the dashboard (needs an interactive terminal)
cursorfleet status            # the same data as plain text
cursorfleet status --json     # stable machine-readable form, see docs/status-json.md
```

TUI keys: `o` overview, `l` timeline, `w` worktrees, `g` gates (heuristic, non-authoritative), `e` evidence,
`/` filter, `p` pin, `t` tiles (160+ columns), `r` re-read, `?` help, `q` quit. Silence shows
as STALE or OFFLINE, never as idle. Details: [tui.md](tui.md).

## 5. Replay, export and purge

```bash
cursorfleet replay <session-id>              # rebuild one session from the spool twice; must match
cursorfleet events export --sanitized -o events.jsonl   # check branch names and paths before sharing
cursorfleet events purge --dry-run           # what the retention policy would delete
cursorfleet events purge --older-than 7d     # delete older spool data
cursorfleet events purge --all --yes         # delete every event and rotate the hash key
```

## 6. Uninstall

```bash
cd /path/to/your/repo             # same repository-root rule as init
cursorfleet uninstall --dry-run   # the diff of what would be removed
cursorfleet uninstall             # removes only what the lockfile lists, while hashes still match
```

Files you edited are reported and left alone (`--force` removes them). `init` followed by
`uninstall` restores the tree byte for byte, including a pre-existing `hooks.json` and
`AGENTS.md`. Runtime data stays in `.git/cursorfleet/` until you run `events purge --all`.

## Try it without Cursor

[`docs/demo.md`](demo.md) runs the whole flow on a throwaway repository with synthetic,
clearly labelled payloads: `scripts/demo.sh`.

## Troubleshooting

- *No events appear.* Run `cursorfleet doctor`. Typical causes: `cursorfleet-hook` not on the
  `PATH` Cursor sees (GUI apps do not inherit your shell profile), the workspace is untrusted,
  or hooks were not reloaded.
- *`runtime directory ... refusing`.* The directory under `.git/cursorfleet` is a symlink,
  owned by someone else or group-writable; fix its ownership/mode or remove it. CursorFleet will
  not use a directory it cannot trust.
- *The hook errors out.* It cannot: hooks always exit 0 and answer `{}` (or
  `{"permission":"allow"}`) on any internal failure, so Cursor is never blocked by CursorFleet.
