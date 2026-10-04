# Security Policy

CursorFleet is pre-alpha, unofficial software (not affiliated with or endorsed by Anysphere or
Cursor). It runs locally, makes no network calls (verified by a test), and in v0.1 (Observe)
does not enforce policy, so it is **not a security boundary**: see the
[threat model](docs/threat-model.md).

## Supported versions

Nothing has been released. Until a first release, only the `main` branch is supported. After
v0.1.0, security fixes will go to the latest minor release only.

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** through GitHub's "Report a vulnerability"
(Security tab of [M9nx/cursorfleet](https://github.com/M9nx/cursorfleet/security/advisories/new)).
Do not open a public issue or pull request for a security problem.

Include: affected version or commit, operating system, a minimal reproduction (a synthetic
payload or repository is ideal), and the impact you expect. **Do not attach real prompts,
transcripts, secrets, or event exports from real work**; reproduce with synthetic data.

What to expect: an acknowledgement within a few days, a fix or an explanation as time allows
(this is a volunteer project; there is no bounty), and credit in the advisory and changelog
unless you prefer otherwise. Please allow time to fix before public disclosure.

## Scope

In scope:

- leakage of prompts, thinking text, file contents, command output, environment, emails or
  transcript paths into persisted state, logs or exports;
- unsafe subprocess, path, symlink or junction handling, including behaviour on a hostile
  repository (malicious `.git/config`, hooks, lockfile, config or artifacts);
- unsafe install, uninstall or merge of `hooks.json`, rules, skills and `AGENTS.md`;
- a hook that blocks, hangs or crashes Cursor instead of failing open;
- terminal-escape or markup injection through untrusted strings shown by the CLI or TUI;
- supply-chain issues in our build and release workflows.

Out of scope:

- behaviour of Cursor itself, git, or third-party dependencies (report those upstream);
- enforcement guarantees, which v0.1 does not provide;
- attacks by a process already running as the same user (they can already read your
  repository and files), and forged events or artifacts from such a process
  ([accepted risk SA-01](docs/security-review-v0.1.md));
- denial of service by filling your own disk, beyond the documented caps;
- findings that depend on unverified Cursor behaviour, unless you can demonstrate them.

## Known issues and review

The v0.1 pre-release review, its fixed findings and its accepted risks are in
[docs/security-review-v0.1.md](docs/security-review-v0.1.md). It is a self-review, not an
independent audit.
