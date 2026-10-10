"""Regression tests for the recruiter-facing chat page.

These keep the requested UX from silently regressing: clickable example
prompts, source chunks shown per answer, a "not in my notes" response, links
to /health /metrics /docs, and the free-tier cold-start "waking up" message.
"""

from app.config import get_settings

STATIC = get_settings().static_dir
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")


def test_page_links_health_metrics_docs():
    for href in ("/health", "/metrics", "/docs"):
        assert f'href="{href}"' in HTML


def test_example_prompts_are_clickable_chips():
    assert 'class="chip"' in HTML
    assert 'data-q="What is a Kubernetes Deployment?"' in HTML


def test_frontend_handles_waking_up_state():
    assert 'id="waking"' in HTML
    assert "/api/v1/ready" in JS
    assert "waking" in JS


def test_sources_render_the_chunk_text():
    assert "chunk" in JS
    assert "sources" in JS
    assert "notfound" in JS
