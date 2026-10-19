# Tasks: Deployment hardening (MM-44)

Sections 1–4 shipped in 317e0bf (MM-44) and are out of scope: do not run `docker`,
`helm` or `kubeconform` for them (a review that shows every checkbox empty should rely
on this sentence and on the evidence cited after each task). The work is section 5;
task 4.1 is closed by 5.5's CI render. Section 5 is the gap found by the 2026-10-15 review: release tags never
publish an image, the published tag scheme does not match the chart default, the
oauth2-proxy pods are selected by the application selectors, and CI never renders
`auth.mode=oauth2proxy`. The three CI fixes (5.2, 5.3, 5.5) edit `.github/workflows/ci.yml`,
which L4 never edits: the owner applied them (cited after each task), and they are checked
by the repository CI and by review (`design.md` section 2), not by an L4 test. The open work
is the chart selectors (5.1, 5.4), `scripts/bump_version.py` (5.6) and the chart README (5.7).

## 1. Lock-pinned images
- [x] 1.1 Remove `uv.lock` from `.gitignore` (the orchestrator commits `uv.lock`).
  (`.gitignore:16-18` keeps it un-ignored; `uv.lock` is tracked.)
- [x] 1.2 Dockerfile: restore `COPY pyproject.toml uv.lock ./` + `uv sync --frozen
  --no-dev --extra otel` (light) / `+ --extra local` (full); update the comment.
  (`Dockerfile:42-49`.)
- [x] 1.3 CI `gates` sync: `uv sync --frozen --extra cochange --extra otel`.
  (`ci.yml:34`, now also `--extra postgres`; `ci.yml:74` for `conformance-pg`.)
- [x] 1.4 Verify `docker build --build-arg VARIANT=light` (frozen) builds + `/healthz`
  200; if `--frozen` fails, `uv lock` and note it. (Reported in 317e0bf; CI
  `deploy-validate` builds the light image on every run, `ci.yml:183-184`.)

## 2. GHCR publish
- [x] 2.1 `ci.yml`: `publish-image` job — needs [gates, deploy-validate], `if:
  github.event_name == 'push'`, `permissions: packages: write`; docker/login-action
  (ghcr, github.actor/GITHUB_TOKEN) + metadata-action (branch/sha/tag/latest tags) +
  build-push-action (VARIANT=light, push, gha cache). Light only; no full/torch.
  (`ci.yml` job `publish-image`. It ran for no tag while `on:` had no `tags`
  filter: fixed by 5.2, done by the owner.)
- [x] 2.2 Chart `image.repository` default → `ghcr.io/welikecode/mint-mory`.
  (`deploy/helm/mintmory/values.yaml:25`.)
- [x] 2.3 README: GHCR pull usage + the one-time org "allow GITHUB_TOKEN packages" note.
  (`deploy/helm/mintmory/README.md:7-25`; its tag sentence is corrected by 5.7.)

## 3. oauth2-proxy / OIDC SSO
- [x] 3.1 values: `auth.mode` (none|basic|oauth2proxy, default none) + `auth.basic`
  (== current basicAuth) + `auth.oauth2proxy` (image/provider/issuer/clientId/
  clientSecret/cookieSecret/emailDomains/extraArgs). values.schema.json enum.
  Migrate the existing `ingress.basicAuth.*` to `auth.basic.*` (keep advanced example
  working) OR keep both wired — pick one and keep it consistent.
  (`values.yaml:124-153`, `values.schema.json:165-168`; migrated to `auth.basic`.)
- [x] 3.2 templates: ingress.yaml branches on auth.mode (basic annotations |
  oauth2-proxy auth-url/auth-signin + `/oauth2` path | none);
  oauth2proxy-deployment.yaml + oauth2proxy-service.yaml + oauth2proxy-secret.yaml
  (client-secret + generated cookie-secret), rendered only when mode=oauth2proxy.
  (`templates/ingress.yaml:14-43`, `templates/oauth2proxy-*.yaml`; the selector
  labels are corrected by 5.4.)
- [x] 3.3 README/NOTES: the three auth modes; SSO needs a BYO OIDC provider.
  (`README.md:159-201`, `templates/NOTES.txt:22-28`.)

## 4. Validation
- [x] 4.1 CI renders and validates `auth.mode` none, basic and oauth2proxy (helm lint,
  helm template, kubeconform in the `deploy-validate` job). Done by hand in 317e0bf;
  CI never rendered oauth2proxy. Closed by 5.5: tick it with 5.5, with no local helm,
  docker or kubeconform run.
- [x] 4.2 `docker build --build-arg VARIANT=light` (frozen) + `/healthz` 200.
  (Reported in 317e0bf; the build runs in CI at `ci.yml:183-184`.)
- [x] 4.3 Existing Python gates green (frozen sync). (`ci.yml:34-46`.)
- [x] 4.4 `openspec validate deployment-hardening --strict`.

## 5. Remaining gap (review of 2026-10-15)

The L4 gates (`.l4/config.yaml`: `uv sync --frozen ...` setup creating `.venv`, then ruff, mypy,
pytest) run on a GitHub-hosted Ubuntu runner that has `helm`: the chart tests below run
`helm template` unconditionally and parse its output. Node and the network are not there, and the
`.venv/bin/...` paths exist because the setup gate creates `.venv`. No new test or line may carry
a `skip`, `skipif` or `xfail` marker or call `pytest.skip`, `pytest.xfail` or
`pytest.importorskip`: the harness refuses an added skip marker as a blocker, and a skipped test
proves nothing.
The chart and README tests go in `tests/integration/test_deploy_hardening.py`, the module task 4.1
created (`tests/integration` is in `[tool.pytest.ini_options] testpaths`). Append NEW test
functions to it; do not change its existing test, its other existing lines or `ROOT` (only its
module docstring, which still says the gates have no `helm`, may be rewritten), use the `yaml`
name its existing module-level line binds (task 4.1's; add no other), and add `import subprocess`
(do NOT add a dependency and do NOT run `uv lock`, CI syncs `--frozen`). The bump_version tests go
in `tests/integration/test_bump_version.py`; find the repository root with
`Path(__file__).parents[2]` there, and add `import tomllib` and `import yaml` (PyYAML is installed
through `fastmcp`). Every test function is annotated `-> None` (ruff `ANN`).

- [x] 5.1 Rendered-chart tests for the oauth2-proxy selectors (tests first; this task's green step
  makes the chart change that 5.4 describes, and nothing else). Append to
  `tests/integration/test_deploy_hardening.py` a helper `_render(*extra: str) -> list[dict[str, Any]]`
  that runs `subprocess.run(["helm", "template", "t", "deploy/helm/mintmory", *extra], cwd=ROOT,
  check=False, capture_output=True, text=True)`, asserts `result.returncode == 0` (with
  `result.stderr` as the message) and returns `[d for d in yaml.safe_load_all(result.stdout) if d]`;
  a helper that returns the one object with a given `kind` and `metadata.name` (assert exactly one);
  and these three tests. The oauth2proxy flags are `"--set", "auth.mode=oauth2proxy", "--set",
  "auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com", "--set",
  "auth.oauth2proxy.clientId=mintmory-ci", "--set", "auth.oauth2proxy.clientSecret=ci-placeholder",
  "--set", "ingress.enabled=true"`. A selector check is a subset test: `sel.items() <= labels.items()`.
  - `test_oauth2proxy_render_selectors_disjoint` (C-a45cc480): the scenario "The rendered
    selectors are disjoint", on `_render(*flags)`.
  - `test_postgres_pdb_does_not_select_oauth2proxy` (C-3ebe6ecd): the scenario "The postgres-mode
    PodDisruptionBudget does not cover oauth2-proxy", on
    `_render("-f", "deploy/helm/mintmory/values-postgres.yaml", *flags)`.
  - `test_oauth2proxy_render_wires_external_auth` (C-ce708748): the scenario "oauth2-proxy mode
    wires external auth without app changes"; the mode-`none` render is
    `_render("--set", "ingress.enabled=true")`, and a Secret's keys are those of its `stringData`
    and `data` together (the chart writes `stringData`).
  All three fail by assertion today: the oauth2-proxy pods carry `app.kubernetes.io/name: mintmory`,
  so the application Service and the PDB select them. Green: apply 5.4 exactly as written (a new
  `mintmory.oauth2ProxySelectorLabels` define in `_helpers.tpl`, included in place of
  `mintmory.selectorLabels` + `component` twice in `oauth2proxy-deployment.yaml` and once in
  `oauth2proxy-service.yaml`); then the three pass and the rest of the suite still passes.
- [x] 5.2 `.github/workflows/ci.yml` `on.push`: keep `branches: [main]` and add
  `tags: ["v*"]`. Update the comment above `publish-image`'s `if` if needed.
  Done by the owner in 47d97a5 (L4 does not edit CI workflows).
- [x] 5.3 `ci.yml` step "Docker metadata (tags + labels)": replace the line
  `type=ref,event=tag` with `type=semver,pattern={{version}}` (tag `v0.1.0` →
  image tag `0.1.0`; a pre-release `v0.1.0-beta.2` → `0.1.0-beta.2`), keep the other
  three tag lines, and add `flavor: |` with the single line `latest=false` under
  `with:` (without it, docker/metadata-action's default `latest=auto` also tags a release
  `latest`; the explicit `type=raw,value=latest,enable={{is_default_branch}}`
  line still tags `main` pushes `latest`). Done by the owner in 47d97a5.
- [x] 5.4 Chart selector labels. In `deploy/helm/mintmory/templates/_helpers.tpl` add
  (do NOT edit `mintmory.selectorLabels`):
  ```
  {{- define "mintmory.oauth2ProxySelectorLabels" -}}
  app.kubernetes.io/name: {{ printf "%s-oauth2-proxy" (include "mintmory.name" .) | trunc 63 | trimSuffix "-" }}
  app.kubernetes.io/instance: {{ .Release.Name }}
  app.kubernetes.io/component: oauth2-proxy
  {{- end -}}
  ```
  In `templates/oauth2proxy-deployment.yaml` replace the two blocks
  `{{- include "mintmory.selectorLabels" . | nindent N }}` +
  `app.kubernetes.io/component: oauth2-proxy` (under `spec.selector.matchLabels`, N=6,
  and `spec.template.metadata.labels`, N=8) with
  `{{- include "mintmory.oauth2ProxySelectorLabels" . | nindent N }}`. In
  `templates/oauth2proxy-service.yaml` do the same under `spec.selector` (N=4). The
  `metadata.labels` of these objects (`mintmory.labels` + `component`) stay as they
  are. `deployment.yaml`, `service.yaml` and `pdb.yaml` are NOT edited. The tests are 5.1's: when
  5.1's green step has made this change, this task is already satisfied by them (report
  `already_satisfied by 5.1` with C-a45cc480, C-3ebe6ecd and C-ce708748, and add no test).
- [x] 5.5 `ci.yml` job `deploy-validate`: after the step "Validate rendered manifests
  (postgres HA)" add a step named "Validate rendered manifests (oauth2proxy auth)"
  whose `run` is:
  ```
  helm template t deploy/helm/mintmory \
    --set auth.mode=oauth2proxy \
    --set auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com \
    --set auth.oauth2proxy.clientId=mintmory-ci \
    --set auth.oauth2proxy.clientSecret=ci-placeholder \
    --set ingress.enabled=true \
    | kubeconform -strict -summary -kubernetes-version 1.29.0 -
  ```
  (Without the three OIDC values `templates/oauth2proxy-secret.yaml` calls `fail`;
  without `ingress.enabled=true` the auth-url/auth-signin annotations are not
  rendered.) Then tick 4.1. Done by the owner in 465af8a.
- [ ] 5.6 `scripts/bump_version.py` (today: `PYPROJECTS`, `bump_text(text, new_version)`,
  `main()` reading `sys.argv`, root `Path(__file__).parents[1]`). Add
  `bump_chart_text(text: str, new_version: str) -> str` that rewrites only the first line
  matching `^appVersion: "[^"]+"` (re.M, count=1) to `appVersion: "<new_version>"` and raises
  `ValueError("appVersion line not found")` when no line matches (single-quoted, unquoted or
  absent). Change `main` to `main(argv: list[str] | None = None, root: Path | None = None)`
  (`argv` defaults to `sys.argv[1:]`, `root` to `Path(__file__).parents[1]`; the `__main__`
  call stays `main()`). `main` first computes the new text of the five pyprojects and of
  `deploy/helm/mintmory/Chart.yaml`, and only then writes them all, printing
  `bumped <rel>` per file (the chart line is `bumped deploy/helm/mintmory/Chart.yaml`); a
  `ValueError` becomes `sys.exit("deploy/helm/mintmory/Chart.yaml: appVersion line not found")`
  with nothing written. Tests first in `tests/integration/test_bump_version.py` (it loads the
  script by path, as the existing tests do; use `tmp_path`, `capsys`, `pytest.raises`):
  - `test_bump_chart_rewrites_app_version_only`: on
    `'apiVersion: v2\nname: mintmory\nversion: 0.1.0\nappVersion: "0.1.0"\n'` with `"0.2.0"`
    the result is `'apiVersion: v2\nname: mintmory\nversion: 0.1.0\nappVersion: "0.2.0"\n'`.
  - `test_bump_chart_fails_without_double_quoted_app_version`: for the texts
    `'appVersion: 0.1.0\n'`, `"appVersion: '0.1.0'\n"` and `'name: x\n'`,
    `bump_chart_text(text, "0.2.0")` raises `ValueError`.
  - `test_bump_main_rewrites_chart_and_pyprojects`: build under `tmp_path` the five
    `packages/<name>/pyproject.toml` files (copy of `SAMPLE`) and
    `deploy/helm/mintmory/Chart.yaml` (the text above); `main(["0.2.0"], root=tmp_path)`;
    Chart.yaml now has `appVersion: "0.2.0"` and still `version: 0.1.0`; captured stdout
    contains the line `bumped deploy/helm/mintmory/Chart.yaml`.
  - `test_bump_main_writes_nothing_when_chart_unparseable` (failure case): same tree but
    Chart.yaml is `'appVersion: 0.1.0\n'`; `main(["0.2.0"], root=tmp_path)` raises `SystemExit`
    whose message contains `appVersion`; every pyproject still contains `version = "0.1.0"`.
  - `test_bump_main_rejects_bad_version`: `main(["1.2"], root=tmp_path)` raises `SystemExit`
    with `usage: bump_version.py X.Y.Z`.
  - `test_chart_app_version_matches_package_version` (a guard: it passes today): on the
    repository's own files, `yaml.safe_load` of `deploy/helm/mintmory/Chart.yaml` gives
    `appVersion` equal to the `tomllib` `[project].version` of `packages/meta/pyproject.toml`.
  Traces: C-d321fc4b ("The chart's default tag tracks the release version") on
  `test_chart_app_version_matches_package_version`, `test_bump_chart_rewrites_app_version_only`
  and `test_bump_main_rewrites_chart_and_pyprojects` (the guard alone passes on the base and
  proves nothing, so it never carries the id alone); C-e656ed0f on
  `test_bump_main_rewrites_chart_and_pyprojects`; C-1997c052 on
  `test_bump_chart_fails_without_double_quoted_app_version` and
  `test_bump_main_writes_nothing_when_chart_unparseable`; C-ce80d78d on
  `test_bump_main_rejects_bad_version`. Each test asserts on the outcome (the returned text,
  the files, the `SystemExit` message), so a function that answers its zero value fails it by
  assertion.
- [ ] 5.7 Docs. In `deploy/helm/mintmory/README.md`, section "Pulling the image (GHCR)": say CI
  publishes on pushes to
  the default branch (`main`, `sha-<sha>`, `latest`) and on release tags `vX.Y.Z` as
  the image tag `X.Y.Z` (e.g. `0.1.0`, the chart's default `appVersion`); `latest`
  tracks only the default branch. Add to the oauth2proxy section: oauth2-proxy pods
  now carry `app.kubernetes.io/name: <chart name>-oauth2-proxy`; a release installed
  earlier in `oauth2proxy` mode must delete its `<release>-mintmory-oauth2-proxy`
  Deployment before `helm upgrade`, because a Deployment selector is immutable. Tests first:
  append `test_readme_documents_release_tags_and_upgrade_note` (C-2f129c5f, the scenario "The
  README documents the tag scheme and the upgrade step") to
  `tests/integration/test_deploy_hardening.py`; it fails by assertion today (the README has no
  `vX.Y.Z`).
- [ ] 5.8 Gates (the L4 gates only): `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`,
  `.venv/bin/mypy packages`, `.venv/bin/pytest -q` (coverage gate). Do NOT run `npx`/`openspec`
  here: it needs Node and network, which the runner and `ci.yml` do not provide; the spec files
  are validated with `openspec validate deployment-hardening --strict` by the author before the
  unit starts (see design.md Decisions).
