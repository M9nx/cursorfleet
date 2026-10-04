# ADR 0005: Naming and trademark

- Status: provisional (`CursorFleet` is a working name; the public name is decided at a release gate)
- Date: 2026-10-04
- Deciders: project owner (M9nx)
- Evidence level: assumption (no registry check in this pass; no legal advice sought)
- Supersedes: none (revises this ADR's own earlier "accepted" status in place, which is allowed because the decision was never validated)
- Superseded by: none
- Related ADRs: 0000 (process), 0009 (everything the installer writes carries the name), 0002 (runtime directory name)
- Implementation status: Implemented as the working name. Every name listed under "What would change" is in the code and docs today. Nothing has been renamed, registered or published.
- Review trigger: any of: Anysphere or counsel objects; the owner chooses a public name; a registry check shows `cursorfleet` is taken; the first public release candidate
- Release gate: all three of: (1) the public name is chosen and uses no third-party mark, (2) availability is verified on PyPI, npm and GitHub on the day of the decision, (3) a trademark review has been done. Until then no package is published and no public docs site goes up.

## Context

- "Cursor" is a trademark of Anysphere. A product named `CursorFleet` embeds that mark
  and could draw a naming complaint.
- Per the reviewed plan, `cursorfleet` is free on PyPI and has no GitHub name collision.
  This was **not re-checked** here. Treat it as unverified.
- The repo started as `agentdeck`; the plan renamed it to `M9nx/cursorfleet`.

## Decision

- **CursorFleet is a working name.** It is used in the code, docs and generated files for
  now. It is not a committed public name.
- The **public name, registry availability (PyPI, npm, GitHub) and a trademark review are
  release gates** for v0.1.0. They are decided and checked together, near release, not now.
- **`fleet-for-cursor` is not a neutral fallback.** It still contains the Cursor mark, so
  it carries the same naming risk as `CursorFleet` and only changes the form. It is
  withdrawn as a fallback. If the gate fails, the fallback must be a name **without any
  third-party mark**, chosen at the gate. No fallback candidate is nominated now.
- **Keep the unofficial / non-affiliation notice**, in the README, docs front matter, the
  `--help` epilog, the PyPI long description and first-run output: "Unofficial: not
  affiliated with or endorsed by Anysphere or Cursor. 'Cursor' is a trademark of its
  respective owner."
- Use "Cursor" only descriptively ("works with Cursor"), never as a logo, never in a way that
  implies endorsement, with no Cursor logo, colours or imitation of its branding.
- This is an engineering note, not a legal opinion.

### What would need renaming if the name changes

- Distribution and import package: `pyproject.toml` `name`, `src/cursorfleet/`, every
  `import cursorfleet`.
- CLI entry points: `cursorfleet` and `cursorfleet-hook`. The hook command is written into
  users' `.cursor/hooks.json`, so installed repositories need a re-`init` or `uninstall`
  first.
- Committed config directory `.cursorfleet/` (`config.toml`, `roster.toml`, `work/`,
  `install.lock.json`).
- Runtime directory `<git-common-dir>/cursorfleet/` and the spike's `cursorfleet-spike/`.
- Generated files and ids: `.cursor/rules/cursorfleet-*.mdc`, `.cursor/skills/cursorfleet-*`,
  the `cf-` subagent prefix, the managed-block markers `<!-- cursorfleet:begin ... -->` in
  `AGENTS.md`.
- Schema ids and `$id` URLs (`cursorfleet.status/..`, `cursorfleet.artifact/..`,
  `https://raw.githubusercontent.com/M9nx/cursorfleet/...`), and `schemas/*.json`.
- Environment variables `CURSORFLEET_*`.
- Repository name and URLs (`M9nx/cursorfleet`), README, all docs, CHANGELOG, workflows,
  trusted-publisher registration, any docs-site domain.
- A one-time migration that reads the old directories and lockfile, and rewrites or removes
  old hook entries, must ship with the rename.

## Consequences

- Positive: no commitment to a name that has not been checked; the unofficial notice stays.
- Negative / costs: a late rename touches installed hooks and committed `.cursorfleet/`
  directories; the cost grows with every user, so the gate should be passed early.
- Follow-ups (owner): choose the public name; verify PyPI, npm and GitHub availability the
  same day; run a trademark search; add the notice to PyPI metadata.

## Open questions

- What name without a third-party mark is both discoverable and unambiguous?
- Is a descriptive "for Cursor" subtitle acceptable in the package description?

## Alternatives considered

- Keep `AgentDeck`: rejected earlier; the project is Cursor-only for v0.1 and the name
  would hide that.
- `fleet-for-cursor` as a nominative-use fallback: withdrawn, see above.
- A name without "Cursor" from the start: the safest option and the likely outcome of the
  gate; deferred because the name is not needed until publication.
