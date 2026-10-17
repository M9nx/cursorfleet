# V012-02 run kit — owner live session (maintainer Linux Cursor IDE)

Status: **run sheet for the owner**, prepared 2026-10-17. It sequences one or more live
Cursor sessions on the maintainer machine that close (or partially close) the three
owner gates of the v0.1.2 baseline:

1. **B0** live scenarios 1, 2, 5 (plus an invited refresh of 3) →
   [`b0-live-validation-2026-10-12.md`](b0-live-validation-2026-10-12.md)
2. **SO-01** live permission-hook rows → [`so01-permission-hooks.md`](so01-permission-hooks.md)
3. **Latency 13B** paired batches (Linux IDE) → [`latency-13b-linux-ide.md`](latency-13b-linux-ide.md)

Nothing in here can be closed by synthetic fixtures or repository tests. Record PARTIAL
when a gate only partially closes; do not upgrade verdicts to make records tidy. A session
performs no tagging, no publishing and no README claim changes.

Read alongside: [`spike/README.md`](../../spike/README.md) and
[`empirical-test-plan.md`](../../empirical-test-plan.md) (rows 8–13 define the procedures
referenced here; row 11 case C1 and row 13B define the contracts).

## Ground rules (from the empirical test plan)

- Scratch repositories only: no secrets, one clean commit, synthetic canary text
  (`CF-PROBE-OK` style), no real paths/emails/tokens in anything captured or recorded.
- Raw captures, stream outputs and timing logs stay **outside this repository**; export
  summarized numbers into the evidence docs only.
- Keep an out-of-band terminal open. If hooks break the UI, edit `.cursor/hooks.json`
  from that terminal and reload.
- Record the exact Cursor version and surface (desktop IDE) for every gate; verdicts
  apply to that surface only.
- Throwaway analysis commands (jq/python one-liners) run out-of-band and are not
  committed, per the plan's ground rules; if one proves broadly useful, propose the
  committed follow-up separately.

## Session 0 — setup

```bash
# throwaway repos, clean tree
mkdir -p ~/cf-v012-scratch && cd ~/cf-v012-scratch
git init rb0 && cd rb0 && git commit --allow-empty -m "scratch" && cd ..
# install the version you will release from (editable checkout is fine for evidence):
uv tool install /path/to/cursorfleet@your-commit   # or pipx / uv sync checkout
cursorfleet --version                               # record this
```

Then in the scratch repo:

```bash
cd rb0
cursorfleet init --cursor --dry-run   # review the exact diff
cursorfleet init --cursor             # twelve observe-only hooks (ADR 0007 amendment)
cursorfleet doctor                    # hooks, runtime dir, spool all expected green
# canary text for probe reads:
printf 'CF-PROBE-OK scratch canary\n' > probe.txt && git add probe.txt && \
  git commit -m "scratch canary"
```

Record in the out-of-band notes: `cursorfleet --version`, Cursor version (About panel),
OS, and the date per gate.

## Session 1 — Gate B0: scenarios 1, 2, 5 (+ invite 3) in the IDE

Procedure shell: [`b0-live-validation-2026-10-12.md`](b0-live-validation-2026-10-12.md)
(fill its table during or right after the session). Attach UX per v0.1.1: attach a
**suggested** session from the Active run screen with **Enter**, or
`cursorfleet run attach <session>` from a terminal, or the env token.

- **Scenario 1 (multiple chats → one run).** `cursorfleet run start --task a --desc "B0 s1"`;
  open **two** separate Cursor chats in the scratch repo; trigger one harmless tool call
  in each (e.g. read `probe.txt`). Attach each chat to the run (≤3 actions each) via the
  Enter suggestion or `run attach`. *Check:* both sessions appear under the run in the
  TUI Active run screen and in `cursorfleet status --json` `runs[]`; attach took ≤3
  actions per chat. Record PASS/PARTIAL/FAIL + notes.
- **Scenario 2 (two simultaneous runs, no cross-attach).** Second scratch repo `rb0b`
  (or a second run in the same repo if the UI supports it): `run start --task b` there;
  confirm runs list disambiguates and a chat in repo A never lands under run B
  (`status --json` cross-check). *No cross-attach* is the pass criterion.
- **Scenario 5 (two chats start simultaneously; no silent merge).** From one run-open
  repo, open two new chats back to back **before** attaching either; then attach one to
  the explicit run and confirm the second did **not** merge silently (it stays
  unlinked/attachable, membership never implicit).
- **Scenario 3 refresh (linked worktree cwd; invited, row 3 is OPEN).** `git worktree add`
  a worktree of `rb0`, open it in Cursor, `run start` from the worktree, and confirm the
  active pointer follows the worktree cwd in `status --json` (`run_builder` scoped facts).
  If it does not behave, record row 3 as PARTIAL/FAIL — it is not part of the 1/2/5 gate.
- **Screenshot.** Crop to the Active run card only. Sanitize: no chat text, prompt
  content, usernames, or private paths visible. If it cannot be sanitized honestly,
  record a text excerpt of the non-sensitive fields instead and note why the image is
  absent — that is a truthful PARTIAL, not a failure. If present, save as
  `docs/evidence/active-run-screenshot.png` (owner commits it; the filename is referenced
  by [b0-live-validation-2026-10-12.md](b0-live-validation-2026-10-12.md)).

Then update the results rows in
[`b0-run-association-spike.md`](b0-run-association-spike.md) only as measured (scenarios
1, 2, 5 PASS is the v0.1.2 go/no-go threshold; scenario 3 updates row 3 if exercised).

## Session 2 — Gate SO-01: permission-hook rows, live

Minimum gate (case **C1** of empirical-test-plan row 11; N=3 per hook, product hooks as
installed by `init --cursor`, `failClosed` false everywhere — the product never writes
`failClosed`):

- **preToolUse (N=3).** In the IDE main agent, three separate prompts: "read probe.txt
  and tell me the canary string" (Read tool). *Check each time:* the action proceeded —
  the agent's transcript shows the Read result; nothing was blocked or asked. The
  product spool gains these events (`cursorfleet status --json` session count grows).
- **subagentStart (N=3).** Three separate prompts: "use the reviewer subagent to review
  probe.txt" (the shipped roster has `reviewer`; any shipped name works). *Check each
  time:* the subagent started and did the work; no approval prompt and no block
  appeared; `subagentStart` telemetry appears (TUI agent card or status session).
- Record the rows in [`so01-permission-hooks.md`](so01-permission-hooks.md): hook,
  Cursor version, date, result, notes ("3/3 proceeded; hook exit 0 by product reply").
- **Do not over-claim:** this confirms *acceptance of the allow reply* live. The full
  row-11 case matrix (C2–C9, failClosed true) stays OPEN for the spike; SO-01 in the
  truth table flips to **Met** only when both rows above are PASS.

## Session 3 — Gate latency 13B: paired batches on Linux IDE

Contract: [`ADR 0001 §D`](../adr/0001-cursor-capabilities.md) and empirical-test-plan row
13B. Target record: [`latency-13b-linux-ide.md`](latency-13b-linux-ide.md).

- **Three batches × 30 pairs (≥90 pairs), each batch in a fresh Cursor session**, Cursor
  version recorded per batch.
- **Pair = the same scripted action once hooks-on (C1), once hooks-off (C0), adjacent in
  time;** order alternates between pairs (ABBA): odd pair → C0 then C1, even pair → C1
  then C0. Drift is thus averaged down rather than assumed away.
- **C1** = the product hook set **as shipped** (the twelve observe hooks of the ADR 0007
  amendment 2026-10-12; the plan's "nine hooks" wording is superseded for the observe
  set). Achieve it with the current `init --cursor` state of the scratch repo.
- **C0** = hooks-off baseline. Use `cursorfleet uninstall` for C0 sides and re-run
  `init --cursor` for C1 sides **only if** Cursor picks the change up without a window
  reload; verify for each pair that C1 actually produced hook events (TUI/status spool
  grew or spike capture saw them) and C0 produced none. If a reload **is** required per
  condition toggle, the pairing degrades: record the methodology note and treat the
  verdict as PARTIAL-eligible only.
- **Per-call timing is not available on the IDE surface**, so this session uses the
  row-13B **specified fallback**: each single action is timed end-to-end by the operator
  (out-of-band), and the pair delta is
  `T(hooks-on side) − T(hooks-off side)`, milliseconds, **negative deltas kept**.
  *Action definition (same for the whole session):* one chat step: "read probe.txt and
  stop"; measure from prompt sent → transcript shows the read result. Keep the action
  identical across all pairs of a batch.
- Scripted headless `agent -p` with `--output-format stream-json` (row-13B preferred
  source) is an **optional extra surface** (CLI); it does not substitute for the IDE
  gate and any numbers from it are recorded as a separate methodology note.
- **Diagnostics (informational, not the verdict):** C0b A/A control (pairs where both
  sides are C0 — do at least one batch-worth if time allows) gives the noise floor; a C1
  pooled delta smaller than the A/A spread is reported as "not detectable at this N".
  C2 no-op hook and 13C blocking/parallel stubs stay row-13 diagnostics; record out of
  band, note their availability next to the verdict.

Log each pair out-of-band as a line `batch,pair,order,T_on_ms,T_off_ms` in
`pairs-13b.csv` outside the repo, then summarize:

```python
# throwaway; run out-of-band. deltas.txt holds T_on-T_off (ms), one number per line.
import math, sys
v = sorted(float(x) for x in open(sys.argv[1]).read().split())
nr = lambda a, q: a[max(0, math.ceil(q * len(a)) - 1)]   # nearest-rank
print("n", len(v), "median", nr(v, 0.5), "p95", nr(v, 0.95), "max", max(v))
```

Fill the batch table (medians/p95 per batch + pooled) and the overall verdict in
[`latency-13b-linux-ide.md`](latency-13b-linux-ide.md): PASS median ≤100 ms and p95
≤200 ms pooled (each batch individually not FAIL); PARTIAL median ≤150 ms and p95
≤300 ms (requires a dated ADR amendment and narrowed claims); otherwise FAIL. Do not
commit the raw pairs file or the raw timing dump.

## Close-out (repo side)

After the owner returns with filled values, repo-side updates happen in one commit:
the three evidence docs, any PARTIAL-driven claim narrowing, truth-table SO-01 flip only
when earned, and a dated status.md line. The v0.1.2 gate for the live evidence is
`PASS/PARTIAL recorded honestly` — **not** green paint. Tagging/publishing remains
separately authorized (V012-06).
