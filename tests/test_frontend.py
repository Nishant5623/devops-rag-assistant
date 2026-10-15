"""Regression tests for the recruiter-facing chat page.

These keep the requested UX from silently regressing: clickable example
prompts, source chunks shown per answer, a "not in my notes" response, links
to the public /health and /docs pages plus the GitHub repository, and the
free-tier cold-start "waking up" message.

They also pin the constraints the page has to live inside: the app is served
with a strict Content-Security-Policy (script-src 'self'; style-src 'self';
img-src 'self' data:), so the markup must stay free of inline <script>/<style>
blocks, style="" attributes and remote assets, and every self-hosted file it
references must actually be served.
"""

import asyncio
import re

import httpx
from app.config import get_settings
from app.main import app

STATIC = get_settings().static_dir
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")

GITHUB_URL = "https://github.com/Nishant5623/devops-rag-assistant"
OG_IMAGE = "https://devops-rag-assistant.onrender.com/static/og.png"


def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)

    async def _send() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            return await c.get(path)

    return asyncio.run(_send())


def test_public_footer_links_public_pages_only():
    """The public footer advertises public pages only.

    /metrics requires the X-Admin-Key header, so linking it publicly would
    only send visitors to a 401. Health, the API docs and the GitHub
    repository (added with the redesigned footer) stay.
    """
    for href in ("/health", "/docs", GITHUB_URL):
        assert f'href="{href}"' in HTML
    assert 'href="/metrics"' not in HTML


def test_example_prompts_are_clickable_chips():
    assert 'class="chip"' in HTML
    assert 'data-q="What is a Kubernetes Deployment?"' in HTML


def test_frontend_handles_waking_up_state():
    """The chat UI must explain the cold start instead of looking broken.

    The free instance sleeps after 15 minutes idle, so on wake the page shows a
    live "waking up" bar and retries until the service answers.
    """
    # The waking bar ships in the HTML, hidden, and is revealed by JS on wake.
    assert 'id="waking"' in HTML
    assert re.search(r'id="waking"[^>]*hidden', HTML)
    # A readiness poll starts on page load, before the visitor even types.
    assert "/api/v1/ready" in JS
    assert "watchServer" in JS
    # The user-visible cold-start copy is present.
    assert "Waking up the service" in JS
    assert "Render's free tier" in JS
    # A request that lands mid-wake (502/503/504) is retried, not surfaced raw.
    assert "502" in JS
    assert "503" in JS
    assert "504" in JS


def test_sources_render_the_chunk_text():
    assert "chunk" in JS
    assert "sources" in JS
    assert "notfound" in JS


def test_frontend_does_not_invent_the_answer_wording():
    """The server owns the answer contract; the page renders it verbatim.

    Answers begin with "Matching notes:" and the refusal reads "That's not in my
    notes." — both strings live in app/rag.py (asserted in
    tests/test_answer_behavior.py), so the frontend must not carry its own
    paraphrased copy of them.
    """
    assert "data.answer" in JS
    assert "data.found === false" in JS
    assert "Matching notes" not in JS
    assert "not in my notes" not in JS
    # Sources are collapsible and carry the file, the chunk number and distance.
    assert "details" in JS and "summary" in JS
    assert "chunk " in JS
    assert "distance " in JS


def test_frontend_stays_inside_the_strict_csp():
    """No inline scripts/styles, no style attributes, no remote assets.

    The page is served with script-src 'self'; style-src 'self';
    img-src 'self' data:, so anything inline or off-origin would be blocked
    (and would show up as a console CSP violation).
    """
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", HTML, re.IGNORECASE)
    assert not re.search(r"<style\b", HTML, re.IGNORECASE)
    assert not re.search(r"\sstyle\s*=", HTML, re.IGNORECASE)
    # Every external reference is same-origin, except the absolute social URLs
    # (which are metadata only — never fetched by the browser for rendering).
    assert "http://" not in HTML
    # Absolute https URLs are metadata or outbound links only; nothing the
    # browser has to fetch for rendering lives off-origin.
    allowed = ("https://devops-rag-assistant.onrender.com/", GITHUB_URL)
    for url in re.findall(r"https://[^\s\"'<>]+", HTML):
        assert url.startswith(allowed), url
    # The stylesheet is a separate file and defines the design tokens in one place.
    assert "--accent:" in CSS
    assert "@media (prefers-color-scheme: light)" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS


def test_page_meta_and_open_graph_are_self_hosted():
    assert "<title>" in HTML and "DevOps Knowledge Assistant" in HTML
    assert re.search(r'<meta\s+name="description"', HTML)
    assert re.search(r'<meta\s+name="theme-color"', HTML)
    assert 'href="/favicon.svg"' in HTML
    assert f'content="{OG_IMAGE}"' in HTML
    assert 'property="og:image"' in HTML
    assert 'property="og:image:width" content="1200"' in HTML
    assert 'property="og:image:height" content="630"' in HTML
    assert 'name="twitter:card" content="summary_large_image"' in HTML
    assert 'name="twitter:image"' in HTML


def test_self_hosted_assets_are_served():
    """The favicon, stylesheet, script and preview image are served same-origin.

    /static/og.png is the URL advertised in the Open Graph tags, so it has to
    resolve rather than 404 for link previews to render.
    """
    for name in ("style.css", "app.js", "favicon.svg", "og.png"):
        assert (STATIC / name).is_file(), name
    for path in ("/style.css", "/app.js", "/favicon.svg", "/og.png", "/static/og.png"):
        resp = _get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
