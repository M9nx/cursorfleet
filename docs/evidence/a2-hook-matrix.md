# A2 hook surface comparison (9 vs 12)

See [a2-contract-decision-matrix.md](a2-contract-decision-matrix.md) for the decision (**keep 12**).

| Hook | In 9-set | In 12-set | Information gained (live + design) | Duplication | Privacy |
| --- | --- | --- | --- | --- | --- |
| sessionStart/End | yes | yes | Session lifecycle | — | OK |
| pre/post ToolUse | yes | yes | Tool telemetry | — | OK |
| subagentStart/Stop | yes | yes | Subagent lifecycle | — | OK |
| preCompact/stop | yes | yes | Compaction, stop status | — | OK |
| beforeShellExecution | no | yes | Permission reply; shell path | overlaps preToolUse for Shell | no output stored |
| afterShellExecution | no | yes | Exit code refinement | postToolUse also fires | output discarded |
| afterFileEdit | no | yes | file.changed without content | postToolUse for Write | edits discarded |

**TUI usefulness:** file.changed and shell exit codes materially improve lanes and verification observations on maintainer smoke.

**Failure behavior:** all hooks fail-open ([ADR 0004](../adr/0004-no-chain-of-thought-and-hook-policy.md)).
