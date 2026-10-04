## CursorFleet

This repository uses [CursorFleet](https://github.com/M9nx/cursorfleet) (unofficial, not affiliated with Anysphere) to observe agent teams.

- Roster: `.cursorfleet/roster.toml`. Generated subagents: `.cursor/agents/{{name_prefix}}*.md`. Do not edit generated files by hand; change the roster and re-run `cursorfleet init --cursor`.
- Multi-agent workflow: the `cursorfleet-coordinator` skill. Handoffs and plans: `{{work_dir}}/`.
- Report concrete progress and real command results. Do not paste reasoning.
