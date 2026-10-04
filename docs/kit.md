# Cursor kit (M1): `init`, `uninstall`, `doctor`, `validate`

Statuses: **PROVISIONAL** marks behavior that depends on Cursor facts not yet
captured live ([ADR 0001](adr/0001-cursor-capabilities.md), section B).
The kit is implemented, provisional and unvalidated against live Cursor; where it differs
from an accepted ADR the difference is marked **Divergence** and listed in
[follow-ups](follow-ups.md). Install ownership rules: [ADR 0009](adr/0009-install-uninstall-ownership.md).

The kit is generated from `.cursorfleet/roster.toml` (default roster if absent)
and `.cursorfleet/config.toml`. Output is deterministic: no timestamps, versions
or machine paths are rendered.

## What `cursorfleet init --cursor` writes

| Path | Owner | Notes |
| --- | --- | --- |
| `.cursor/agents/<prefix><id>.md` | CursorFleet | One per enabled roster agent. Frontmatter is limited to `name`, `description`, `model`, `readonly`, `is_background`. The coordinator is never a subagent file. |
| `.cursor/skills/cursorfleet-coordinator/SKILL.md` | CursorFleet | The coordinator playbook (main agent). `delivery = "rule"` or `"both"` also writes `.cursor/rules/cursorfleet-coordinator.mdc`. |
| `.cursor/skills/cursorfleet-artifacts/SKILL.md` | CursorFleet | How to write plan, handoff, blocker and context artifacts (ADR 0006). |
| `.cursor/rules/cursorfleet-core.mdc` | CursorFleet | `alwaysApply`, about ten lines. |
| `.cursor/rules/cursorfleet-handoff.mdc` | CursorFleet | Applies to `.cursorfleet/work/**`; the artifact format and context manifest. |
| `AGENTS.md` and `<work dir>/AGENTS.md` | You | A delimited managed block is appended (never overwrites). The nested one tells agents that artifacts are untrusted data. |
| `.cursor/hooks.json` | You | CursorFleet's entries are merged in; yours are preserved. |
| `.cursorfleet/config.toml`, `roster.toml` | You | Written only if absent; yours afterwards (kept by `uninstall` if edited). |
| `.cursorfleet/install.lock.json` | CursorFleet | Paths, sha256, managed blocks, hook entries, created directories. No timestamps. |

Templates live in `templates/cursor/` and ship in the wheel as
`cursorfleet/_templates/cursor` (hatch `force-include`); a source checkout reads
`templates/cursor` directly.

## Hooks written

Exactly the enabled subset of `ALLOWED_V01_HOOKS` (default: all 12), each as
(**Divergence:** [ADR 0007](adr/0007-narrower-v01-hook-policy.md) decides nine hooks:
`sessionStart`, `sessionEnd`, `preToolUse`, `postToolUse`, `postToolUseFailure`,
`subagentStart`, `subagentStop`, `preCompact`, `stop`. The shell and file-edit hooks are to
be dropped after the spike, and re-running `init` will need a migration that removes the
old entries.)

```json
{ "command": "cursorfleet-hook", "timeout": 5 }
```

- No arguments: the hook name comes from `hook_event_name` on stdin.
- No `failClosed`: a missing binary or crash fails open.
- **No `matcher`.** Matchers target tool types, subagent types or command text
  (ADR 0001 A3); the values for custom `cf-*` subagents and for MCP tools are
  unverified (**PROVISIONAL**), and a wrong matcher would silently drop events.
  Revisit after a live capture.
- The installer asserts every event against `ALLOWED_V01_HOOKS` and
  `FORBIDDEN_HOOKS` before building any entry; a forbidden name raises and
  nothing is written. The config model cannot represent one either.
- `.cursor/hooks.json` is the only executable surface CursorFleet touches, and
  its diff is always printed, also with `--yes`.

## Install and uninstall guarantees

- `--dry-run` prints the exact unified diff of every file and writes nothing.
- Without `--yes`, a prompt (default no) is required; no TTY and no input means abort.
- Dirty conflicts (an unmanaged file at a managed path, a modified managed file
  or block, invalid JSON in `hooks.json`, a symlinked target) abort before any write.
- Writes are atomic per file; the lockfile is written last.
- A second `init` is a no-op.
- `uninstall` removes only what the lockfile lists, only while hashes still
  match. Drifted items are reported, skipped and stay in the lockfile
  (`--force` removes them). Edited `config.toml`/`roster.toml` are kept.
- `init` followed by `uninstall` restores the tree byte for byte, including a
  pre-existing `hooks.json` and `AGENTS.md`. `hooks.json` formatting (indent,
  separators, line endings) is detected and reproduced; when it cannot be
  reproduced exactly, the original text is kept in the lockfile (`original_b64`)
  and used if the file is unchanged since install. That field contains the
  project's own pre-existing `hooks.json`, which is normally committed already.
- The lockfile is untrusted repository data: paths must match an allowlist
  (`.cursor/agents|rules|skills/`, `.cursorfleet/`, `AGENTS.md`), so a hostile
  lock cannot make `uninstall` delete other files.

## `doctor`

Read-only. Checks Python (>= 3.11), `cursorfleet-hook` on PATH, git and the
runtime dir (`git rev-parse --git-common-dir`, then `cursorfleet/`, ADR 0002),
runtime permissions (0700/0600, POSIX), config validity, lockfile drift, and
lists hooks at enterprise, team (not visible from disk), project and user level.
Content-bearing hooks registered by anyone are a warning. The Cursor version is
taken from `CURSOR_VERSION` or `cursor --version` (argv, 5 s timeout, skip with
`--no-probe-cursor`) and is never invented; versions not listed in
`[cursor].validated_versions` give a warning (**PROVISIONAL**). Exit 0 when no
check is `fail`, 1 otherwise. `--json` schema: `cursorfleet.doctor/1`.

Enterprise paths (PROVISIONAL, docs only): Linux `/etc/cursor/hooks.json`, macOS
`/Library/Application Support/Cursor/hooks.json`, Windows
`%PROGRAMDATA%\Cursor\hooks.json`.

## `validate`

Config and roster against the models; roster consistency; generated files and
managed blocks against the templates (drift); subagent frontmatter keys; rule
extension (`.mdc`), frontmatter and length (< 500 lines); skill frontmatter; and
every artifact under the work dir. Findings in CursorFleet's own files are
errors; findings in your own rules are warnings. Exit 1 on any error. `--json`
schema: `cursorfleet.validate/1`.

### Artifact frontmatter (PROVISIONAL, see ADR 0006)

**Decided ([ADR 0006](adr/0006-agent-declared-events.md)):** TOML frontmatter between `+++`
fences, parsed with `tomllib`, schema `cursorfleet.artifact/0.1`. Fields: `schema`, `kind`,
`task`, `artifact_id`, `revision`, optional `digest` (`blake2s:<64 hex>`, computed by the
indexer, never trusted from the file), `author_role`, `created`, and for handoffs `to_role`,
`issue_ref`, `context_refs`. If a `digest` is present and does not match what the indexer
computes, that is a `digest_mismatch` problem. Every artifact event is self-reported and ineligible as gate
evidence ([ADR 0011](adr/0011-evidence-trust-model.md)). YAML stays for Cursor's own agent,
rule and skill files.

**Divergence (current code, to change after the spike):** the parser
(`cursorfleet.workflow.frontmatter`) reads a YAML subset between `---` fences with
`schema: cursorfleet.artifact/1`, and has no `artifact_id`, `revision` or `digest`. The
generated rule, skills and `AGENTS.md` templates teach that YAML form, and `emit` is not
implemented. Treat the YAML description below as the interim format.

Interim layout (both formats): files at `<work dir>/<task>/<NN>-<kind>-<author_role>.md`,
`task` equal to the directory, `created` as ISO 8601, `kind` one of the four artifact kinds,
at most 50 `context_refs` (workspace-relative), 64 KiB per file. Read-only agents
(architect, scout, reviewer) cannot write files; they return the artifact text and the
coordinator saves it.
