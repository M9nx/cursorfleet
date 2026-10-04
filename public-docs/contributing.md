# Contributing

CursorFleet is pre-alpha and unofficial (not affiliated with or endorsed by
Anysphere or Cursor). Issues and small pull requests are welcome; for larger
changes please open an issue first.

For security problems do **not** open a public issue. Report privately through
GitHub's "Report a vulnerability" on
[M9nx/cursorfleet](https://github.com/M9nx/cursorfleet/security/advisories/new).
Do not attach real prompts, transcripts, secrets, or event exports from real
work; reproduce with synthetic data.

## Setup

```bash
uv sync --all-extras
uv run cursorfleet --version
```

Without uv: `python -m venv .venv && .venv/bin/pip install -e ".[watch]" --group dev`
(pip >= 25.1), then run the tools from `.venv/bin`.

## Checks (must pass before a PR)

```bash
uv run ruff check .
uv run ruff format --check .      # `uv run ruff format .` fixes it
uv run mypy src
uv run pytest                     # benchmark-marked tests are excluded by default
```

CI runs the same on Linux, macOS, and Windows with Python 3.11 to 3.14, plus a
job that builds the wheel and smoke-tests it in a clean venv. To reproduce that
locally:

```bash
uv build && python scripts/check_dist.py dist
uv venv /tmp/cf-venv && uv pip install --python /tmp/cf-venv dist/*.whl
python scripts/smoke_wheel.py /tmp/cf-venv
python scripts/demo.py --venv /tmp/cf-venv      # synthetic demo, no Cursor
```

Coverage: `uv run pytest --cov=cursorfleet --cov-report=term-missing`. Hook
timings: `uv run pytest -m benchmark` or `uv run python scripts/bench_hook.py`.

Public docs (this site) live in `public-docs/`. After editing them:

```bash
uv run zensical build --clean
```

Preview locally with `uv run zensical serve` (default `localhost:8000`). Do not
edit the generated `site/` directory.

### Site branding assets

Header logo, favicon, and Open Graph card live under `public-docs/assets/`:

- `cursorfleet-icon-source.png` — master mark (replace this, then regenerate)
- `logo-circle.png`, `favicon-32.png`, `apple-touch-icon.png` — circular variants
- `cursorfleet-wordmark.png` — footer watermark only
- `og-card.png` — default social preview (1200×630)

Theme paths and metadata are in [`zensical.toml`](../zensical.toml) and
[`public-docs/.meta.yml`](.meta.yml). Head tags (Open Graph, apple-touch-icon)
are extended in [`public-docs/overrides/main.html`](overrides/main.html).

To regenerate derivatives after updating the source PNG, re-run the image
pipeline locally (ffmpeg/Pillow) and commit the outputs so CI/Pages stay
image-tool-free.

## Conventions

Read `AGENTS.md` in the repository. Highlights:

- the hook hot path is stdlib-only and fails open (exit 0 with the right reply);
- every subprocess uses an argv list and an explicit `timeout=`;
- never persist prompts, thinking, file contents, command output, env, emails,
  or transcript paths; drop them at the parser boundary with an allowlist;
- no sleeps in tests; keep Windows, macOS, and Linux behaviour in step;
- security-relevant changes get a regression test under `tests/security/`;
- documentation must stay honest: mark anything that depends on unverified
  Cursor behaviour as provisional, and do not claim enforcement.

Do not commit real Cursor payloads. Fixtures under `tests/fixtures/cursor` must
be captured, reviewed, and sanitized, with the Cursor version recorded.

By contributing you agree your work is licensed under the MIT License.
