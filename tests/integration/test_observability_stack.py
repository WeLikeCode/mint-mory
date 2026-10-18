"""File-level tests for the local observability stack.

Covers the ``Local observability stack`` and ``MintMory API service in the local
stack`` requirements: the compose stack, the collector routing, the Prometheus
scrape config, the ``.env.example`` variables and the repository ``Dockerfile``.
The Docker check runs only where ``docker`` exists (the gates have none).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
STACK = ROOT / "deploy" / "observability"
COMPOSE = STACK / "compose.yaml"
COLLECTOR = STACK / "otel-collector.yaml"
PROMETHEUS = STACK / "prometheus.yml"
ENV_EXAMPLE = STACK / ".env.example"
DOCKERFILE = ROOT / "Dockerfile"

_VAR_RE = re.compile(r"\$\{[A-Z0-9_]+:-(?P<default>[^}]*)\}")
_PORT_RE = re.compile(
    r"\$\{(?P<bind>[A-Z0-9_]+):-127\.0\.0\.1\}"
    r":\$\{(?P<var>[A-Z0-9_]+):-(?P<hostport>\d+)\}"
    r":(?P<containerport>\d+)"
)


def _load_yaml(path: Path) -> dict:
    """Parse ``path`` as a YAML mapping, failing loudly when it is missing."""
    assert path.is_file(), f"{path} must exist"
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), f"{path} must parse to a mapping"
    return data


def _load_compose() -> dict:
    return _load_yaml(COMPOSE)


def _resolve_default(value: str) -> str:
    """Reduce ``${VAR:-default}`` to ``default``; leave plain values alone."""
    match = _VAR_RE.fullmatch(value)
    return match.group("default") if match else value


def _image_tag(image: str) -> str:
    """The tag, i.e. the part after the last ``:`` following the last ``/``."""
    tail = image.rsplit("/", 1)[-1]
    return tail.rsplit(":", 1)[1] if ":" in tail else ""


def _port_strings(service: dict) -> list[str]:
    """Published ports of a compose service, short syntax as written."""
    result: list[str] = []
    for port in service.get("ports", []):
        if isinstance(port, str):
            result.append(port)
        elif isinstance(port, dict):
            result.append(f"{port.get('published', '')}:{port.get('target', '')}")
    return result


def _container_port(port: str) -> str:
    """The container port of a published port (its last colon-separated part)."""
    match = _PORT_RE.fullmatch(port)
    if match:
        return str(match.group("containerport"))
    return port.rsplit(":", 1)[-1]


def _environment(service: dict) -> dict[str, str]:
    """Compose ``environment`` as a mapping, whichever of the two forms is used."""
    env = service.get("environment", {})
    if isinstance(env, dict):
        return {str(key): str(value) for key, value in env.items()}
    mapping: dict[str, str] = {}
    for item in env:
        key, _, value = str(item).partition("=")
        mapping[key] = value
    return mapping


def _uv_sync_commands(text: str) -> list[str]:
    """``uv sync`` command lines from a Dockerfile, ``RUN``/``&&``/``;`` stripped."""
    commands: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        changed = True
        while changed:
            changed = False
            for prefix in ("RUN", "&&", ";"):
                if line.startswith(prefix):
                    line = line[len(prefix) :].strip()
                    changed = True
        if line.startswith("uv sync"):
            commands.append(line)
    return commands


@pytest.mark.l4("C-1ee679bf")
def test_stack_defines_collector_jaeger_and_prometheus() -> None:
    services = _load_compose()["services"]
    assert {"otel-collector", "jaeger", "prometheus"} <= set(services)


@pytest.mark.l4("C-1ee679bf")
def test_stack_images_are_pinned_and_not_latest() -> None:
    services = _load_compose()["services"]
    for name, service in services.items():
        image = service.get("image")
        if image is None:
            continue
        resolved = _resolve_default(image)
        tag = _image_tag(resolved)
        assert tag, f"service {name!r} image {resolved!r} has no tag"
        assert tag != "latest", f"service {name!r} image {resolved!r} uses latest"


@pytest.mark.l4("C-1ee679bf")
def test_stack_published_ports_are_configurable_and_on_loopback() -> None:
    services = _load_compose()["services"]
    published = [port for service in services.values() for port in _port_strings(service)]
    assert published, "the stack must publish at least one port"
    for port in published:
        match = _PORT_RE.fullmatch(port)
        assert match is not None, f"port {port!r} is not bind:published:target"
        assert match.group("hostport") == match.group("containerport")


@pytest.mark.l4("C-1ee679bf")
def test_jaeger_serves_ui_without_publishing_its_otlp_ports() -> None:
    ports = _port_strings(_load_compose()["services"]["jaeger"])
    container_ports = {_container_port(port) for port in ports}
    assert "16686" in container_ports
    assert "4317" not in container_ports
    assert "4318" not in container_ports


@pytest.mark.l4("C-59c20d3b")
def test_collector_otlp_receiver_listens_on_grpc_and_http() -> None:
    protocols = _load_yaml(COLLECTOR)["receivers"]["otlp"]["protocols"]
    assert str(protocols["grpc"]["endpoint"]).endswith(":4317")
    assert str(protocols["http"]["endpoint"]).endswith(":4318")


@pytest.mark.l4("C-59c20d3b")
def test_collector_traces_pipeline_exports_to_jaeger() -> None:
    config = _load_yaml(COLLECTOR)
    pipeline = config["service"]["pipelines"]["traces"]
    assert "otlp" in pipeline["receivers"]
    exporters = [config["exporters"][name] for name in pipeline["exporters"]]
    assert any(exporter.get("endpoint") == "jaeger:4317" for exporter in exporters)


@pytest.mark.l4("C-59c20d3b")
def test_collector_metrics_pipeline_is_scraped_by_prometheus() -> None:
    config = _load_yaml(COLLECTOR)
    pipeline = config["service"]["pipelines"]["metrics"]
    assert "otlp" in pipeline["receivers"]
    assert "prometheus" in pipeline["exporters"]
    prom_port = str(config["exporters"]["prometheus"]["endpoint"]).rsplit(":", 1)[1]
    prometheus = _load_yaml(PROMETHEUS)
    targets = [
        target
        for job in prometheus["scrape_configs"]
        for static in job.get("static_configs", [])
        for target in static["targets"]
    ]
    assert any(str(target).endswith(f":{prom_port}") for target in targets)


@pytest.mark.l4("C-44862bf2")
def test_env_example_documents_every_compose_variable() -> None:
    assert COMPOSE.is_file(), f"{COMPOSE} must exist"
    used = re.findall(r"\$\{(MINTMORY_OBS_[A-Z0-9_]+):-([^}]*)\}", COMPOSE.read_text())
    assert used, "compose.yaml must parameterise the stack with MINTMORY_OBS_* variables"
    assert ENV_EXAMPLE.is_file(), f"{ENV_EXAMPLE} must exist"
    env_text = ENV_EXAMPLE.read_text()
    declared = {
        match.group(1): match.group(2).strip().strip("'\"")
        for match in re.finditer(r"^(MINTMORY_OBS_[A-Z0-9_]+)=(.*)$", env_text, re.MULTILINE)
    }
    for name, default in used:
        assert name in declared, f"{name} is missing from .env.example"
        assert declared[name] == default, f"{name} default differs in .env.example"
    assert "# OTEL_TRACES_SAMPLER=" in env_text


@pytest.mark.l4("C-d797e1ac")
@pytest.mark.skipif(shutil.which("docker") is None, reason="docker is not installed")
def test_docker_compose_config_accepts_the_stack() -> None:
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.l4("C-990f7ec4")
def test_api_profile_is_wired_to_the_collector() -> None:
    compose = _load_compose()
    api = compose["services"]["mintmory-api"]
    assert api.get("profiles") == ["api"]

    build = api["build"]
    context = build["context"] if isinstance(build, dict) else build
    assert (STACK / context).resolve() == ROOT.resolve()
    assert "command" not in api

    volumes = api.get("volumes", [])
    data_sources = [
        volume.split(":")[0]
        for volume in volumes
        if len(volume.split(":")) >= 2 and volume.split(":")[1] == "/data"
    ]
    assert data_sources, "mintmory-api must mount a volume at /data"
    named_volumes = compose.get("volumes", {})
    assert any(source in named_volumes for source in data_sources)

    assert "${MINTMORY_OBS_BIND:-127.0.0.1}:${MINTMORY_OBS_API_PORT:-8080}:8080" in _port_strings(
        api
    )

    environment = _environment(api)
    assert environment.get("OTEL_EXPORTER_OTLP_ENDPOINT") == "http://otel-collector:4318"
    assert environment.get("MINTMORY_OTEL_ENABLED") == "true"

    assert DOCKERFILE.is_file(), f"{DOCKERFILE} must exist"
    commands = _uv_sync_commands(DOCKERFILE.read_text())
    assert len(commands) == 2, f"expected two uv sync commands, found {len(commands)}"
    assert all("--extra otel" in command for command in commands)
