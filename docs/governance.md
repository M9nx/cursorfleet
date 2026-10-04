# Governance model: roster, artifacts, handoffs

This page explains how CursorFleet organises an agent team and, more importantly, **what it
can and cannot vouch for** in v0.1. v0.1 is *Observe*: it shows what happened and what agents
claim; it does not allow, deny or approve anything.

Status: implemented, provisional, unvalidated against live Cursor; new work is frozen until
the live spike runs ([status](status.md)). Decisions behind this page:
[ADR 0008](adr/0008-enforcement-boundaries.md) (enforcement),
[ADR 0011](adr/0011-evidence-trust-model.md) (evidence), and
[ADR 0012](adr/0012-roster-and-worktree-ownership.md) (roster and worktrees).

## Honest limits of v0.1

- **No enforcement.** Nothing is blocked, scoped or approved. Cursor has no per-subagent tool
  allowlist, path scope or network permission; subagent frontmatter is only `name`,
  `description`, `model`, `readonly` and `is_background`. The roster's "capabilities" are
  documentation for humans and prompts for agents, not permissions.
- **No forced approvals.** The `ask` decision is not enforced for `preToolUse` and `stop` cannot
  block completion, so gate tiles are heuristic, non-authoritative displays.
- **No cloud-agent visibility.** Cloud agents run hooks in a VM; their events never reach the
  local spool. Only local sessions are seen.
- **Not a security boundary.** A prompt-injected or malicious agent can ignore the conventions,
  forge artifacts, or edit files CursorFleet watches ([threat model](threat-model.md)).
- **Unverified against live Cursor.** Whether tool hooks identify which subagent made a call,
  how custom subagent names appear, and whether hooks fire in the CLI and Agents Window are
  open questions (ADR 0001 Q1 to Q4). Attribution is `exact`, `inferred` or `unknown`
  ([ADR 0003](adr/0003-event-model-and-sanitization.md); a role-only identity is `inferred`,
  never `exact`) and is **PROVISIONAL**.
- **Local Cursor IDE only.** The CLI, Agents Window, worktrees, parallel subagents and `ask`
  are not claimed until tested ([ADR 0001](adr/0001-cursor-capabilities.md)).

## Roster

`.cursorfleet/roster.toml` (committed; a default roster is used if the file is absent) lists
the roles for your team. `cursorfleet init --cursor` renders one Markdown file per enabled agent
under `.cursor/agents/` with the `cf-` prefix, and the **Coordinator is the main agent** (a
design choice, not a platform limit), driven by the generated skill `cursorfleet-coordinator`
(and optionally a rule), not a subagent. The default roster has an architect, an
implementer, a patch engineer, a QA/release agent, a repository scout, a test engineer and a
reviewer. A second implementer (`implementer-beta`) exists but is **disabled by default**:
there is one owner per file-changing lane, and parallel implementers need isolation that you
or Cursor must provide ([ADR 0012](adr/0012-roster-and-worktree-ownership.md)). Edit the roster, run `cursorfleet validate`, then `init` again
(a no-op if nothing changed); `uninstall` removes only what it installed.

Generated files are deterministic: no timestamps, versions or machine paths, so they diff
cleanly and `validate` can detect drift.

## Work artifacts and handoffs

Agents are asked, through the generated rules and skills, to leave short Markdown files with a
strict frontmatter under `.cursorfleet/work/<task>/` (the decided format is TOML with
`artifact_id`, `revision` and a digest, [ADR 0006](adr/0006-agent-declared-events.md); the
code and templates still use a YAML subset, see [kit.md](kit.md)):

```
.cursorfleet/work/add-login-form/01-plan-architect.md
.cursorfleet/work/add-login-form/02-handoff-implementer-alpha.md
```

Four kinds exist: `plan.created`, `handoff.created`, `blocker.raised` and `context.loaded`
([ADR 0006](adr/0006-agent-declared-events.md), format in [kit.md](kit.md)). A handoff names the
author role, the receiving role, the task, and workspace-relative `context_refs`; the body is
free Markdown that CursorFleet never copies into events. Read-only agents (architect, scout,
reviewer) cannot write files, so they return the artifact text and the coordinator saves it.

The indexer scans the work directory read-only (symlinks skipped, size and file-count caps),
validates each artifact, and turns it into a `self_reported` event. `cursorfleet validate` runs
the same checks, and editing a file by hand is the supported way to correct one. ADR 0006 also
describes a `cursorfleet emit` fallback; it is **not implemented in v0.1**.

## Observed versus self-reported

| | Observed | Self-reported |
| --- | --- | --- |
| Source | Passive Cursor hooks and read-only git | Artifact files written by agents |
| Examples | tool calls, shell commands (sanitized), file edits (paths only), subagent start/stop, compactions, worktree and dirty state | plans, handoffs, blockers, "context loaded" |
| Trust | As good as Cursor's hook payloads (unverified) and the local user account | Anything an agent says about itself, including `author_role`, can be wrong or forged |
| In the UI | normal | labelled SELF-REPORTED |
| Counts as evidence for a gate | **no, not in v0.1**: a hook observation is the weakest tier; only a deterministic runner bound to a commit (v0.3) can satisfy a gate | never |

The event model enforces the split: it rejects a self-reported tool, file or subagent event, and
an observed plan, handoff, blocker or context event.

## Gates

Gate tiles (tests, lint, review, and so on) are **heuristic and non-authoritative**. Nothing
in v0.1 satisfies a gate: observed hook events and agent-declared artifacts are both below
the evidence tier a gate needs ([ADR 0011](adr/0011-evidence-trust-model.md)), and heuristic
events never satisfy a gate. They do not stop anyone from merging.

**Divergence:** the current TUI derives PASS and FAIL tiles from a classifier over redacted
shell command text. The decided behaviour is to show `verification.observed` events as
observations with a method and confidence, not as gates ([tui.md](tui.md)).

## What a human should still do

Review diffs and run the checks yourself. Use CursorFleet to find out which worktree or agent
produced a change and what it claimed, not to decide that it is safe. The v0.2 "Guard" and v0.3
"Prove" milestones in the [product contract](product-contract.md) are where enforcement and
commit-bound evidence belong; neither exists yet.
