# Installation

CursorFleet needs **Python 3.11+** and **git**. It is **not on PyPI**. Until a
release exists, install from a git checkout.

**Unofficial and pre-alpha.** CursorFleet is not affiliated with or endorsed by
Anysphere or Cursor.

## From a checkout

```bash
git clone https://github.com/M9nx/cursorfleet && cd cursorfleet
uv tool install .            # or: pipx install .
cursorfleet --version
```

`uv` is documented at [docs.astral.sh/uv](https://docs.astral.sh/uv/). `pipx`
is an alternative for the same console scripts.

Once a first release exists, the intended commands are
`uv tool install cursorfleet` or `pipx install cursorfleet`. Those are **not**
available yet.

## Check the hook entry point

Hooks invoke `cursorfleet-hook` by name. Cursor must be able to find it on
`PATH` (restart Cursor after installing):

```bash
cursorfleet --version
echo '{}' | cursorfleet-hook
```

The hook prints a safe reply (`{"permission":"allow"}`) and exits 0. It is
stdlib-only on the hot path and **fails open**: an internal error still exits 0
with the reply that hook type requires, so Cursor is not blocked by
CursorFleet.

## Optional watch extra

```bash
uv tool install ".[watch]"
```

This adds `watchfiles` so the dashboard can react to file changes instead of
polling. Without it, the TUI polls on the default interval.

## Development install

From the repository root, for contributors:

```bash
uv sync --all-extras
uv run cursorfleet --version
```

See [Contributing](../contributing.md).

## Requirements the kit will not waive

- **Git is required** for `cursorfleet init`. There is no `--allow-non-git`
  flag, environment variable, or config key.
- Run `init` from a **Git repository root** (a linked-worktree root and a
  genuine nested repository are valid roots). An ordinary subdirectory or a
  non-git folder exits 2 and writes nothing.
