# Docs site plan

Status: **plan only.** No site, workflow file or dependency has been added, and none should
be until the naming gate below is passed. This is the author's own evaluation, written on
2026-10-04; it is not an independent review. Facts about third-party tools were checked
against the pages cited; what could not be checked is listed at the end.

## Recommendation

- **Primary: Zensical**, with docs kept as plain CommonMark/GFM Markdown.
- **Fallback: mdBook**, if Zensical is still early 0.x, has no workable versioning, or
  changes its Markdown toolchain in a way that breaks our files when the decision is made.
- **Do not start a new site on Material for MkDocs or MkDocs.** Material for MkDocs is in
  maintenance mode and MkDocs 1.x is described by the Material team as unmaintained.
- Decide only after the naming gate (ADR 0005) and the live spike, and re-check every
  "unverified" item below on that day.

Rationale:

- Fits a Python/uv project: installable from PyPI into a `docs` dependency group; no Node
  toolchain in a repository that otherwise has none.
- Reads `mkdocs.yml`, so the configuration style is familiar and a fallback to other
  MkDocs-style tooling stays possible.
- Built-in client-side search, Mermaid support (the docs already have two Mermaid diagrams),
  and a maintainer team with a ten-year record on Material for MkDocs.
- Our Markdown is already GitHub-first, and Zensical renders ordinary Markdown, so no
  MDX-only syntax is needed.
- Risks, stated plainly: it is pre-1.0, its Markdown engine is planned to change (the team
  promises migration tooling), plugin support is a subset, and its versioning story is not
  confirmed. mdBook is the boring alternative with none of those risks and fewer features.

## Criteria and evaluation

Ratings are the author's judgment. "Unverified" means not confirmed from a source in this
pass.

### Zensical

- Python/uv fit: good. PyPI package; MIT licence.
- Markdown-first, Mermaid: reads existing `docs/` and `mkdocs.yml`; Mermaid documented
  (page cited below).
- Search: built in (the team's own client-side engine).
- Versioning: unverified.
- Pages deploy: static output; works with the official Pages actions.
- Build speed: the team claims 4 to 5x faster rebuilds than MkDocs; initial builds can be
  slower. Our docs are about thirty small files, so speed does not matter.
- Maintenance risk: medium. Pre-1.0, a company-backed project; its "Zensical Spark" paid
  tier funds development. Breaking changes are plausible.
- Accessibility, dark mode: Material-derived theme; dark mode expected, accessibility not
  audited by me.
- Link checking: not built in as far as I know (unverified); use an external checker.
- Contributor friendliness: good, plain Markdown, `uv run zensical serve`.
- Plain GitHub-rendered Markdown: yes if we avoid Python-Markdown extensions such as
  `!!!` admonitions, content tabs and snippets.

### Material for MkDocs and MkDocs

- Maintenance: the Material team says Material is in maintenance mode with a commitment to
  critical fixes and security fixes for at least 12 months from 2025-11-05, so that window
  ends about November 2026. It says MkDocs 1.x has been unmaintained since August 2024 and
  that MkDocs 2.0 will introduce breaking changes.
- Verdict: do not begin new work on it. Everything else (Markdown, search, Mermaid, `mike`
  versioning) is good but sits on a stack its own authors advise leaving.

### Astro Starlight

- Python/uv fit: poor; adds Node, npm and an Astro project.
- Markdown-first: Markdown and MDX supported; pages need `title` frontmatter, which GitHub
  renders as a table at the top of our existing files, so we would need a build-time copy
  step (unverified).
- Search: Pagefind full-text search is on by default, no configuration (verified).
- Versioning: not built in as far as I know; community plugins exist (unverified).
- Pages deploy: Astro documents a GitHub Pages workflow.
- Dark mode and accessibility: a stated strength of Starlight; not audited by me.
- Mermaid: needs an extra plugin (unverified).
- Maintenance risk: low to medium; large ecosystem. Node supply chain surface is wider.

### Fumadocs

- React and Next.js based, MDX-first. Strong for product sites, a poor fit for a plain
  Markdown Python project; MDX-only features would tempt us away from GitHub-rendered
  Markdown. Not recommended. Details unverified beyond its documentation index.

### Docusaurus

- Node/React. Built-in docs versioning is its strength. MDX is the default parser, which can
  choke on `{`, `<` and `{{ }}` in Markdown written for GitHub unless set to plain
  Markdown mode (unverified). Mermaid via an official theme package (unverified).
  Heavy for thirty files. Reasonable only if versioned docs become a hard requirement.

### VitePress

- Node/Vue. Markdown-first with built-in local search; versioning not built in
  (unverified). Markdown is compiled as a Vue template, so literal `{{ }}` in docs
  (the generated templates use `{{role.implementer}}`-style placeholders) needs escaping
  (unverified). Mermaid via a plugin (unverified). Not recommended for a Python project.

### mdBook

- Rust single binary; plain Markdown plus a `SUMMARY.md` table of contents; built-in search.
  Mermaid via the `mdbook-mermaid` preprocessor and link checking via `mdbook-linkcheck`
  (both unverified). No versioning. No Python or Node. Needs a pinned binary in CI. The
  simplest option and the best fallback; theme and accessibility are basic.

## Migration outline (when the gates pass)

Layout:

- Keep `docs/` as the source. Add one config file at the repository root and a short
  `docs/index.md` landing page (not a copy of the README).
- Eight links from `docs/` to files outside it exist today (mostly `../spike/README.md` and
  `../spike/questions.md`) and break in the built site. Rewrite them to absolute
  repository URLs at build time or keep them as GitHub links; decide per link.
- Do not add MDX, shortcodes or tool-specific syntax to the Markdown. GitHub rendering stays
  the source of truth.

Navigation (draft):

- Start: quickstart, demo, product contract, status.
- Concepts: governance, architecture, privacy, threat model, platform support.
- Reference: kit, TUI, `status --json`, CLI reference, JSON schemas, hook latency.
- Decisions: ADR index and the ADRs.
- Project: empirical test plan, follow-ups, release checklist, changelog, security review.

ADR index and status badges:

- The ADR index is already a bullet list with status, supersession and gates
  ([`adr/README.md`](adr/README.md)). Keep it hand-written, or generate it with a small
  script from each ADR's header fields (the fields are fixed by ADR 0000).
- Status "badges" are plain text in the header (`Status: provisional`), which works in
  GitHub and in the site. Avoid theme-specific badge syntax.

Typer CLI reference:

- Generate Markdown from the Typer app with a script run in CI (Typer has a docs
  generation command; unverified in this pass) and write it to a build-only directory, not
  into `docs/`, so the repository does not carry stale generated text.

JSON schema reference:

- `schemas/*.schema.json` are already generated from the models. Render a short page per
  schema (title, fields, enums) with a script, or link to the raw files; do not hand-copy.

Changelog:

- Pull `CHANGELOG.md` into the build (copy step) instead of duplicating it.

## Actions workflow outline (not created)

Principles: official actions only, pinned by commit SHA at the time of writing the file,
least-privilege `permissions`, no secrets, no third-party deploy tokens, and no deploy from
pull requests.

- Trigger `pull_request` (paths: `docs/**`, config, `README.md`, `CHANGELOG.md`): job `build`
  with `permissions: contents: read`; checkout, set up uv, `uv sync --group docs --frozen`,
  build the site with strict warnings as errors, run the link check, upload nothing.
- Trigger `push` to `main` and tags `v*`: the same `build` job plus
  `actions/configure-pages` and `actions/upload-pages-artifact`; then a separate `deploy` job
  with `permissions: contents: read, pages: write, id-token: write`, `needs: build`, an
  `environment: github-pages`, running `actions/deploy-pages`. These requirements come from
  GitHub's custom-workflow page cited below.
- `concurrency` group for Pages with `cancel-in-progress: false` on deploy.
- Link check job: check internal links and anchors on the built output, and external links
  on a schedule only (so a flaky external site does not fail pull requests). A throwaway
  Python checker like the one used for this documentation pass is enough for internal
  links; a dedicated checker action is an option (unverified, evaluate then).
- Required repository settings (manual, by the owner): Pages source set to "GitHub Actions";
  environment protection on `github-pages`.
- The existing `ci.yml` and `release.yml` stay as they are; the docs workflow is separate.

## What to defer

- **No public docs site before the naming and trademark gate** ([ADR 0005](adr/0005-naming-and-trademark.md)).
  The site URL (repository name), page titles, the package name in install commands and the
  `cursorfleet-*` generated paths all carry the working name. A rename after publishing
  leaves stale indexed pages and links.
- No public site before the live spike either, or the site must open with the same
  "unverified against live Cursor, pre-alpha, unofficial" banner as the README
  ([status](status.md)).
- No custom domain, analytics, comments or a search service. Client-side search only.
- No versioned docs until there is more than one release to document.
- Until then, GitHub renders `docs/` and the ADRs as they are.

## Effort estimate

Rough author estimate, one person, after the gates pass:

- Config, nav, landing page, link rewriting: about 1 day.
- CLI reference and schema reference scripts: about 1 day.
- Workflow, link check, Pages settings, a dry run on a fork: about 0.5 day.
- Accessibility and dark-mode review, banner text: about 0.5 day.
- Total about 3 days; add 1 to 2 days if the fallback (mdBook) is chosen or the first tool
  choice turns out to need workarounds.

## Sources

Checked in this pass (read the page):

- [Zensical announcement by the Material for MkDocs team, 2025-11-05](https://squidfunk.github.io/mkdocs-material/blog/2025/11/05/zensical/):
  Zensical reads `mkdocs.yml`; MIT; subset of plugins; MkDocs unmaintained since August 2024;
  Material in maintenance mode with at least 12 months of critical fixes; rebuilds 4 to 5x
  faster; Python Markdown today with a Rust CommonMark toolchain planned.
- [Starlight site search](https://starlight.astro.build/guides/site-search/): Pagefind by
  default, DocSearch optional.
- [GitHub: custom workflows with Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages):
  `configure-pages`, `upload-pages-artifact`, `deploy-pages`; deploy job needs `pages: write`
  and `id-token: write`; environment `github-pages`.

Read earlier in this task (from my notes; not re-fetched for this edit):

- [Zensical on PyPI](https://pypi.org/project/zensical/): version `0.0.67` at the time,
  pre-1.0. [Zensical getting started](https://zensical.org/docs/get-started/),
  [basics](https://zensical.org/docs/setup/basics/) (`zensical.toml`, reads `mkdocs.yml`) and
  [diagrams](https://zensical.org/docs/authoring/diagrams/) (Mermaid).

Listed for the owner to check, not verified here:

- [Starlight getting started](https://starlight.astro.build/getting-started/) and
  [Astro on GitHub Pages](https://docs.astro.build/en/guides/deploy/github/)
- [Fumadocs](https://www.fumadocs.dev/docs)
- [Docusaurus versioning](https://docusaurus.io/docs/versioning)
- [VitePress](https://vitepress.dev/guide/what-is-vitepress)
- [mdBook](https://rust-lang.github.io/mdBook/)
- [Material for MkDocs repository](https://github.com/squidfunk/mkdocs-material)

## What could not be verified

- Zensical: versioning support, link checking, current release number and stability today,
  whether `README.md` acts as a directory index, exact Mermaid configuration, and whether
  third-party MkDocs plugins we might want (CLI reference generators) work.
- Starlight: versioning plugins, Mermaid plugin, `title` frontmatter requirement details.
- Docusaurus: plain Markdown mode behaviour with GitHub-style Markdown.
- VitePress: handling of literal `{{ }}` and Mermaid plugin status.
- mdBook: current version, `mdbook-mermaid` and `mdbook-linkcheck` maintenance status.
- Typer's docs-generation command and any link-check action.
- Accessibility and dark mode of every tool: not tested.
- Star counts, release dates and download numbers: not gathered (network batch checks were
  blocked in this session).
- Several fetches for other tools' pages were not repeated in this final edit; claims about
  them are from general knowledge and marked unverified above.
