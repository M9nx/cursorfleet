# Changelog

All notable changes to CursorFleet are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project intends to follow
[Semantic Versioning](https://semver.org/) once a first release exists.

CursorFleet is an unofficial tool: it is not affiliated with or endorsed by Anysphere or Cursor.

## [Unreleased]

Nothing has been released. The version in `pyproject.toml` is `0.0.1.dev0`. Everything below is
pre-alpha and **has not been verified against a live Cursor session** (the questions in
[ADR 0001](docs/adr/0001-cursor-capabilities.md) are open). v0.1 is *Observe* only: no
enforcement, no forced approvals, no cloud-agent visibility.

### Process

- **M0a freeze (2026-10-04).** New M2 and TUI implementation is frozen until the live Cursor
  spike ([spike/README.md](spike/README.md)) has been run and the ADR 0001 questions are
  answered. The existing M1, M2 and TUI code is *implemented, provisional, unvalidated
  against live Cursor*. See [docs/status.md](docs/status.md).

### Documentation

- ADR process and template accepted as ADR 0000, with required fields on every ADR
  (supersession, related ADRs, implementation status, review trigger, release gate) and an
  indexed list of release gates in [docs/adr/README.md](docs/adr/README.md).
- New ADRs: 0007 narrower v0.1 hook policy (supersedes 0004; nine hooks), 0008 enforcement
  boundaries, 0009 install and uninstall ownership, 0010 reducer state semantics, 0011
  evidence trust model, 0012 roster and worktree ownership.
- Decisions recorded that the code does **not** yet follow (tracked in
  [docs/follow-ups.md](docs/follow-ups.md), to be done after the spike): nine registered
  hooks, event schema version `0.1`, `verification.observed` instead of `test.completed`,
  command display off by default, BLAKE2s segment fingerprints, HMAC worktree ids, a
  maintenance lock, TOML artifact frontmatter, no gate derived from heuristic events, and
  `init`/`uninstall` repository-root preconditions (exit 2; no `--allow-non-git`).
- ADR 0001 stays provisional and now carries an empirical test matrix; the local Cursor IDE
  (desktop) is the only supported v0.1 surface, and the CLI, Agents Window and worktrees are
  not claimed. See [docs/empirical-test-plan.md](docs/empirical-test-plan.md).
- ADR 0005: `CursorFleet` is a working name; the public name, registry availability and a
  trademark review are release gates. `fleet-for-cursor` is withdrawn as a fallback because
  it still contains the Cursor mark.
- Docs-site plan only ([docs/docs-site-plan.md](docs/docs-site-plan.md)); no site, workflow or
  dependency was added.

### Added

- **M0 foundations:** project scaffold, ADRs 0001 to 0006, product contract, threat model,
  privacy statement, JSON Schemas for events, config, roster and policy (reserved), a throwaway
  capture kit under `spike/` and a Linux hook-latency benchmark (27.7 ms steady-state p95).
- **M1 kit:** `cursorfleet init --cursor`, `uninstall`, `doctor` and `validate`. Deterministic
  generation of subagent files, rules, skills, `AGENTS.md` blocks and a merged
  `.cursor/hooks.json` of twelve passive hooks (ADR 0007 later narrowed this to nine; code not yet changed), with a visible diff, confirmation, an install
  lockfile and byte-for-byte uninstall.
- **M2 observer:** a stdlib-only, fail-open hook entry point (`cursorfleet-hook`) with an
  allowlist parser, command and path sanitizer, per-writer append-only JSONL spool with CRC and
  size caps, a single-writer SQLite projection with quarantine and rebuild, deterministic
  reducer and `replay`, a read-only git/worktree collector, retention and `events export` /
  `events purge`, and `status --json` (`cursorfleet.status/1`).
- **M3 dashboard:** the Textual TUI (`cursorfleet tui`) with overview, agent detail, timeline,
  worktrees, gates (display-only), evidence and tiles views, filtering, pinning, and a degraded
  mode for missing telemetry.
- **M4 release preparation:**
  - security and privacy review ([docs/security-review-v0.1.md](docs/security-review-v0.1.md))
    with regression tests, including a no-network test;
  - cross-platform CI (Linux, macOS, Windows; Python 3.11 to 3.14) with lint, format, types,
    coverage, and a wheel build-and-smoke-test job; inactive release workflow
    (`.github/workflows/release.yml`) using PyPI Trusted Publishing and a draft GitHub release;
  - `docs/quickstart.md`, `governance.md`, `demo.md`, `platform-support.md`,
    `release-checklist.md` and a reproducible synthetic demo (`scripts/demo.sh`).

### Security

- Bounded redaction window removes a regular-expression denial of service in the hook's command
  and text redaction (SR-01).
- The runtime directory is refused when it is a symlink, a reparse point, owned by another user
  or group/other-writable (SR-02).
- Tools (`git`, `cursor`) are resolved from absolute `PATH` entries only, never the current
  directory (SR-03); NTFS junctions count as links (SR-04); the workspace resolver uses the same
  hostile-repository git hardening as the collector (SR-05); paths inside `.git` are rejected in
  config and lockfile (SR-06).
- Lower-severity hardening: planted-database recovery, no local variables in tracebacks,
  escaped terminal control characters in error and doctor output, `O_NOFOLLOW` artifact reads,
  non-blocking spool open, drive-letter refs refused, attached `mysql -p` passwords redacted.

### Known limitations

- Not published; not on PyPI or TestPyPI. No tags or GitHub releases exist.
- The TUI derives PASS/FAIL gate tiles from heuristic command classification. This is
  non-authoritative and contradicts ADR 0003 rule R1; fix pending after the spike.
- The code registers twelve hooks; ADR 0007 decides nine.
- Hook payload shapes come from documentation, not captures. Agent attribution on tool events,
  custom subagent names, CLI and Agents Window behaviour, and macOS/Windows hook latency are
  unverified (see [docs/platform-support.md](docs/platform-support.md)).
- Windows ACLs are not set on the runtime directory.
- GitHub Actions are pinned by major version, not by commit SHA.
- `cursorfleet emit` (ADR 0006 fallback) is not implemented.
