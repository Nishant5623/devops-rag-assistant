import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear slowapi's in-memory limiter state between tests.

    slowapi keeps counters in a process-global store keyed by remote address,
    and every TestClient request looks like it comes from the same host. Without
    this reset, tests that call rate-limited endpoints (/ingest is capped at
    5/minute) start failing with 429 purely because of test ordering.
    """
    from app.main import limiter

    limiter.reset()
    yield
    limiter.reset()
