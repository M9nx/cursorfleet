# Doc-derived example payloads (NOT captured)

These files were **hand-built from the examples in the Cursor hooks reference**
(https://cursor.com/docs/hooks, fetched 2026-10-04). They are **not** payloads
captured from a live Cursor session and **must not be used as contract-test
fixtures or as evidence of real Cursor behaviour.**

- Base fields (`conversation_id`, `model`, ...) were added to every event
  because the docs say all hooks receive them. Their values are placeholders
  (`doc-example-conversation`, `0.0.0-doc-example`).
- Event-specific fields and example values come from the docs. Where the docs
  show a placeholder like `<full terminal command>` it is kept verbatim.
- `_doc_derived_not_captured: true` is an extra marker key that real Cursor
  never sends. `capture_hook.py` records it as `<odd-key>`.
- `subagentStop` has no `subagent_id` because the docs list none.

Uses: `python3 spike/capture_hook.py --selftest` replays them to check the
hook accepts every documented shape and leaks none of their content;
`bench_latency.py` uses `preToolUse.doc-derived.json` as stdin.
Real fixtures belong in `tests/fixtures/` only after a captured, reviewed,
`cursor_version`-stamped run (see `spike/README.md`).
