# Proposal: fix 2 for add-local-observability-stack

## Why
Requested by CiprianSpot, 2026-10-18T19:51:33Z in FB-001 (tests, tests/integration/test_helm_telemetry.py:121-131, tests/integration/test_observability_stack.py:197-199): Remove the three @pytest.mark.skipif(shutil.which(...) is None, ...) markers and keep the tests as they are. helm and docker are on the gate runner: the gates already ran these three tests and they passed (the skipped count stayed 114). L4's integrity check refuses any added skip or xfail marker (blocker F-5758ac1b), whatever the spec text says; the spec's 'skipped otherwise' note is outdated.

    @pytest.mark.l4("C-7836148e")
    @pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
    def test_helm_template_defaults_disable_telemetry() -> None:
        output = _helm_template()
        assert 'MINTMORY_OTEL_ENABLED: "false"' in output
        assert "OTEL_TRACES_SAMPLER" not in output


    @pytest.mark.l4("C-7836148e")
    @pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
    def test_helm_template_renders_sampler_values() -> None:
    @pytest.mark.l4("C-d797e1ac")
    @pytest.mark.skipif(shutil.which("docker") is None, reason="docker is not installed")
    def test_docker_compose_config_accepts_the_stack() -> None:

The verifier found problems in `add-local-observability-stack` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-f5fcb85c (major): Feedback FB-001 (tests): Remove the three @pytest.mark.skipif(shutil.which(...) is None, ...)

## Impact
The code and the tests of `add-local-observability-stack`.
