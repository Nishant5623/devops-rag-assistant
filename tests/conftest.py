"""Shared pytest fixtures.

The rate limiter is process-global and keys on the client address, which is the
same ("testclient") for every TestClient call. As the suite grew its number of
rate-limited /ask and /ingest requests, they accumulated across tests and could
trip a 429 that had nothing to do with the behaviour under test. Clearing the
window between tests keeps each test independent.
"""

import pytest
from app.main import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter.reset()
    yield
