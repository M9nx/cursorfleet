# Live spike prep (do not run from this document)

This is a hand-off for a human with a real Cursor install. **Do not run the spike
from an agent session.** Every empirical verdict stays **OPEN** until a human
fills the result records in [`empirical-test-plan.md`](empirical-test-plan.md).
M2 and TUI work stay frozen ([`status.md`](status.md)).

The in-repo hook contract for nested non-Git directories (task 16) is implemented.
That is not a Cursor verification.

## Next human steps

Follow [`spike/README.md`](../spike/README.md) in order. Do not skip the
self-test.

1. **Read row 16 first** (raw-capture hygiene) in the empirical test plan, then
   README section 0.
2. From this repository: `python3 spike/capture_hook.py --selftest` and
   `python3 spike/bench_latency.py -n 40` (no Cursor needed).
3. Create a **scratch git repo** (one commit, no real secrets). Copy
   `spike/capture_hook.py` and `spike/hooks.json.example` as in README section 1.
   Commit `.cursor/`. Open that folder in Cursor and trust the workspace.
4. Label the run (`--set-label ide-main`), run README sections 2–5, then analyze
   with `python3 spike/analyze.py`.
5. Repeat the surface subset the test plan names for CLI, Agents Window, and
   worktrees. Keep an out-of-band terminal for cleanup.
6. After analysis: fill `spike/questions.md` and the ADR 0001 matrix. Leave every
   result **OPEN** until the capture is reviewed.

## Analyzer (four identity buckets)

`spike/analyze.py` is already fixed. Q1 reports four buckets separately; do not
collapse them:

- `direct_current_identity`
- `role_only_identity`
- `parent_only_identity`
- `unclassified_identity_candidates`

The VERDICT line is a hint only. Classify by hand per empirical-test-plan row 8.
Parent fields never confirm current-subagent identity. The analyzer has not been
run against a live capture.

## Row 17 / 17b (expected cases; verdict OPEN)

Use scratch folders only. The **code** contract is implemented; Cursor behaviour
is unverified.

| Case | Hook expected | `init` expected |
| --- | --- | --- |
| 17a no enclosing Git | no event, fail open, no writes | exit 2, no writes |
| 17b nested non-Git dir inside an **initialized** root | inherit that root; paths relative to it; no nested `.cursorfleet/` or runtime | exit 2, no writes |
| Inner `.git` / gitfile / submodule | new boundary; do not inherit the outer | inner root is its own root |
| Uninitialized inner repository | no fallback to the outer; no event | inner root only |
| Missing `.cursorfleet/config.toml` at the detected root | no event, fail open | n/a (write commands still require the Git root) |
| External symlink, ambiguous multi-root, uninitialized root | no event, fail open | n/a |

Resolution: tool cwd when available, otherwise `CURSOR_PROJECT_DIR`; realpath;
nearest Git root; require `<repo-root>/.cursorfleet/config.toml` as a regular
file; use that root's git-common-dir. Never continue searching outward after an
inner Git boundary.

## Raw-capture hygiene (row 16)

- Capture directory is `0700`, under `<git-common-dir>/cursorfleet-spike/` (or
  `CURSORFLEET_SPIKE_DIR`). Never commit it.
- Skim `captures.jsonl` before sharing. Residual risk: nested key names,
  `tool_name`, `subagent_type`, `git_branch`.
- Do not run the spike in a repo with real secrets.
- Record the retention deadline. Delete the capture after review. Sign the
  raw-capture line in each result record.
- Evidence paths stay **outside** this repository working tree.

## Freeze

- Every empirical verdict remains **OPEN**.
- Do not claim Cursor behaviour verified from synthetic hook tests.
- Do not resume M2 or TUI work from this prep.
