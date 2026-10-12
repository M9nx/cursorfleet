# B1 Active Run prototype sign-off

Status: **accepted (engineering, 2026-10-12).**

Prototype building blocks:

- `cursorfleet.state.run_builder.build_active_run`
- Unit tests in `tests/unit/test_run_builder.py` (including run-scoped git fields)

**TUI:** Active run is the default screen (`a`). Set `CURSORFLEET_PROTOTYPE=overview` to restore the
session-centric archive as the landing view.

Go/no-go: would you use this daily on a real repo?

**Maintainer answer (2026-10-12):** Yes for observe-only multi-chat tasks **with explicit run attach**;
attach ceremony remains the main UX debt (see B0 attach-picker decision).

**Screenshot:** Maintainer to add `docs/evidence/active-run-screenshot.png` from a live two-chat task
before Product Hunt gate; not committed in this pass (no raw spool in repo).
