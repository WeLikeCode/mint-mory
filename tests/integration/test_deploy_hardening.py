"""Deployment-hardening checks (MM-44).

The L4 gates have no ``helm``, ``docker`` or network, so every check reads the
repository's workflow or chart text directly. This module currently pins the
``CI validates the oauth2proxy auth render`` requirement: ``deploy-validate``
must render ``auth.mode=oauth2proxy`` and validate it with kubeconform.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


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
