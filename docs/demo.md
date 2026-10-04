# Demo (synthetic, no Cursor)

> **This demo is synthetic.** No Cursor is started or contacted. The "agent sessions" are
> hand-built payloads derived from Cursor's hooks documentation (`spike/doc_examples/`), fed to
> the real `cursorfleet-hook` executable. They show what CursorFleet does with such payloads, and
> prove **nothing** about how real Cursor behaves (ADR 0001 questions are still open).

## Run it

```bash
scripts/demo.sh                    # uses uv if available, else python3
python scripts/demo.py             # also works on Windows (py scripts/demo.py)
python scripts/demo.py --keep      # keep the temporary directory to explore it
python scripts/demo.py --no-uninstall   # also keep the installed kit, to open the TUI
python scripts/demo.py --venv /path/to/venv   # use an installed wheel instead of the checkout
```

It needs git, and either CursorFleet on `PATH`, `--venv`, or `uv` (it then runs the checkout via
`uv run --project`). Everything happens in a temporary directory that is deleted at the end
unless you pass `--keep`.

## What it does

1. Creates a git repository and a linked worktree (`feat/qa`).
2. `cursorfleet init --cursor --dry-run`, then `--yes` (the diff is printed and abbreviated).
3. Replays two synthetic sessions through `cursorfleet-hook`: `demo-main` (shell command, file
   edit, a subagent start/stop, a compaction, stop) in the main checkout, and `demo-qa` in the
   worktree, ending with `sessionEnd`. The shell command carries a planted bearer token; the
   command output and the edit carry planted marker strings.
4. **Privacy check:** greps the spool for the planted strings and fails if any is present. The
   token is redacted in the stored command display, and output and edit contents are never read.
5. `cursorfleet doctor --no-probe-cursor`, `status`, `status --json`, `replay demo-main`
   (rebuilds twice and compares digests) and `events export --sanitized`.
6. `cursorfleet uninstall --yes` and a check that `git status` is identical to before `init`.

## What you should see

Abbreviated output from a real run on Linux (timestamps and temp paths vary):

```text
=== 5. privacy check: planted secrets must not be in the spool
    bearer token: 0 occurrence(s) in 10903 bytes of spool
    command output: 0 occurrence(s) in 10903 bytes of spool
    edited file content: 0 occurrence(s) in 10903 bytes of spool

=== 7. cursorfleet status
    telemetry: hooks | sessions 2 | events 21 | token budget: unknown
    SESSIONS
      demo-main  lane=awaiting_review  tools=1  compactions=1  elapsed=0s  events=11
        - generalPurpose#demo-main-sub  lane=done (observed_activity)  attribution=exact  tools=0
        - main  lane=awaiting_review (observed_activity)  attribution=unknown  tools=1
      demo-qa  lane=done  tools=1  compactions=1  elapsed=0s  events=10
    WORKTREES
      .../repo     [main]    dirty=3  lane=awaiting_review  telemetry=hooks
      .../repo-qa  [feat/qa] dirty=0  lane=done             telemetry=hooks

=== 9. cursorfleet replay demo-main ...
    digest d7e2...  deterministic=true

=== 11. cursorfleet uninstall --yes ...
    working tree identical to before init: True
```

Note `attribution=unknown` on tool events and `exact` only for the subagent that the synthetic
`subagentStart` named: that is the honest state of agent attribution until Q1 is answered.

## See the dashboard

The demo does not launch the interactive TUI. To look at the same data yourself:

```bash
python scripts/demo.py --no-uninstall    # keeps the directory and skips the final uninstall
cd <the printed repo directory>
cursorfleet tui
```

## Optional: record it (not required, not run in CI)

- **asciinema:** `asciinema rec demo.cast -c "python scripts/demo.py"`, then `asciinema play demo.cast`.
- **VHS** (https://github.com/charmbracelet/vhs): a tape such as
  ```text
  Output demo.gif
  Set Width 1200
  Type "python scripts/demo.py" Enter
  Sleep 15s
  ```
  and `vhs demo.tape`. Keep "SYNTHETIC" visible in any recording you publish.
