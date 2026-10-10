import asyncio

import httpx
from app.main import app

_CSP_NAME = "content-security-policy"


def _csp_values(resp):
    return [
        value for name, value in resp.headers.multi_items() if name.lower() == _CSP_NAME
    ]


def _get(path: str):
    transport = httpx.ASGITransport(app=app)

    async def _send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.get(path)

    return asyncio.run(_send())


def test_docs_has_exactly_one_csp_header_that_is_the_looser_policy():
    """Browsers enforce every CSP header they receive, so /docs must emit
    exactly one Content-Security-Policy header and it must be the
    SwaggerUI-compatible (looser) policy. If a strict policy were also present
    it would win and white-screen the API docs."""
    resp = _get("/docs")
    assert resp.status_code == 200
    csp = _csp_values(resp)
    assert len(csp) == 1, f"expected exactly one CSP header, got {csp!r}"
    looser = csp[0]
    assert "https://cdn.jsdelivr.net" in looser
    assert "'unsafe-inline'" in looser
    assert "script-src" in looser
    assert "default-src" in looser


def test_redoc_has_exactly_one_looser_csp_header():
    resp = _get("/redoc")
    assert resp.status_code == 200
    csp = _csp_values(resp)
    assert len(csp) == 1
    assert "https://cdn.jsdelivr.net" in csp[0]
    assert "'unsafe-inline'" in csp[0]


def test_app_pages_keep_the_strict_csp():
    resp = _get("/api/v1/health")
    assert resp.status_code == 200
    csp = _csp_values(resp)
    assert len(csp) == 1, f"expected exactly one CSP header, got {csp!r}"
    strict = csp[0]
    assert "cdn.jsdelivr.net" not in strict
    assert "'unsafe-inline'" not in strict
    assert "script-src 'self'" in strict
