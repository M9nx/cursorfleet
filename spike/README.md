# CursorFleet M0a spike: Cursor reality capture kit

> **THROWAWAY.** Stdlib-only, not product code. It exists to answer the open
> questions in [`questions.md`](questions.md) with real Cursor payloads before
> any CursorFleet schema is frozen. It is **not** the v0.1 hook entrypoint.

**Status:** the kit is built and self-tested. One sequential Cursor 3.22.7
observation exists and is **UNVERIFIED** (not a row-8 result). That first live
capture is **incomplete**: it was taken before `parent_tool_call_id` and
`child_conversation_id` were on the ID allowlist, so those scalars were
dropped. Copy the **updated** `capture_hook.py` into the scratch repo and start
a **fresh labeled** capture. Do **not** append to the older `captures.jsonl`.
A later Cursor 3.22.7 Linux capture did retain `parent_tool_call_id` (45
comparable inner events, 45 matches, 0 mismatches/collisions) but did **not**
observe a parallel/background lifecycle: two-agent attempts showed
`subagentStart=2`, `subagentStop=0`, `is_parallel_worker=true` count=0,
`overlapping_subagent_windows=0`, Task `run_in_background` missing=2. After
`is_background: true` on the custom agent, a full Cursor reload, and a fresh
`/cf-writer` chat, a one-agent probe still had Task `run_in_background`
missing=1. That is an observation, not a verdict. Formal repeated parallel
classification has **not** run. Do **not** start formal row 8 until the
analyzer prints `ROW 8 READINESS: READY: ...`. `BLOCKED/OPEN` is not `FAIL`
and is not a Q1 result. Q1 and Q2 stay **OPEN**. Everything in
`docs/adr/0001-cursor-capabilities.md` marked UNVERIFIED stays provisional
until row-8 repetitions classify it. Raw captures stay private and outside
this repository.

## What the kit does and does not record

`capture_hook.py` appends one sanitized JSON line per hook call to
`captures.jsonl`. It records event name, timings (wall + monotonic latency),
pid/ppid, key names and value **types**, and values only for IDs
(`conversation_id`, `generation_id`, `session_id`, `subagent_id`,
`subagent_type`, `parent_conversation_id`, `parent_tool_call_id`,
`child_conversation_id`, `tool_use_id`, `tool_call_id`,
`tool_name`, `git_branch`, `cursor_version`), small enums, booleans and
counters. `parent_tool_call_id` and `child_conversation_id` are optional
opaque scalars, stored only when they are valid bounded identifier strings
(same treatment as `tool_call_id` / `subagent_id`). Paths are reduced to a
basename plus a git kind (`main | linked-worktree | submodule-or-other | none`).

It never writes prompts, thinking, file contents, commands, tool inputs or
outputs, edits, summaries, emails, transcript paths or full paths. It prints
`{}` (or `{"permission":"allow"}` for permission hooks) and always exits 0.

Residual risk to know about: nested **key names** (for example the keys of
`tool_input`) are recorded when they are lowercase snake_case, and `tool_name`,
`subagent_type` and `git_branch` are recorded verbatim. Skim
`captures.jsonl` before sharing it. The hooks still *receive* sensitive content
in memory (`afterShellExecution.output`, `afterFileEdit.edits`,
`subagentStart.task`); the kit simply discards it. Do not run the spike in a
repo with real secrets.

The kit deliberately does **not** register `afterAgentThought`,
`afterAgentResponse`, `beforeSubmitPrompt` or `beforeReadFile`, so thinking,
response text, prompts and file contents are never delivered to it.

## Prerequisites

- Cursor (note the version: `cursor --version` or Help > About) and optionally
  the Cursor CLI (`agent`). Cursor CLI install: `curl https://cursor.com/install -fsS | bash`.
- Python 3.9+ on `PATH` as `python3` (macOS/Linux) or `python` (Windows).
- A **scratch git repo with at least one commit.** Do not use a real project.

## 0. Run the self-test and benchmark (no Cursor needed)

```sh
python3 spike/capture_hook.py --selftest      # privacy + latency assertions
python3 spike/bench_latency.py -n 40          # writes spike/results/latency-<platform>.json
```

Run the benchmark on every OS you care about (Linux result already recorded in
`spike/results/latency-linux.json`; macOS and Windows are still open).

## 1. Create the scratch repo and install the hooks

```sh
mkdir ~/cf-spike-scratch && cd ~/cf-spike-scratch
git init -q && git commit -q --allow-empty -m "init"
mkdir -p .cursor/hooks .cursor/agents
cp /path/to/cursorfleet/spike/capture_hook.py .cursor/hooks/capture_hook.py
cp /path/to/cursorfleet/spike/hooks.json.example .cursor/hooks.json
# Must be the updated hook (parent_tool_call_id + child_conversation_id on the
# ID allowlist). After recopying, start a NEW labeled capture directory/label.
# Do not append to an older captures.jsonl that predates this allowlist.
```

Windows (PowerShell): copy `hooks.windows.json.example` instead (it calls
`python`, not `python3`). If your Python is only available as `py`, edit the
`command` strings to `py -3 .cursor/hooks/capture_hook.py <event>`. Hook
commands run through the platform shell; the `<event>` argument is a fallback
so permission hooks can still answer correctly if stdin is malformed.

Add two custom subagents (names are deliberately distinctive so you can look
for them in `subagent_type`):

```sh
cat > .cursor/agents/cf-reviewer.md <<'EOF'
---
name: cf-reviewer
description: Read-only reviewer. Use proactively when asked to review a file.
readonly: true
---
Read the file you are told about and reply with one sentence. Do not edit files.
EOF
cat > .cursor/agents/cf-writer.md <<'EOF'
---
name: cf-writer
description: Writes a tiny note file when asked. Use for creating notes.
---
Create the file you are told about with one line of text, then reply "done".
EOF
git add .cursor && git commit -q -m "spike hooks and agents"
```

**Commit the `.cursor/` directory.** Cursor-managed worktrees are checkouts of
the branch, so untracked hook files will not exist there and you would capture
nothing from worktrees.

Open the folder in Cursor and trust the workspace (project hooks only run in
trusted workspaces). Check **Customize > Hooks** and the **Hooks** output
channel to see the hooks load. Cursor reloads `hooks.json` on save; restart
Cursor if they do not appear. Then label the run:

```sh
python3 .cursor/hooks/capture_hook.py --set-label ide-main
python3 .cursor/hooks/capture_hook.py --print-capture-dir   # <git-common-dir>/cursorfleet-spike
```

The capture directory lives inside `.git/`, so it is shared by every linked
worktree of this repo and is never tracked. Set `CURSORFLEET_SPIKE_DIR` to
override (note: the IDE does not inherit your shell env; the `LABEL` file is
the reliable way to tag runs).

## 2. Run A: custom subagent in the IDE (Q1, Q2)

In Agent chat, with the main (parent) agent:

> Use the cf-reviewer subagent to review README.md (create it with one line first if it doesn't exist), then use the cf-writer subagent to create notes/a.txt.

Run it sequentially so you get clean subagent windows. Let it finish. Also run
one explicit invocation: `/cf-reviewer review README.md`.

Now analyze:

```sh
python3 spike/analyze.py            # run from the scratch repo, or pass the path
```

Read the **Q1** and **Q2** sections. Q1 asks whether tool hooks inside a subagent
identify the *current subagent instance*. The analyzer reports four categories
separately: `direct_current_identity` (a unique current-instance id, for example a
`subagent_id` that equals a captured `subagentStart.subagent_id` on every occurrence),
`role_only_identity` (`subagent_type` and similar), `parent_only_identity`
(`parent_conversation_id`, or a `conversation_id` equal to the parent's; this can never
confirm identity) and `unclassified_identity_candidates` (id-like keys with undocumented
meaning, an id that does not link to a start, or a deterministic-link candidate such as
`parent_tool_call_id`; never auto-promoted). `parent_tool_call_id` is **not** parent-only
and is **not** EXACT until row 8 concurrent repetitions verify it. `session_id` is
session-level correlation only; it is not a Q1 identity candidate. Its VERDICT line
follows CONFIRMED (direct only), PARTIAL (role only), OPEN (only unclassified candidates,
or no data) and REFUTED (parent only, or nothing found inside subagent windows) and is a
hint: classify by hand per `docs/empirical-test-plan.md` row 8. Q2 asks whether
`subagent_type` shows `cf-reviewer`, `cf-writer`, or only `generalPurpose`.

Linkage is reported as evidence (`observed` / `comparable` / `matches` /
`mismatches` / `unavailable` / `collisions`), not bare equality counters. A
missing field is **unavailable**, never "0 matches" as a refutation. The first
Cursor 3.22.7 capture dropped `parent_tool_call_id` and `child_conversation_id`
at the hook, so those relationships are unavailable there. Re-analyze only after
a fresh labeled capture with the updated hook.

One unverified sequential Cursor 3.22.7 observation saw optional `subagent_id` and
`child_conversation_id` on `subagentStop` (docs list neither). The analyzer pairs
start/stop by that optional id when present, else by type+order; it associates inner
tool events by `parent_tool_call_id`, then `child_conversation_id`, then temporal
fallback (temporal is never treated as exact). Inner hooks may use a child
`conversation_id`, so a parent-`conversation_id` window match alone will miss them.
Do not promote Q1 or Q2 from OPEN on that single run. A later Cursor 3.22.7
Linux capture retained `parent_tool_call_id` on comparable inner events but
did not observe overlapping windows, `is_parallel_worker=true`, or Task
`run_in_background=true` with matched start/stop. Do not start formal row 8
until the analyzer readiness line is `READY`.

## 3. Run B: two subagents in parallel with worktree isolation (Q3, Q4, Q5)

```sh
python3 .cursor/hooks/capture_hook.py --set-label ide-parallel-wt
```

Prompt (the docs say isolation is requested in the prompt, not configured):

> Launch two subagents in parallel, each in its own environment (isolated git worktree): cf-writer creates notes/one.txt and cf-writer creates notes/two.txt. Run them concurrently.

Afterwards, in the scratch repo: `git worktree list` (record how many
worktrees Cursor created and where; do not paste your home path into issues).
Analyze again and read **Q3/Q4** (is `workspace_roots` a linked worktree, and
does one capture file contain events from several worktrees) and **Q5**
(`overlapping_subagent_windows`, `tool_calls_started_while_another_open`,
`max_concurrent_hook_processes`).

Also try the Agents Window: start an agent from the Agents Window into a
worktree (label `agents-window-wt` first), run a prompt that edits one file
and runs one shell command. Then `/worktree <task>` and `/best-of-n` from the
IDE (labels `ide-worktree-cmd`, `ide-best-of-n`).

## 4. Run C: Cursor CLI (Q3)

```sh
python3 .cursor/hooks/capture_hook.py --set-label cli
agent -p --force "Use the cf-reviewer subagent to review README.md, then run 'git status' in the shell."
```

`--force` is required for file changes in print mode; the scratch repo makes
that safe. Also try an interactive `agent` session once (label `cli-interactive`).
Questions: do hooks fire at all (the docs only guarantee `workspaceOpen` runs in
the CLI), which events, and which `cursor_version` is reported? The CLI
inherits your shell env, so you can also use
`CURSORFLEET_SPIKE_DIR=/tmp/cf-cli agent -p ...` to separate it.

## 5. Context compaction, failures, and the rest (Q6, token data)

- Trigger a tool failure (ask the agent to `cat` a file that does not exist)
  to capture `postToolUseFailure`.
- `preCompact` needs a long conversation or a manual compact. If you can get
  it, note whether `context_*` counters are present: they are the only
  token-ish data hooks expose.
- Run `python3 spike/bench_latency.py -n 40` on Windows and macOS too.

## 6. Final analysis and what to hand back

```sh
python3 spike/analyze.py > spike/results/analysis-$(date +%Y%m%d).txt
python3 spike/analyze.py --json > /tmp/analysis.json
```

Then answer each item in [`questions.md`](questions.md) with
`CONFIRMED / REFUTED / PARTIAL` plus the evidence line from the analysis, and
update `docs/adr/0001-cursor-capabilities.md` (move items out of
UNVERIFIED). Only after review, copy a **hand-sanitized subset** of
`captures.jsonl` lines to `tests/fixtures/` with the recorded `cursor_version`.
The capture file is already sanitized by design, but still read it first.

## Cleanup

```sh
rm -rf "$(git rev-parse --git-common-dir)/cursorfleet-spike"
rm -rf .cursor/hooks .cursor/hooks.json .cursor/agents/cf-*.md   # then commit
git worktree list && git worktree prune
```

## Files

- `capture_hook.py`: the hook, plus `--selftest`, `--set-label`, `--print-capture-dir`.
- `hooks.json.example`, `hooks.windows.json.example`: passive hooks only.
- `analyze.py`: per-event key shapes, identity evidence in four separate categories (direct
  current identity, role only, parent only, unclassified candidates including
  `parent_tool_call_id`; `session_id` is reported only as session correlation), the verdict
  is a hint, start/stop pairing by optional stop `subagent_id` else type+order, inner-tool
  association by task/child ids then temporal (never exact), linkage evidence
  (matches / mismatches / unavailable / collisions; missing is never a 0-match
  refutation), Task `run_in_background` and `is_parallel_worker` true/false/missing
  counts, tool outcomes by hook event and tool name, lifecycle completeness
  (starts / matched stops / unmatched starts), a row-8 readiness gate (`READY` vs
  `BLOCKED/OPEN`, never `FAIL`, never a Q1 verdict), latency percentiles, worktree
  flags, interleaving evidence. Tolerates torn lines and odd records. Unit-tested
  with synthetic records in `tests/unit/test_spike_analyze.py`.
- `bench_latency.py`: steady-state process wall-clock latency (fresh process, warm cache); results in `results/`.
- `questions.md`: the open questions and how each is answered.
- `doc_examples/`: hand-built, doc-derived example payloads. **Not captured.**
