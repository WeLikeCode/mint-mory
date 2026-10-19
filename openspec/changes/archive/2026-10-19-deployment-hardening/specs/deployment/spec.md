# Capability: deployment (delta)

## ADDED Requirements

### Requirement: Published container image
CI publishes the light image to `ghcr.io/<owner>/<repo>`, and a release tag `vX.Y.Z`
publishes the image tag `X.Y.Z` (the CI behaviour is in `design.md` section 2: it is
checked by the repository CI and by review, not by these scenarios). For that tag to be
the chart's default image tag, the chart's `appVersion` SHALL equal the package version,
and `scripts/bump_version.py` SHALL rewrite the double-quoted `appVersion` line of
`deploy/helm/mintmory/Chart.yaml` with the five package `pyproject.toml` files, through
`bump_chart_text(text: str, new_version: str) -> str` and
`main(argv: list[str] | None = None, root: Path | None = None) -> None`. A chart without
that line, or a version that is not `X.Y.Z`, SHALL fail the bump with nothing written.

#### Scenario: The chart's default tag tracks the release version
- **WHEN** the test compares `appVersion` from `deploy/helm/mintmory/Chart.yaml` with `project.version` from `packages/meta/pyproject.toml`
- **THEN** they are equal, and `scripts/bump_version.py X.Y.Z` rewrites the Chart `appVersion` to `"X.Y.Z"` (the chart's own `version:` line is left unchanged; see the next scenarios), so the tag that `release.yml` accepts (`vX.Y.Z` equal to the package version) always publishes the chart's default image tag.

#### Scenario: bump_version.py updates the chart through main()
- **GIVEN** a root with the five package `pyproject.toml` files at `version = "0.1.0"` and `deploy/helm/mintmory/Chart.yaml` containing `apiVersion: v2\nname: mintmory\nversion: 0.1.0\nappVersion: "0.1.0"\n`
- **WHEN** `main(["0.2.0"], root=<that root>)` runs (`main(argv=None, root=None)` defaults to `sys.argv[1:]` and the repository root)
- **THEN** Chart.yaml is `apiVersion: v2\nname: mintmory\nversion: 0.1.0\nappVersion: "0.2.0"\n`, the five pyprojects have `version = "0.2.0"`, and stdout contains the line `bumped deploy/helm/mintmory/Chart.yaml`.

#### Scenario: A Chart without a double-quoted appVersion fails the bump and writes nothing
- **GIVEN** the same root but Chart.yaml is `appVersion: 0.1.0\n` (or single-quoted, or has no `appVersion` line)
- **WHEN** `main(["0.2.0"], root=<that root>)` runs, or `bump_chart_text` is called on that text
- **THEN** `bump_chart_text` raises `ValueError("appVersion line not found")`, `main` exits via `SystemExit` with a message containing `appVersion`, and no file (pyproject or chart) has been modified.

#### Scenario: A bad version argument is rejected
- **WHEN** `main(["1.2"], root=<that root>)` runs
- **THEN** `SystemExit("usage: bump_version.py X.Y.Z")` is raised and no file is modified.

### Requirement: Selectable ingress authentication mode
The chart's `auth.mode` is `none` (default), `basic` or `oauth2proxy`; `none` and
`basic` are the simple and advanced tiers of the deployment spec's requirement "Simple
and advanced deployment tiers" and do not change here. In `oauth2proxy` mode the chart
SHALL deploy oauth2-proxy for a bring-your-own OIDC provider and SHALL route ingress auth
through it with ingress-nginx external-auth annotations, with no application code or
container change, the health probes still reachable, and application traffic kept on
the application pods.

#### Scenario: oauth2-proxy mode wires external auth without app changes
- **WHEN** the chart is rendered with `helm template` as release `t` twice: in mode `none` with only `--set ingress.enabled=true`, and in mode `oauth2proxy` with `--set auth.mode=oauth2proxy --set auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com --set auth.oauth2proxy.clientId=mintmory-ci --set auth.oauth2proxy.clientSecret=ci-placeholder --set ingress.enabled=true`
- **THEN** the `oauth2proxy` render has a Deployment, a Service and a Secret named `t-mintmory-oauth2-proxy` (the Secret holds the keys `client-secret` and `cookie-secret`); its Ingress `t-mintmory` has the annotation `nginx.ingress.kubernetes.io/auth-url` starting with `http://t-mintmory-oauth2-proxy.` and `nginx.ingress.kubernetes.io/auth-signin` containing `/oauth2/start`, and a path `/oauth2` whose backend is Service `t-mintmory-oauth2-proxy`; the containers of its Deployment `t-mintmory` equal those of the `none` render, and their liveness and readiness probes are `httpGet` on `/healthz` and `/readyz` (the kubelet calls the pod, not the ingress); and the selector of Service `t-mintmory` is NOT a subset of the pod-template labels of Deployment `t-mintmory-oauth2-proxy`, so no application request reaches oauth2-proxy.

### Requirement: oauth2-proxy pods have their own selector labels
In `auth.mode: oauth2proxy` the oauth2-proxy pods SHALL carry
`app.kubernetes.io/name: <chart name>-oauth2-proxy`, and the oauth2-proxy Deployment
and Service SHALL select on that label, so the application Service, Deployment and
PodDisruptionBudget selectors never match an oauth2-proxy pod and application
traffic never reaches oauth2-proxy. The application selectors SHALL NOT change.

#### Scenario: The rendered selectors are disjoint
- **WHEN** the chart is rendered with `helm template` as release `t` with `--set auth.mode=oauth2proxy --set auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com --set auth.oauth2proxy.clientId=mintmory-ci --set auth.oauth2proxy.clientSecret=ci-placeholder --set ingress.enabled=true`
- **THEN** Deployment `t-mintmory-oauth2-proxy` has pod-template labels `{app.kubernetes.io/name: mintmory-oauth2-proxy, app.kubernetes.io/instance: t, app.kubernetes.io/component: oauth2-proxy}` and the same `matchLabels`; the selector of Service `t-mintmory` is NOT a subset of those pod labels; the selector of Service `t-mintmory-oauth2-proxy` IS a subset of them and is NOT a subset of the pod labels of Deployment `t-mintmory`; and the application selectors are unchanged: Deployment `t-mintmory` still has `matchLabels` `{app.kubernetes.io/name: mintmory, app.kubernetes.io/instance: t}` and Service `t-mintmory` still has exactly that selector.

Facts the render relies on (read from the chart): the oauth2-proxy pod template carries only the helper labels (no `podLabels` are merged into it; `podLabels` apply to `deployment.yaml` only), and `values-postgres.yaml` renders the PDB `t-mintmory` with no further required values (CI already renders it that way).

#### Scenario: The postgres-mode PodDisruptionBudget does not cover oauth2-proxy
- **WHEN** the same render adds `-f deploy/helm/mintmory/values-postgres.yaml`
- **THEN** the `matchLabels` of PodDisruptionBudget `t-mintmory` are NOT a subset of the oauth2-proxy pod-template labels, and are still exactly `{app.kubernetes.io/name: mintmory, app.kubernetes.io/instance: t}`.

#### Scenario: The README documents the tag scheme and the upgrade step
- **WHEN** `tests/integration/test_deploy_hardening.py` reads `deploy/helm/mintmory/README.md`
- **THEN** the text contains each of the substrings `vX.Y.Z`, `X.Y.Z`, `latest`, `app.kubernetes.io/name`, `oauth2-proxy Deployment` and `helm upgrade`.
