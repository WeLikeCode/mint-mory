# Design: Container images + Helm chart (MM-43)

Packaging only — no app code changes (MM-42 added `/healthz`, `/readyz`, OTel).
Validated with `helm lint` + `helm template` + `kubectl apply --dry-run=client` +
`docker build` (light). No live cluster available → no in-cluster smoke.

## 1. Dockerfile (multi-stage, uv, non-root)

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ARG VARIANT=light           # light | full
ENV UV_LINK_MODE=copy PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
# light: [otel]; full: also [local] (sentence-transformers + torch)
RUN if [ "$VARIANT" = "full" ]; then \
      uv sync --frozen --package mintmory-api --extra otel --extra local ; \
    else \
      uv sync --frozen --package mintmory-api --extra otel ; \
    fi
# non-root
RUN useradd -u 10001 -m app && mkdir -p /data && chown app:app /data
USER app
VOLUME ["/data"]
ENV MINTMORY_DB=/data/memories.db
EXPOSE 8080
# prod: 1 worker (SQLite single-writer), no --reload
CMD ["uv","run","--no-sync","uvicorn","mintmory.api.app:app","--host","0.0.0.0","--port","8080","--workers","1"]
```
`.dockerignore`: `.venv`, `.git`, `**/__pycache__`, `.mypy_cache`, `.ruff_cache`,
`.pytest_cache`, `htmlcov`, `docs/superpowers`, `*.db*`, `.firecrawl`, tests are
kept out of the runtime image (copy only packages needed — or keep it simple and
copy all `packages` but rely on `uv sync --package mintmory-api` to install just the
API + its deps). Verify the exact copy set builds; adjust if a package is missing.

**Image size note:** `light` ≈ 700 MB (numpy + fastapi + uvicorn + otel + the
workspace; measured 716 MB); `full` adds torch (~2 GB). CI builds only `light`.

## 2. Helm chart layout — `deploy/helm/mintmory/`

```
Chart.yaml            # apiVersion v2, appVersion "0.1.0", type application
values.yaml           # documented defaults (== simple tier)
values-simple.yaml    # example override (thin)
values-advanced.yaml  # example override: ingress+auth+otel+resources+backup
values.schema.json    # JSON schema for values (helm validates on install)
templates/
  _helpers.tpl        # name/labels/selectorLabels/htpasswd helpers
  deployment.yaml
  service.yaml
  pvc.yaml
  configmap.yaml      # MINTMORY_* + OTel env (non-secret)
  secret.yaml         # api keys (only rendered if any provided)
  auth-secret.yaml    # htpasswd Secret (only when ingress.basicAuth.enabled)
  ingress.yaml        # only when ingress.enabled
  backup-cronjob.yaml # only when backup.enabled
  NOTES.txt
README.md
```

### Deployment (the SQLite guardrails are non-negotiable defaults)
- `spec.replicas: 1` (hardcoded to `{{ .Values.replicaCount | default 1 }}` but the
  README + a values.schema `maximum: 1` forbid >1; the app cannot multi-write).
- `strategy: { type: Recreate }` (fixed; RollingUpdate would run two writers).
- container port 8080; `MINTMORY_DB=/data/memories.db`; volumeMount `/data` ← PVC.
- `livenessProbe: httpGet /healthz :8080` (initialDelay ~5s, period 10s),
  `readinessProbe: httpGet /readyz :8080` (period 10s, failureThreshold 3).
- envFrom: the ConfigMap; env: secret keys via `secretKeyRef` (only when set).
- resources from values (unset in simple; set in advanced).
- securityContext: runAsNonRoot, runAsUser 10001, readOnlyRootFilesystem where
  feasible (writable /data + /tmp).

### PVC
- `accessModes: [ReadWriteOnce]`, `resources.requests.storage` (default 1Gi),
  optional `storageClassName` (values). Documented: must be **block** storage, not
  NFS (SQLite WAL mmap).

### ConfigMap / Secret
- ConfigMap keys: `MINTMORY_DB`, `MINTMORY_SQLITE_BUSY_TIMEOUT_MS`,
  `MINTMORY_EMBED_*` (non-key), `MINTMORY_LLM_PROVIDER/BASE_URL/MODEL/…`,
  `MINTMORY_OTEL_ENABLED/EXPORTER/SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT` —
  each rendered only when set in values (`config:` map passthrough).
- Secret (Opaque, only if any provided): `MINTMORY_LLM_API_KEY`,
  `MINTMORY_EMBED_API_KEY`, `MINTMORY_VISION_API_KEY`.

### Ingress + basic auth (advanced)
- `ingress.enabled` → Ingress with `ingressClassName` (default `nginx`), host, path
  `/`, backend the Service :8080; optional `tls`.
- `ingress.basicAuth.enabled` → annotations
  `nginx.ingress.kubernetes.io/auth-type: basic`,
  `auth-secret: {{ include "mintmory.fullname" . }}-basic-auth`,
  `auth-realm: "MintMory"`; and `auth-secret.yaml` renders an Opaque Secret with key
  `auth` = `{{ htpasswd .Values.ingress.basicAuth.username .Values.ingress.basicAuth.password }}`
  (Sprig). If `existingSecret` is set, reference it instead and render nothing.
  Health paths are NOT special-cased (probes hit the pod directly, not via ingress).

### OTel (advanced, BYO collector)
- `otel.enabled` sets ConfigMap `MINTMORY_OTEL_ENABLED=true`,
  `MINTMORY_OTEL_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_ENDPOINT={{ .Values.otel.endpoint }}`.
  No collector bundled.

### Backup CronJob (advanced, off by default)
- `backup.enabled` → CronJob (schedule from values) running the image with
  `sqlite3 /data/memories.db ".backup /backup/memories-$(date).db"` to a second PVC
  (or an object-store upload sidecar — out of scope; PVC target only). Mounts the
  SAME data PVC read-only? No — `.backup` needs a live read; mount RWO won't co-mount
  with the running pod. Document that the CronJob and the app can't both hold the RWO
  PVC → the pragmatic v1 backup is an in-pod sidecar `CronJob`-style loop OR a manual
  `kubectl exec … sqlite3 .backup`. Keep `backup.enabled=false` default and document
  the limitation honestly rather than shipping a broken CronJob.

## 3. values.yaml (shape)

```yaml
image: { repository: mintmory, tag: "", pullPolicy: IfNotPresent }  # tag "" -> appVersion
replicaCount: 1
persistence: { enabled: true, size: 1Gi, storageClassName: "", accessMode: ReadWriteOnce }
resources: {}                      # simple: unset; advanced: requests/limits
config: {}                         # MINTMORY_* non-secret passthrough
secrets: {}                        # MINTMORY_*_API_KEY -> Secret
service: { type: ClusterIP, port: 8080 }
ingress:
  enabled: false
  className: nginx
  host: mintmory.local
  tls: []
  basicAuth: { enabled: false, username: "", password: "", existingSecret: "" }
otel: { enabled: false, endpoint: "" }
backup: { enabled: false, schedule: "0 3 * * *", size: 1Gi }
probes: { liveness: /healthz, readiness: /readyz }
```
`values.schema.json` enforces `replicaCount` ≤ 1 and required shapes.

## 4. CI (deploy-validate job)

Add to `.github/workflows/ci.yml` a job (or steps) that:
- `helm lint deploy/helm/mintmory`
- `helm template t deploy/helm/mintmory` and `... -f values-advanced.yaml` (both
  render without error)
- `helm template ... | kubectl apply --dry-run=client -f -` (schema-valid manifests;
  kubectl needs no cluster for client dry-run)
- `docker build --build-arg VARIANT=light -t mintmory:ci .` (build-smoke; no push)
The full/torch build is NOT run in CI (size/time); documented in the README.

## 5. Testing / validation (local, before commit)
- `helm lint` clean; `helm template` renders both tiers; `kubectl --dry-run=client`
  accepts the output; `yamllint` on the chart (advisory).
- `docker build --build-arg VARIANT=light` succeeds and `docker run` + curl
  `/healthz` returns 200 (a real container smoke, if the daemon is available).
- Confirm no template ever emits `replicas > 1` or `strategy: RollingUpdate`.

## 6. Gates

Existing Python gates stay green (this change touches no Python). Plus: `helm lint`,
`helm template` (both tiers), `kubectl --dry-run=client`, `docker build` (light),
`openspec validate add-helm-chart --strict`.
