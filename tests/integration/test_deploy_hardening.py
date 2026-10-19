"""Deployment-hardening checks (MM-44).

The rendered-chart checks run ``helm template`` on the gate runner and parse its
output. This module pins the ``CI validates the oauth2proxy auth render``
requirement (``deploy-validate`` must render ``auth.mode=oauth2proxy`` and
validate it with kubeconform) and the oauth2-proxy selector/ingress render.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
CHART_README = ROOT / "deploy" / "helm" / "mintmory" / "README.md"


def _deploy_validate_steps() -> list[dict[str, Any]]:
    """The step list of the ``deploy-validate`` job in ``ci.yml``."""
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["deploy-validate"]["steps"]
    assert isinstance(steps, list)
    return steps


@pytest.mark.l4("C-f0b32952", "C-d55fe94d")
def test_ci_validates_oauth2proxy_render() -> None:
    required = (
        "auth.mode=oauth2proxy",
        "auth.oauth2proxy.oidcIssuerUrl=",
        "auth.oauth2proxy.clientId=",
        "auth.oauth2proxy.clientSecret=",
        "ingress.enabled=true",
        "kubeconform -strict",
    )
    runs = [step["run"] for step in _deploy_validate_steps() if isinstance(step.get("run"), str)]
    matching = [run for run in runs if all(token in run for token in required)]
    assert matching, (
        "deploy-validate must render the chart with auth.mode=oauth2proxy and "
        "validate it with kubeconform"
    )


def _render(*extra: str) -> list[dict[str, Any]]:
    """``helm template`` the chart as release ``t`` and return its non-empty documents."""
    result = subprocess.run(
        ["helm", "template", "t", "deploy/helm/mintmory", *extra],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def _one(documents: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    """The single rendered object with ``kind`` and ``metadata.name``."""
    matches = [
        document
        for document in documents
        if document.get("kind") == kind and document["metadata"]["name"] == name
    ]
    assert len(matches) == 1, f"expected exactly one {kind}/{name}, found {len(matches)}"
    return matches[0]


@pytest.mark.l4("C-a45cc480")
def test_oauth2proxy_render_selectors_disjoint() -> None:
    documents = _render(
        "--set",
        "auth.mode=oauth2proxy",
        "--set",
        "auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com",
        "--set",
        "auth.oauth2proxy.clientId=mintmory-ci",
        "--set",
        "auth.oauth2proxy.clientSecret=ci-placeholder",
        "--set",
        "ingress.enabled=true",
    )
    proxy = _one(documents, "Deployment", "t-mintmory-oauth2-proxy")
    app = _one(documents, "Deployment", "t-mintmory")
    app_service = _one(documents, "Service", "t-mintmory")
    proxy_service = _one(documents, "Service", "t-mintmory-oauth2-proxy")

    expected_proxy_labels = {
        "app.kubernetes.io/name": "mintmory-oauth2-proxy",
        "app.kubernetes.io/instance": "t",
        "app.kubernetes.io/component": "oauth2-proxy",
    }
    proxy_pod_labels = proxy["spec"]["template"]["metadata"]["labels"]
    assert proxy_pod_labels == expected_proxy_labels
    assert proxy["spec"]["selector"]["matchLabels"] == expected_proxy_labels

    expected_app_labels = {
        "app.kubernetes.io/name": "mintmory",
        "app.kubernetes.io/instance": "t",
    }
    app_pod_labels = app["spec"]["template"]["metadata"]["labels"]
    assert app["spec"]["selector"]["matchLabels"] == expected_app_labels
    assert app_service["spec"]["selector"] == expected_app_labels

    assert not (app_service["spec"]["selector"].items() <= proxy_pod_labels.items())
    assert proxy_service["spec"]["selector"].items() <= proxy_pod_labels.items()
    assert not (proxy_service["spec"]["selector"].items() <= app_pod_labels.items())


@pytest.mark.l4("C-3ebe6ecd")
def test_postgres_pdb_does_not_select_oauth2proxy() -> None:
    documents = _render(
        "-f",
        "deploy/helm/mintmory/values-postgres.yaml",
        "--set",
        "auth.mode=oauth2proxy",
        "--set",
        "auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com",
        "--set",
        "auth.oauth2proxy.clientId=mintmory-ci",
        "--set",
        "auth.oauth2proxy.clientSecret=ci-placeholder",
        "--set",
        "ingress.enabled=true",
    )
    proxy = _one(documents, "Deployment", "t-mintmory-oauth2-proxy")
    pdb = _one(documents, "PodDisruptionBudget", "t-mintmory")

    expected_app_labels = {
        "app.kubernetes.io/name": "mintmory",
        "app.kubernetes.io/instance": "t",
    }
    pdb_labels = pdb["spec"]["selector"]["matchLabels"]
    assert pdb_labels == expected_app_labels
    proxy_pod_labels = proxy["spec"]["template"]["metadata"]["labels"]
    assert not (pdb_labels.items() <= proxy_pod_labels.items())


@pytest.mark.l4("C-2f129c5f")
def test_chart_readme_documents_tag_scheme_and_upgrade_step() -> None:
    text = CHART_README.read_text(encoding="utf-8")
    required = (
        "vX.Y.Z",
        "X.Y.Z",
        "latest",
        "app.kubernetes.io/name",
        "oauth2-proxy Deployment",
        "helm upgrade",
    )
    missing = [substring for substring in required if substring not in text]
    assert not missing, f"chart README must contain {missing!r}"


@pytest.mark.l4("C-ce708748")
def test_oauth2proxy_render_wires_external_auth() -> None:
    documents = _render(
        "--set",
        "auth.mode=oauth2proxy",
        "--set",
        "auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com",
        "--set",
        "auth.oauth2proxy.clientId=mintmory-ci",
        "--set",
        "auth.oauth2proxy.clientSecret=ci-placeholder",
        "--set",
        "ingress.enabled=true",
    )
    none_documents = _render("--set", "ingress.enabled=true")

    proxy = _one(documents, "Deployment", "t-mintmory-oauth2-proxy")
    _one(documents, "Service", "t-mintmory-oauth2-proxy")
    secret = _one(documents, "Secret", "t-mintmory-oauth2-proxy")
    ingress = _one(documents, "Ingress", "t-mintmory")

    secret_keys = set(secret.get("stringData", {})) | set(secret.get("data", {}))
    assert {"client-secret", "cookie-secret"} <= secret_keys

    annotations = ingress["metadata"]["annotations"]
    auth_url = annotations["nginx.ingress.kubernetes.io/auth-url"]
    auth_signin = annotations["nginx.ingress.kubernetes.io/auth-signin"]
    assert auth_url.startswith("http://t-mintmory-oauth2-proxy.")
    assert "/oauth2/start" in auth_signin

    paths = ingress["spec"]["rules"][0]["http"]["paths"]
    oauth2_paths = [path for path in paths if path["path"] == "/oauth2"]
    assert len(oauth2_paths) == 1
    assert oauth2_paths[0]["backend"]["service"]["name"] == "t-mintmory-oauth2-proxy"

    app = _one(documents, "Deployment", "t-mintmory")
    app_plain = _one(none_documents, "Deployment", "t-mintmory")
    app_containers = app["spec"]["template"]["spec"]["containers"]
    assert app_containers == app_plain["spec"]["template"]["spec"]["containers"]

    container = app_containers[0]
    assert container["livenessProbe"]["httpGet"]["path"] == "/healthz"
    assert container["readinessProbe"]["httpGet"]["path"] == "/readyz"

    app_service = _one(documents, "Service", "t-mintmory")
    proxy_pod_labels = proxy["spec"]["template"]["metadata"]["labels"]
    assert not (app_service["spec"]["selector"].items() <= proxy_pod_labels.items())
