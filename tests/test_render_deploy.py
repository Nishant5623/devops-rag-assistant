"""
Guards for the Render deployment.

These are config-regression tests, not application tests. The failure they
prevent is specific and expensive: a Render deploy that builds fine, passes its
health check, and then serves 502 on every request, or leaves /ingest and
/metrics open to the internet because a key was left blank.

The port test exists because the Dockerfile used to hardcode
`--port 8000` in CMD while Render assigns the listen port via $PORT. Every
request would have hit a closed port.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
RENDER_YAML = ROOT / "render.yaml"
DOCKERFILE = ROOT / "Dockerfile"
ENTRYPOINT = ROOT / "docker-entrypoint.sh"


@pytest.fixture(scope="module")
def blueprint() -> dict:
    return yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def service(blueprint: dict) -> dict:
    services = blueprint["services"]
    assert len(services) == 1, "expected exactly one service in render.yaml"
    return services[0]


@pytest.fixture(scope="module")
def env(service: dict) -> dict[str, dict]:
    return {e["key"]: e for e in service["envVars"]}


# --- Service shape ---------------------------------------------------------
def test_service_is_a_free_docker_web_service(service: dict) -> None:
    assert service["type"] == "web"
    assert service["runtime"] == "docker"
    assert service["plan"] == "free"


def test_uses_repo_dockerfile_and_context(service: dict) -> None:
    assert service["dockerfilePath"] == "./Dockerfile"
    assert service["dockerContext"] == "."


def test_health_check_path_is_a_real_route(service: dict) -> None:
    """The health check must be the readiness route, not liveness.

    /api/v1/health returns 200 even with no index, so using it would let
    Render route traffic to a replica that cannot answer questions.
    """
    assert service["healthCheckPath"] == "/api/v1/ready"


# --- The port contract -----------------------------------------------------
def test_render_does_not_hardcode_port(env: dict[str, dict]) -> None:
    """Render injects $PORT and routes to whatever it assigns.

    Pinning it in the blueprint can silently disagree with Render's own
    assignment and produce a service nothing can reach.
    """
    assert "PORT" not in env


def test_entrypoint_honours_port_env() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "${PORT:-8000}" in text, "entrypoint must read $PORT with a default"


def test_dockerfile_does_not_hardcode_the_listen_port() -> None:
    """Regression guard: CMD used to pin --port 8000, breaking Render.

    The port now comes from docker-entrypoint.sh. Only a top-level instruction
    counts here - a Dockerfile instruction must start at column 0, so the
    `CMD` inside the HEALTHCHECK block is a continuation line, not a CMD that
    would override the entrypoint.
    """
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    instructions = [
        line.split(maxsplit=1)[0]
        for line in dockerfile.splitlines()
        if line and not line[0].isspace()
    ]
    assert "CMD" not in instructions, (
        "Dockerfile must not define a top-level CMD with a hardcoded port; "
        "docker-entrypoint.sh resolves $PORT instead"
    )
    assert "ENTRYPOINT" in instructions
    assert 'ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]' in dockerfile


def test_dockerfile_copies_and_execs_the_entrypoint() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY docker-entrypoint.sh" in dockerfile
    assert "chmod +x /usr/local/bin/docker-entrypoint.sh" in dockerfile


# --- Proxy / rate limiting -------------------------------------------------
def test_proxy_headers_enabled(env: dict[str, dict]) -> None:
    """Without this, every visitor shares one rate-limit bucket.

    Render proxies to the container, so slowapi would otherwise see the proxy
    IP as the client and collapse all traffic into a single 10/min bucket.
    """
    assert env["PROXY_HEADERS"]["value"] == "1"


# --- Security --------------------------------------------------------------
def test_admin_key_is_generated_not_hardcoded(env: dict[str, dict]) -> None:
    """A blank ADMIN_API_KEY leaves /ingest and /metrics open to the world.

    _is_admin() returns True for every caller when no key is configured, and
    AdminGateMiddleware skips its check entirely, so this is the difference
    between a public read-only service and an open one that anyone can use to
    trigger re-ingestion.
    """
    entry = env["ADMIN_API_KEY"]
    assert entry.get("generateValue") is True
    assert "value" not in entry, "never commit a literal admin key"


def test_anthropic_key_is_never_committed(env: dict[str, dict]) -> None:
    entry = env["ANTHROPIC_API_KEY"]
    assert entry.get("sync") is False
    assert "value" not in entry


def test_runs_in_production_mode(env: dict[str, dict]) -> None:
    assert env["ENV"]["value"] == "production"
    assert env["AUTO_INGEST"]["value"] == "true"


def test_chroma_dir_is_writable_and_ephemeral_safe(env: dict[str, dict]) -> None:
    """Render's free disk is ephemeral, so the index is rebuilt every wake.

    Pointing at /tmp also keeps it off the application directory, which is
    not writable for arbitrary users on some platforms.
    """
    # S108 does not apply: this is a configured string being asserted on, not
    # a temporary file this process creates.
    assert env["CHROMA_DIR"]["value"].startswith("/tmp/")  # noqa: S108


def test_no_cors_wildcard_on_a_public_url(env: dict[str, dict]) -> None:
    """The UI is served by this same app, so same-origin needs no CORS."""
    assert env["CORS_ORIGINS"]["value"] == "[]"


def test_no_secret_looking_values_committed(blueprint: dict) -> None:
    raw = RENDER_YAML.read_text(encoding="utf-8")
    for marker in ("sk-ant-", "ghp_", "AKIA", "BEGIN PRIVATE KEY"):
        assert marker not in raw, f"possible committed secret: {marker}"
    assert blueprint  # keeps the fixture honest
