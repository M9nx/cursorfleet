<div class="cf-home-hero" markdown="0">
<div class="cf-home-hero__layout">
<div class="cf-home-hero__copy">
<h1 class="cf-home-hero__title">CursorFleet</h1>
<p class="cf-home-hero__subtitle">A local TUI and workflow harness for Cursor agent teams.</p>
<p class="cf-home-hero__disclaimer"><strong>Unofficial.</strong> Not affiliated with or endorsed by Anysphere or Cursor. &ldquo;Cursor&rdquo; is a trademark of its respective owner. &ldquo;CursorFleet&rdquo; is a working name.</p>
<ul class="cf-home-hero__actions">
<li><a href="getting-started/installation/" class="md-button md-button--primary">Install</a></li>
<li><a href="getting-started/quickstart/" class="md-button">Quickstart</a></li>
</ul>
</div>
<div class="cf-home-hero__media" aria-hidden="true">
<video class="cf-home-hero__video" autoplay muted loop playsinline poster="assets/hero-poster.jpg">
<source src="assets/hero-loop.mp4" type="video/mp4">
</video>
<img class="cf-home-hero__poster" src="assets/hero-poster.jpg" alt="">
</div>
</div>
</div>

<div class="cf-home-below" markdown="1">

**Pre-alpha, not released.** v0.1 is **Observe** only: passive hooks and read-only git, local Cursor sessions, no enforcement and no cloud-agent visibility. [Known limitations](known-limitations.md) cover open spike questions (Q1/Q2) and parallel-identity **BLOCKED/OPEN** on Cursor 3.22.7 Linux.

<ul class="cf-home-cards">
<li><a href="getting-started/installation/">Install</a><p>Clone the repo and install with uv. Git is required for <code>init</code>.</p></li>
<li><a href="privacy-and-security/">Privacy</a><p>No network calls, no telemetry. Prompts and file contents are not stored.</p></li>
<li><a href="known-limitations/">Known limitations</a><p>Spike status, TUI freeze, and supported surfaces.</p></li>
</ul>

## What you get in the checkout

| Area | What exists today |
| --- | --- |
| Kit | `cursorfleet init --cursor`, `uninstall`, `doctor`, `validate` |
| Observer | Fail-open `cursorfleet-hook`, local spool and projection, `status --json` |
| Dashboard | `cursorfleet tui` — under development, observe-only |
| Scope | One Git repository; runtime state under that repo's Git common directory |

MIT. Source: [github.com/M9nx/cursorfleet](https://github.com/M9nx/cursorfleet).

</div>
