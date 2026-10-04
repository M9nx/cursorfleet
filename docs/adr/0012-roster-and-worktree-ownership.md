# ADR 0012: Roster and worktree ownership

- Status: provisional (the roster model is decided; worktree behaviour depends on the spike)
- Date: 2026-10-04
- Deciders: project owner (M9nx), architecture-owner decision
- Evidence level: verified-from-docs (ADR 0001 A7, A8) for subagent frontmatter and worktree facts; assumption for how Cursor places and cleans worktrees
- Supersedes: none
- Superseded by: none
- Related ADRs: 0001 (A7, A8, Q3, Q4), 0002 (worktree id, runtime dir shared by worktrees), 0003 (attribution), 0008 (no enforcement), 0009 (generated roster files)
- Implementation status: Implemented-provisional. The default roster (`config/roster.py`), the coordinator skill, the "one owner per file" and "ask for an isolated worktree" text, and the read-only worktree collector exist. Owner mapping in `status_doc.py` is derived from events that carry a `worktree_id`. Divergent-from-code on one point: `worktree_id` is an unkeyed hash (ADR 0002). CursorFleet creates, moves and deletes no worktree.
- Review trigger: spike rows for Cursor-managed worktrees, manual worktrees, parallel subagents and `subagentStart.git_branch` / `is_parallel_worker`; a change to Cursor's worktree cap or cleanup
- Release gate: the TUI and docs show a worktree owner only with its attribution label; no text implies CursorFleet isolates or cleans up worktrees; the cleanup-cap risk is stated in the quickstart; worktree behaviour claims match the spike matrix (ADR 0001)

## Context

Verified from the Cursor docs (ADR 0001, fetched 2026-10-04):

- Subagents share the parent's checkout by default and can overwrite each other's changes.
  Isolation is obtained by **asking for it in the prompt**; there is no frontmatter field (A8).
- Cursor creates, discovers and deletes worktrees itself. Default cap
  `cursor.worktreeMaxCount` is 25 per machine across workspaces, with
  `cursor.worktreeCleanupIntervalHours`; worktrees made by `git worktree add` or the
  worktree skills are also eligible for deletion (A8).
- Subagent frontmatter has `name`, `description`, `model`, `readonly`, `is_background`;
  nothing scopes tools or paths (A7).
- The docs do not say where Cursor places worktrees or what hook payloads contain inside
  them (A8, Q4).

## Decision

### The coordinator is the main agent

- The coordinator is the main (parent) agent, driven by the generated skill and optionally
  a rule. It is never rendered as a subagent file. This is a **design choice**, not a
  platform limit (ADR 0001 A7 caveat): it avoids the subagent nesting depth and the
  unproven identity of hooks inside subagents.

### One owner per file-changing lane

- At any time, one roster agent is the owner of a lane that changes files. Two writers
  never share files; if two need the same file, the coordinator serializes them.
- The default roster has one implementer enabled. Read-only roles (`architect`,
  `repo-scout`, `reviewer`) cannot write files and return artifact text for the coordinator
  to save. `readonly` is Cursor's only switch and is coarse; the roster's capability notes
  are documentation, not permissions.
- `implementer-beta` is **disabled by default**. Enable it only for truly independent
  tasks and only with worktree isolation requested, because parallel work without isolation
  can overwrite `implementer-alpha`'s edits.

### Worktree isolation is requested, not configured

- The coordinator is told to ask for isolation in its prompt ("each in its own
  environment") when running parallel implementers. CursorFleet cannot configure it, cannot
  verify that Cursor honoured it, and can only **detect** it afterwards from git state and
  from `workspace_roots`/`git_branch` in events, if the spike shows those carry it.

### Who creates, owns and deletes worktrees

- **Cursor or the user create and delete worktrees. CursorFleet never does in v0.1.** Its
  git collector is read-only (`git worktree list`, status, rev-parse; argv lists; timeouts;
  no fetch, no `worktree add/remove/prune`, no checkout).
- CursorFleet treats every worktree as external and ephemeral. Records that mention a
  deleted worktree stay until retention; the TUI shows it as missing or prunable and never
  assumes persistence.
- `worktree_id` is a keyed identifier of the realpath (ADR 0002 amendment), so it is stable
  per repository and does not leak the path.

### Lane/owner mapping

- A worktree's owner is **derived**, not declared: an agent entry whose events carry that
  `worktree_id`. The mapping is shown with the owner's `attribution` label (ADR 0003) and
  is only as good as Q1 and Q4. A worktree with no events is `unknown / no telemetry`, not
  "unowned".
- Artifacts may name a `to_role` or `author_role`; these are self-reported and never decide
  ownership (ADR 0011).

### Cursor worktree cleanup cap (25) risk

- Cursor may delete worktrees, including ones still holding unmerged work, once the machine
  has more than the cap. CursorFleet cannot prevent this and does not protect worktrees.
- The docs must say so: commit and push work you care about; do not rely on a worktree
  being there tomorrow. `doctor` should surface the configured cap if it can read it
  (not implemented).

## Consequences

- Positive: v0.1 never mutates a worktree; ownership claims are labelled; parallel
  implementers are opt-in.
- Negative / costs: the tool cannot enforce or even guarantee isolation, so a user who
  ignores the guidance gets the overwrite hazard the docs describe; owner mapping may be
  unknown for many worktrees until Q1 and Q4 are answered.
- Follow-ups: spike rows for managed and manual worktrees and for parallel subagents;
  quickstart text on the 25-worktree cap.

## Open questions

- Do hooks inside a Cursor-managed worktree report `workspace_roots` as the worktree path
  and resolve the same common dir (Q4)?
- Does `subagentStart.git_branch` change and `is_parallel_worker` become true under
  isolation?
- Does the 25-worktree cap apply to manually created worktrees opened in Cursor?

## Alternatives considered

- Have CursorFleet create worktrees for parallel agents: rejected for v0.1, it is a mutating
  operation, Cursor already manages worktrees, and cleanup interactions are unverified.
- Make the coordinator a subagent: not adopted, revisit after Q1.
- Enforce one-writer-per-file with path-scoped denies: Guard work (ADR 0008).
