# Contributing to CursorFleet

CursorFleet is pre-alpha and unofficial. Issues and small PRs are welcome; for larger changes
please open an issue first. For security problems do **not** open a public issue: see
[SECURITY.md](SECURITY.md).

## Setup

```bash
uv sync --all-extras
uv run cursorfleet --version
```

## Checks (must pass before a PR)

```bash
uv run ruff check .
uv run ruff format --check .      # `uv run ruff format .` fixes it
uv run mypy src
uv run pytest                     # benchmark-marked tests are excluded by default
```

CI runs the same on Linux, macOS and Windows with Python 3.11 to 3.14, plus a job that builds
the wheel and smoke-tests it in a clean venv. To reproduce that locally:

```bash
uv build && python scripts/check_dist.py dist
uv venv /tmp/cf-venv && uv pip install --python /tmp/cf-venv dist/*.whl
python scripts/smoke_wheel.py /tmp/cf-venv
python scripts/demo.py --venv /tmp/cf-venv      # synthetic demo, no Cursor
```

Coverage: `uv run pytest --cov=cursorfleet --cov-report=term-missing`. Hook timings:
`uv run pytest -m benchmark` or `uv run python scripts/bench_hook.py`.

Without uv: `python -m venv .venv && .venv/bin/pip install -e ".[watch]" --group dev` (pip >= 25.1),
then run the tools from `.venv/bin`.

## Conventions

Read [`AGENTS.md`](AGENTS.md). Highlights:

- the hook hot path is stdlib-only and fails open (exit 0 with the right reply);
- every subprocess uses an argv list and an explicit `timeout=`; resolve tools with
  `cursorfleet.safeexe.find_executable`, never from the current directory;
- never persist prompts, thinking, file contents, command output, env, emails or transcript
  paths; drop them at the parser boundary with an allowlist;
- no sleeps in tests; keep Windows, macOS and Linux behaviour in step and skip a test only with
  an explicit `reason=`;
- security-relevant changes get a regression test under `tests/security/`;
- documentation must stay honest: mark anything that depends on unverified Cursor behaviour
  as PROVISIONAL, and do not claim enforcement.

Do not commit real Cursor payloads. Fixtures under `tests/fixtures/cursor` must be captured,
reviewed and sanitized, with the Cursor version recorded; doc-derived examples live in
`spike/doc_examples` and are not fixtures.

By contributing you agree your work is licensed under the MIT License.
