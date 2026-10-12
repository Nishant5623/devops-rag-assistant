"""Regression tests for the recruiter-facing chat page.

These keep the requested UX from silently regressing: clickable example
prompts, source chunks shown per answer, a "not in my notes" response, links
to the public /health and /docs pages, and the free-tier cold-start "waking
up" message.
"""

import re

from app.config import get_settings

STATIC = get_settings().static_dir
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")


def test_public_footer_links_health_and_docs_only():
    """The public footer advertises public pages only.

    /metrics requires the X-Admin-Key header, so linking it publicly would
    only send visitors to a 401. Health and API docs stay.
    """
    for href in ("/health", "/docs"):
        assert f'href="{href}"' in HTML
    assert 'href="/metrics"' not in HTML


def test_example_prompts_are_clickable_chips():
    assert 'class="chip"' in HTML
    assert 'data-q="What is a Kubernetes Deployment?"' in HTML


def test_frontend_handles_waking_up_state():
    """The chat UI must explain Render's cold start instead of looking broken.

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
