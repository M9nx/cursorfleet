# Governance model: roster, artifacts, handoffs

This page explains how CursorFleet organises an agent team and, more importantly, **what it
can and cannot vouch for** in v0.1. v0.1 is *Observe*: it shows what happened and what agents
claim; it does not allow, deny or approve anything.

## Honest limits of v0.1

- **No enforcement.** Nothing is blocked, scoped or approved. Cursor has no per-subagent tool
  allowlist, path scope or network permission; subagent frontmatter is only `name`,
  `description`, `model`, `readonly` and `is_background`. The roster's "capabilities" are
  documentation for humans and prompts for agents, not permissions.
- **No forced approvals.** The `ask` decision is not enforced for `preToolUse` and `stop` cannot
  block completion, so gates are display-only signals.
- **No cloud-agent visibility.** Cloud agents run hooks in a VM; their events never reach the
  local spool. Only local sessions are seen.
- **Not a security boundary.** A prompt-injected or malicious agent can ignore the conventions,
  forge artifacts, or edit files CursorFleet watches ([threat model](threat-model.md)).
- **Unverified against live Cursor.** Whether tool hooks identify which subagent made a call,
  how custom subagent names appear, and whether hooks fire in the CLI and Agents Window are
  open questions (ADR 0001 Q1 to Q4). Agent attribution is shown as `exact`, `inferred` or
  `unknown` and is **PROVISIONAL**.

## Roster

`.cursorfleet/roster.toml` (committed; a default roster is used if the file is absent) lists
the roles for your team. `cursorfleet init --cursor` renders one Markdown file per enabled agent
under `.cursor/agents/` with the `cf-` prefix, and the **Coordinator is the main agent**, driven
by the generated skill `cursorfleet-coordinator` (and optionally a rule), not a subagent. The
default roster has an architect, an implementer, a patch engineer, a QA/release agent, a
repository scout and a reviewer. Edit the roster, run `cursorfleet validate`, then `init` again
(a no-op if nothing changed); `uninstall` removes only what it installed.

Generated files are deterministic: no timestamps, versions or machine paths, so they diff
cleanly and `validate` can detect drift.

## Work artifacts and handoffs

Agents are asked, through the generated rules and skills, to leave short Markdown files with a
strict frontmatter under `.cursorfleet/work/<task>/`:

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
| Counts as evidence for a gate | yes, bound to a commit, stale when HEAD moves | never |

The event model enforces the split: it rejects a self-reported tool, file or subagent event, and
an observed plan, handoff, blocker or context event.

## Gates

Gate tiles (tests, lint, review, and so on) are inferred from sanitized shell commands that
look like checks and from observed outcomes, bound to the commit they ran on, and marked
stale when `HEAD` moves. They are a heuristic. They do not stop anyone from merging, and the
classification is a guess over redacted command text.

## What a human should still do

Review diffs and run the checks yourself. Use CursorFleet to find out which worktree or agent
produced a change and what it claimed, not to decide that it is safe. The v0.2 "Guard" and v0.3
"Prove" milestones in the [product contract](product-contract.md) are where enforcement and
commit-bound evidence belong; neither exists yet.
