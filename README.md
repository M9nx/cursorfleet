# CursorFleet

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Status: pre-alpha](https://img.shields.io/badge/status-pre--alpha-orange.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)

A local TUI and workflow harness for Cursor agent teams: see which local agents and worktrees
are doing what, from passive hooks and read-only git, without sending anything anywhere.

> **Unofficial:** CursorFleet is not affiliated with or endorsed by Anysphere or Cursor. "Cursor" is a trademark of its respective owner.

## Status

**Pre-alpha, not released.** There is no PyPI package, tag or GitHub release yet.

- v0.1 is **Observe**: no enforcement, no forced approvals, and no cloud-agent visibility
  (local Cursor sessions only). It is not a security boundary: a malicious or prompt-injected
  agent can bypass or forge what it shows ([threat model](docs/threat-model.md)).
- **Not yet verified against a live Cursor.** Hook payload shapes come from Cursor's
  documentation; the open questions (agent identity inside subagent tool hooks, custom
  subagent names, CLI and Agents Window behaviour, hook latency outside Linux) are tracked in
  [ADR 0001](docs/adr/0001-cursor-capabilities.md) and marked **PROVISIONAL** throughout.
- **Development is frozen at the M0a spike.** The existing observer and TUI code is
  implemented, provisional and unvalidated against live Cursor; no new M2/TUI work until the
  live spike is run ([status](docs/status.md),
  [empirical test plan](docs/empirical-test-plan.md)).
- **Supported surface: the local Cursor IDE (desktop) only**, once the spike confirms it.
  The Cursor CLI, the Agents Window, Cursor-managed and manual worktrees, parallel
  subagents and cloud agents are not claimed.
- The name "CursorFleet" is a working name; the final name is a release gate
  ([ADR 0005](docs/adr/0005-naming-and-trademark.md)).
- Linux is the tested platform; macOS and Windows are CI-tested only
  ([platform support](docs/platform-support.md)).
- Cursor is the only officially supported IDE; internals are adapter-ready but no other
  adapter is planned for v0.1.
- Local only: no network calls, no telemetry, no accounts (checked by a test). It never stores
  prompts, model thinking, responses, file contents, command output, environment variables,
  emails or transcript paths ([privacy](docs/privacy.md)).

## Install

Needs Python 3.11+ and git. Until it is published, install from a checkout:

```bash
git clone https://github.com/M9nx/cursorfleet && cd cursorfleet
uv tool install .            # or: pipx install .
cursorfleet --version
```

(Once released: `uv tool install cursorfleet` or `pipx install cursorfleet`; see the
[release checklist](docs/release-checklist.md).)

## Quickstart

```bash
cursorfleet init --cursor --dry-run   # review the exact diff first
cursorfleet init --cursor             # install the observe-only hooks and kit (once per repo)
# ...work with Cursor agents as usual...
cursorfleet doctor                    # check hooks, runtime dir and spool
cursorfleet tui                       # open the dashboard (needs an interactive terminal)
cursorfleet status --json             # stable machine-readable snapshot for scripts
cursorfleet uninstall                 # remove exactly what init added
```

Full walkthrough: [docs/quickstart.md](docs/quickstart.md). No Cursor handy? Run the
[synthetic demo](docs/demo.md): `scripts/demo.sh`.

Dashboard keys: `o` overview, `l` timeline, `w` worktrees, `g` gates, `e` evidence, `v`
violations (v0.2 placeholder), `/` filter, `p` pin, `t` tiles (160+ columns), `r` re-read,
`?` help, `q` quit. The TUI only observes: silence shows as STALE / OFFLINE, never idle, and
gate tiles are heuristic and non-authoritative, not proof that anything passed. Details:
[docs/tui.md](docs/tui.md).

## Documentation

[Quickstart](docs/quickstart.md) · [governance model](docs/governance.md) ·
[demo](docs/demo.md) · [kit reference](docs/kit.md) · [TUI](docs/tui.md) ·
[`status --json`](docs/status-json.md) · [product contract](docs/product-contract.md) ·
[architecture](docs/architecture.md) · [privacy](docs/privacy.md) ·
[threat model](docs/threat-model.md) · [security review](docs/security-review-v0.1.md) ·
[platform support](docs/platform-support.md) · [hook latency](docs/hook-latency.md) ·
[release checklist](docs/release-checklist.md) · [project status](docs/status.md) ·
[empirical test plan](docs/empirical-test-plan.md) · [follow-ups](docs/follow-ups.md) ·
[docs-site plan](docs/docs-site-plan.md) · [ADRs](docs/adr/README.md) ·
[changelog](CHANGELOG.md)

## Development

```bash
uv sync --all-extras
uv run cursorfleet --version
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
```

Regenerate schemas with `uv run python scripts/gen_schemas.py`. See
[CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md) and [SECURITY.md](SECURITY.md).

## License

MIT, see [LICENSE](LICENSE).
