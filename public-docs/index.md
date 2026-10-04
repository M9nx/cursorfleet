<div class="cf-home-page" markdown="0">
<section class="cf-home-hero" aria-labelledby="cf-home-title">
<div class="cf-home-container cf-home-hero__layout">
<div class="cf-home-hero__copy">
<p class="cf-home-hero__eyebrow"><span>Local</span><span>Observe-only</span><span>Pre-alpha</span></p>
<h1 id="cf-home-title" class="cf-home-hero__title">CursorFleet</h1>
<p class="cf-home-hero__statement">Observe your local agent team from one terminal.</p>
<p class="cf-home-hero__subtitle">A local TUI and workflow harness for following parallel coding agents, their activity, and handoffs — without taking control of their work.</p>
<div class="cf-home-hero__actions">
<a href="getting-started/installation/" class="cf-home-hero__btn cf-home-hero__btn--primary">Install</a>
<a href="getting-started/quickstart/" class="cf-home-hero__btn">Quickstart</a>
<a href="https://github.com/M9nx/cursorfleet" class="cf-home-hero__link" rel="noopener">View on GitHub</a>
</div>
<p class="cf-home-hero__status">Pre-alpha · Observe-only · Local-first</p>
<p class="cf-home-hero__limits"><a href="known-limitations/">Known limitations</a></p>
<p class="cf-home-hero__note">Unofficial project. Not affiliated with Anysphere.</p>
</div>
<div class="cf-home-hero__visual" aria-hidden="true">
<div class="cf-home-hero__visual-glow"></div>
<img class="cf-home-hero__spiral" src="assets/hero-spiral.svg" alt="" width="800" height="700" decoding="async">
</div>
</div>
</section>

<section class="cf-home-section cf-home-capabilities" aria-labelledby="cf-home-cap-title">
<div class="cf-home-container">
<h2 id="cf-home-cap-title" class="cf-home-section__title">What CursorFleet provides</h2>
<ul class="cf-home-capabilities__grid">
<li class="cf-home-card">
<span class="cf-home-card__icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="12" cy="12" r="3"/><path d="M3 12h3m12 0h3M12 3v3m0 12v3"/></svg></span>
<h3 class="cf-home-card__title">Observe</h3>
<p class="cf-home-card__body">See agent activity and workflow state from one local interface.</p>
</li>
<li class="cf-home-card">
<span class="cf-home-card__icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M4 12h6l2-4 4 8 2-4h2"/></svg></span>
<h3 class="cf-home-card__title">Follow</h3>
<p class="cf-home-card__body">Understand parallel tasks, handoffs, and progress without jumping between sessions.</p>
</li>
<li class="cf-home-card">
<span class="cf-home-card__icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h10M7 13h6"/></svg></span>
<h3 class="cf-home-card__title">Stay local</h3>
<p class="cf-home-card__body">CursorFleet observes local workflows and does not need to become the agent orchestrator.</p>
</li>
</ul>
</div>
</section>

<section class="cf-home-section cf-home-preview" aria-labelledby="cf-home-preview-title">
<div class="cf-home-container cf-home-preview__layout">
<div class="cf-home-preview__copy">
<h2 id="cf-home-preview-title" class="cf-home-section__title">One terminal. Your whole agent team.</h2>
<p class="cf-home-preview__desc">The Textual dashboard reads local hook telemetry and read-only git context. It is observe-only, provisional, and under active validation against live Cursor.</p>
<p class="cf-home-preview__hint"><a href="tui/overview/">TUI overview</a> · <a href="tui/current-status/">Current status</a></p>
</div>
<div class="cf-home-terminal" role="img" aria-label="Illustrative terminal layout based on documented TUI lanes; not a live screenshot.">
<div class="cf-home-terminal__bar">cursorfleet tui · observe-only · lanes</div>
<pre class="cf-home-terminal__body"><code>OVERVIEW
────────────────────────────────────────
WORKING     cf-writer    hooks + spool
PLANNING    cf-reviewer  read-only git
UNKNOWN     (no telemetry yet)

<span class="cf-home-terminal__dim">j/k move · Enter detail · q quit</span></code></pre>
</div>
</div>
</section>

<section class="cf-home-section cf-home-install" aria-labelledby="cf-home-install-title">
<div class="cf-home-container cf-home-install__inner">
<h2 id="cf-home-install-title" class="cf-home-section__title">Get started</h2>
<p class="cf-home-install__note">Not on PyPI yet — install from a git checkout (Python 3.11+ and git required).</p>
<div class="cf-home-install__cmd">
<code id="cf-install-cmd">git clone https://github.com/M9nx/cursorfleet &amp;&amp; cd cursorfleet &amp;&amp; uv tool install .</code>
<button type="button" class="cf-home-install__copy" data-copy-target="cf-install-cmd">Copy</button>
</div>
<p class="cf-home-install__next"><a href="getting-started/quickstart/">Quickstart</a> · <a href="getting-started/installation/">Full installation</a></p>
</div>
</section>

<footer class="cf-home-legal">
<div class="cf-home-container">
<p>CursorFleet is an unofficial open-source project and is not affiliated with or endorsed by Anysphere or Cursor. &ldquo;Cursor&rdquo; is a trademark of its respective owner. CursorFleet is currently a working name.</p>
</div>
</footer>
</div>
<script>
(function () {
  var btn = document.querySelector(".cf-home-install__copy");
  if (!btn) return;
  btn.addEventListener("click", function () {
    var id = btn.getAttribute("data-copy-target");
    var el = id && document.getElementById(id);
    if (!el || !navigator.clipboard) return;
    var text = el.textContent || "";
    navigator.clipboard.writeText(text).then(function () {
      btn.textContent = "Copied";
      window.setTimeout(function () { btn.textContent = "Copy"; }, 1600);
    });
  });
})();
</script>
