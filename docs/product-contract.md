# Product contract

CursorFleet is an **unofficial** local TUI and workflow harness for Cursor agent
teams. It is not affiliated with or endorsed by Anysphere or Cursor
([ADR 0005](adr/0005-naming-and-trademark.md)).

Status markers: **PROVISIONAL** means the behavior depends on Cursor facts not yet
captured live ([ADR 0001](adr/0001-cursor-capabilities.md), section B).

## What CursorFleet is

- A read-mostly observer: it shows what local Cursor agent sessions did, per
  agent and per worktree, from passive hook events and read-only git state.
- A kit generator: roster, subagent files, `.mdc` rules and skills rendered from
  `.cursorfleet/roster.toml` (M1).
- A convention for agent-declared work artifacts (plans, handoffs, blockers)
  under `.cursorfleet/work/<task>/` ([ADR 0006](adr/0006-agent-declared-events.md)).
- Local only: no network calls, no telemetry, no accounts.

## What CursorFleet is not

- Not a security boundary, sandbox or policy enforcer in v0.1
  ([threat model](threat-model.md)). A prompt-injected or malicious agent can
  bypass, disable or forge anything CursorFleet shows.
- Not an agent runner: it does not spawn, schedule or steer agents.
- Not a cost or token tracker.
- Not multi-IDE. Cursor is the only officially supported IDE; internals are
  adapter-ready (`cursorfleet.adapters.*`, normalized events) but no second
  adapter ships in v0.1.

## v0.1 scope: Observe

- Passive hooks only (the 12 in `ALLOWED_V01_HOOKS`); the four content-bearing
  hooks are never registered ([ADR 0004](adr/0004-no-chain-of-thought-and-hook-policy.md)).
- Stdlib-only hook hot path that always fails open, appends to per-session JSONL
  spools; a single-writer indexer builds a rebuildable SQLite projection
  ([architecture](architecture.md), [ADR 0002](adr/0002-storage-layout-and-runtime-directory.md)).
- Sanitized, versioned event model ([ADR 0003](adr/0003-event-model-and-sanitization.md)).
- CLI (`init --cursor`, `doctor`, `validate`, `status --json`, `events purge`)
  and Textual TUI: overview, agent detail, timeline, worktrees, display-only gates.
- Git/worktree collector: read-only, argv lists, timeouts, no fetch.
- Local sessions only.

## Explicit non-goals for v0.1

- No enforcement: no allow/deny/ask decisions, no path or command blocking.
- No forced approvals and no custom approval channel.
- No cloud-agent or cloud-subagent visibility; their hooks run in a VM and never
  reach the local spool.
- No token or cost budgets. Cursor hooks expose context usage only in
  `preCompact`; the TUI shows elapsed time, tool-call counts and compactions and
  says token use is unknown.
- No capture of prompts, thinking, responses, file contents or command output.
- No headless `stream-json` ingestion, no MCP server, no second IDE adapter.
- No real "done" gate: `stop` cannot block completion, so gate tiles are
  display-only signals bound to a commit and marked stale when HEAD moves.

## What Cursor cannot do (so CursorFleet cannot promise it)

Verified from docs (ADR 0001, section A):

- No per-subagent tool allowlist, path scope, network or git permission.
  Subagent frontmatter is only `name`, `description`, `model`, `readonly`,
  `is_background`. The roster's capability notes are documentation only.
- Worktree isolation is requested in the prompt, not configured; CursorFleet can
  detect it, not enforce it. Cursor creates and deletes worktrees itself.
- `ask` is not enforced for `preToolUse` and is treated as `deny` for
  `subagentStart`.
- `stop` and `subagentStop` can only send a bounded follow-up message.
- No hook reports which rules, skills or AGENTS.md files were loaded;
  `context.loaded` is therefore self-reported only.
- A subagent can launch child subagents one level deep. Having the Coordinator
  be the main agent is a **design choice**, not a platform limit.

Unverified and shown as such until captured: agent identity inside subagent tool
hooks, custom `subagent_type` naming, hook behavior in the CLI and Agents Window
worktrees (**PROVISIONAL**).

## Acceptance criteria for v0.1

From the reviewed plan, section 6. Each has a verification method.

- **Install and uninstall:** installs on a clean repo with a visible diff;
  one `uninstall` restores prior state. Verified by integration tests on
  fixture repos.
- **No sensitive data:** zero raw prompts, thinking, file contents, env, emails
  or transcript paths in the spool. Verified by property tests plus a synthetic
  secret corpus (security tests).
- **Parallel worktrees:** parallel subagents in separate worktrees all appear in
  one TUI. Verified with a fixture repo and, once captured, real fixtures
  (**PROVISIONAL**).
- **Corruption tolerance:** killing a hook mid-write or truncating a JSONL file
  never crashes the TUI, and `replay` rebuilds identical state.
- **Latency and fail-open:** hook p95 under 60 ms warm on Linux, macOS and
  Windows (Linux cold start measured at 27.7 ms p95; others open); hooks fail
  open on any internal error.
- **Honest docs:** README and docs state no enforcement, no forced approvals, no
  cloud-agent visibility.

## Roadmap

- **v0.1 Observe** (this contract).
- **v0.2 Guard:** policy engine with allow/warn/ask/deny where Cursor supports
  it; path-scoped write denial; tamper protection for hooks and policy;
  `failClosed` shim; headless `ingest`; optional MCP server for typed event
  emission. `schemas/policy.schema.json` is reserved for it.
- **v0.3 Prove:** evidence contracts bound to commit SHA; review, patch,
  re-review state machine; QA in a fresh worktree; external gate command and CI
  status; read-only GitHub issue/PR context.
