# Questions — deployment-hardening

<!-- l4:questions v1
How to answer: write under "### Answer" and set **Status** to `answered`.
To accept the clarifier's suggestion as-is, set **Status** to `accepted`.
Status values: open · answered · accepted · answered-by-clarifier · dismissed · superseded
Kind values: technical · product · ambiguous · verdict · harness. For a `verdict` question, start the answer with `accept` or
`reject`, then give your reason; for a `harness` question, with `accept` or `retry`.
Do not change question IDs. Commit and push to the l4/… branch to resume the run. -->

<!-- l4:index:start -->
| ID | Status | Blocking | Kind | Question |
|----|--------|----------|------|----------|
| Q-001 | open | 4.1 | technical | tests/integration/test_deploy_hardening.py:42 needs a deploy-validate oauth2proxy step in the protected .github/workflows/ci.yml |
<!-- l4:index:end -->

---

## Q-001: tests/integration/test_deploy_hardening.py:42 needs a deploy-validate oauth2proxy step in the protected .github/workflows/ci.yml

- **Status:** open
- **Blocking tasks:** 4.1
- **Kind:** technical
- **Asked:** 2026-10-19T04:50Z by deepseek, run r-20261019T0440Z-a1ca, task 4.1

### Context
The frozen red test asserts that some step of jobs.deploy-validate.steps has a `run` string containing auth.mode=oauth2proxy, auth.oauth2proxy.oidcIssuerUrl=, auth.oauth2proxy.clientId=, auth.oauth2proxy.clientSecret=, ingress.enabled=true and `kubeconform -strict` (spec C-f0b32952 / C-d55fe94d, design section 4). The spec and design require this CI step, and the chart already renders the oauth2proxy resources, but .github/workflows/ci.yml is a protected path that the harness reverts at every step (my previous attempt's edit was restored, and the test was then judged failing). I cannot make the test pass without persisting a change there, so I need a human to unfreeze that one file for this task (or apply the step).

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `tests/integration/test_deploy_hardening.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit deployment-hardening`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `.github/workflows/ci.yml`: within `jobs.deploy-validate.steps`, insert immediately after the `Validate rendered manifests (postgres HA)` step a new step: # oauth2-proxy / OIDC SSO auth mode (MM-44) — placeholder OIDC values so the # oauth2proxy Deployment/Service/Secret and the ingress auth annotations render. - name: Validate rendered manifests (oauth2proxy auth) run: | helm template t deploy/helm/mintmory \ --set auth.mode=oauth2proxy \ --set auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com \ --set auth.oauth2proxy.clientId=mintmory-ci \ --set auth.oauth2proxy.clientSecret=ci-placeholder \ --set ingress.enabled=true \ | kubeconform -strict -summary -kubernetes-version 1.29.0 -

### Clarifier suggestion
Edit `.github/workflows/ci.yml`: within `jobs.deploy-validate.steps`, insert immediately after the `Validate rendered manifests (postgres HA)` step a new step:

\      # oauth2-proxy / OIDC SSO auth mode (MM-44) — placeholder OIDC values so the
\      # oauth2proxy Deployment/Service/Secret and the ingress auth annotations render.
      - name: Validate rendered manifests (oauth2proxy auth)
        run: |
          helm template t deploy/helm/mintmory \
            --set auth.mode=oauth2proxy \
            --set auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com \
            --set auth.oauth2proxy.clientId=mintmory-ci \
            --set auth.oauth2proxy.clientSecret=ci-placeholder \
            --set ingress.enabled=true \
\            | kubeconform -strict -summary -kubernetes-version 1.29.0 -

### Answer
<!-- write below this line -->
