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
3. Create a **scratch git repo** (one commit, no real secrets). Copy the
   **updated** `spike/capture_hook.py` (the allowlist now keeps scalar
   `parent_tool_call_id` and `child_conversation_id`) and
   `spike/hooks.json.example` as in README section 1. Commit `.cursor/`. Open
   that folder in Cursor and trust the workspace.
4. Start a **fresh labeled** capture (`--set-label ide-main-<date>` or similar).
   Do **not** append to the older `captures.jsonl` from the first Cursor 3.22.7
   run: that file lacks the two new ID scalars. Run README sections 2–5, then
   analyze with `python3 spike/analyze.py`. A later Cursor 3.22.7 Linux capture
   did retain `parent_tool_call_id` (see the observation below). Do **not**
   start formal row 8 until `analyze.py` prints
   `ROW 8 READINESS: READY: required parallel/background lifecycle observed with matched start/stop`.
   If it prints `BLOCKED/OPEN`, leave Q1/Q2 OPEN and do not infer a Q1 verdict.
5. Repeat the surface subset the test plan names for CLI, Agents Window, and
   worktrees. Keep an out-of-band terminal for cleanup. If readiness is still
   `BLOCKED/OPEN` after IDE two-agent prompts, the remaining experiment is a
   **different surface** (Agents Window background control, or CLI), then
   re-analyze. Do not claim Cursor can run parallel/background subagents if that
   capture still lacks overlapping windows, `is_parallel_worker=true`, and Task
   `run_in_background=true` with matched start/stop. Sequential README 2 / R8.3
   windows can still be collected; they cannot close row 8.
6. After analysis: fill `spike/questions.md` and the ADR 0001 matrix. Leave every
   result **OPEN** until the capture is reviewed.

## Analyzer (four identity buckets)

Q1 reports four buckets separately; do not collapse them:

- `direct_current_identity`
- `role_only_identity`
- `parent_only_identity` (`parent_conversation_id` only, never `parent_tool_call_id`)
- `unclassified_identity_candidates` (includes `parent_tool_call_id` as a
  deterministic-link candidate, not EXACT until row 8 concurrent repetitions)

`session_id` is session-level correlation only; it is not reported in any of
the four Q1 buckets. Linkage equalities are evidence structures
(matches / mismatches / unavailable / collisions). Missing values are
**unavailable**, never "0 matches".

The VERDICT line is a hint only. Classify by hand per empirical-test-plan row 8.
`parent_conversation_id` never confirms current-subagent identity. Q1 and Q2
remain **OPEN**. One sequential Cursor 3.22.7 observation is UNVERIFIED; do not
promote it. That run also showed optional `subagent_id` and `child_conversation_id`
on `subagentStop` (not guaranteed) and inner tool hooks using a child
`conversation_id` plus `parent_tool_call_id`, but the first capture hook dropped
those two scalars. Copy the updated hook and start a **fresh labeled** capture;
do not append to or re-analyze the older jsonl as row-8 evidence.

`analyze.py` also reports sanitized background flags and a row-8 readiness gate
(not a Q1 verdict): `READY` only when overlapping subagent windows **or**
`is_parallel_worker=true` **or** Task `run_in_background=true` is observed, **and**
those parallel instances have matched start/stop. Otherwise it prints
`BLOCKED/OPEN` (never `FAIL`).

## Cursor 3.22.7 Linux observation (not a verdict)

Sanitized counts from a later Cursor 3.22.7 Linux capture (raw captures stay
private and outside this repository). This is an observation, not a Q1/Q2 result
and not a claim that Cursor can or cannot do parallel work in general.

- Two-agent attempts repeatedly produced: `subagentStart=2`, `subagentStop=0`,
  `is_parallel_worker=true` count=0, `overlapping_subagent_windows=0`,
  Task `run_in_background` missing=2.
- `parent_tool_call_id` linkage stayed deterministic on comparable inner events:
  45 comparable, 45 matches, 0 mismatches, 0 collisions. It matched every
  comparable inner event.
- Custom-agent definition was then set to `is_background: true`; Cursor fully
  reloaded; a fresh chat ran `/cf-writer`. The one-agent probe still showed
  Task `run_in_background` missing=1.
- Formal repeated parallel classification (row 8 R8.1 / R8.2) has **not** run.
  Analyzer readiness for that capture is `BLOCKED/OPEN`. Q1 and Q2 stay **OPEN**.

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
