# Tasks: Container images + Helm chart (MM-43)

## 1. Container image
- [ ] `Dockerfile` (multi-stage, python:3.12-slim, uv, non-root user 10001, `/data`
  volume, EXPOSE 8080). Build ARG `VARIANT=light|full`: light = `uv sync --package
  mintmory-api --extra otel`; full = `+ --extra local`. CMD runs uvicorn 1 worker,
  no `--reload`. `MINTMORY_DB=/data/memories.db`.
- [ ] `.dockerignore` (.venv, .git, caches, *.db*, .firecrawl, superpowers, etc.).
- [ ] Verify `docker build --build-arg VARIANT=light` succeeds; `docker run` + curl
  `/healthz` → 200 (if daemon available).

## 2. Helm chart `deploy/helm/mintmory/`
- [ ] Chart.yaml, values.yaml (simple defaults), values-simple.yaml,
  values-advanced.yaml, values.schema.json (replicaCount ≤ 1), README.md.
- [ ] templates: _helpers.tpl, deployment.yaml (replicas 1, strategy Recreate,
  probes /healthz+/readyz, envFrom ConfigMap + secretKeyRef, non-root securityContext,
  /data volumeMount), service.yaml (ClusterIP 8080), pvc.yaml (RWO), configmap.yaml
  (MINTMORY_* + OTel env, keys only when set), secret.yaml (api keys, only if set),
  auth-secret.yaml (htpasswd via Sprig, only when basicAuth.enabled and no
  existingSecret), ingress.yaml (only when enabled; basic-auth annotations),
  backup-cronjob.yaml (only when backup.enabled), NOTES.txt.
- [ ] Guardrails: no template ever renders replicas>1 or RollingUpdate; PVC RWO;
  document block-not-NFS + single-writer in README/NOTES.

## 3. Two tiers
- [ ] Simple: Service + PVC + probes, no ingress/auth, OTel off.
- [ ] Advanced: ingress + ingress-nginx basic-auth annotations + htpasswd Secret,
  OTLP endpoint (BYO), resource limits, optional backup (off by default, limitation
  documented honestly).

## 4. CI (deploy-validate)
- [ ] Add helm lint + helm template (both tiers) + `kubectl apply --dry-run=client`
  + `docker build --build-arg VARIANT=light` (build-smoke, NO publish) to ci.yml.

## 5. Docs
- [ ] `deploy/helm/mintmory/README.md` + a top-level deploy note: how to install
  simple vs advanced, the SQLite single-replica constraints, backup guidance.

## 6. Gates
- [ ] `helm lint` clean; `helm template` both tiers render; `kubectl --dry-run=client`
  accepts output; `docker build` (light) succeeds.
- [ ] Existing Python gates unchanged/green.
- [ ] `openspec validate add-helm-chart --strict`.
