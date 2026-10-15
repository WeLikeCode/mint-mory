# Change: Container images + Helm chart for Kubernetes deployment (MM-43)

## Why

MintMory has no containerization or deployment artifacts (a Fable audit confirmed:
no Dockerfile, compose, k8s/, or helm/ anywhere). MM-42 added the enabling code
(`/healthz`, `/readyz`, OTel activation + OTLP metrics). This change ships the
packaging so MintMory can be deployed to a Kubernetes cluster, made network-
accessible, fronted with basic auth, health-checked, and observed — with a
**simple** and an **advanced** tier.

## What changes

**Container images (`Dockerfile`, `.dockerignore`):**
- Multi-stage, `python:3.12-slim`, uv-based (`uv sync --package mintmory-api`),
  **non-root** user, `/data` volume, `EXPOSE 8080`. Prod entrypoint runs
  `uvicorn mintmory.api.app:app --host 0.0.0.0 --port 8080 --workers 1` (one worker
  — SQLite single-writer; NOT the dev `main()` with `reload=True`).
- Build ARG `VARIANT`: **`light`** (default, ~700 MB — `[otel]` extra, hashing
  embedder, no torch) and **`full`** (adds the `[local]` sentence-transformers/torch
  extra, ~2 GB). The `[cochange]`/`[local]` extras are lazy-imported and degrade
  gracefully, so `light` is fully functional.

**Helm chart (`deploy/helm/mintmory/`)** — one values-driven chart, two tiers:
- Templates: `Deployment` (**`replicas: 1`**, **`strategy: Recreate`**, 1 uvicorn
  worker), `Service` (ClusterIP :8080), `PersistentVolumeClaim`
  (**`ReadWriteOnce`**, mounted `/data`, `MINTMORY_DB=/data/memories.db`),
  `ConfigMap` (`MINTMORY_*` + OTel env), `Secret` (LLM/embed/vision API keys),
  optional `Ingress`, `_helpers.tpl`, `NOTES.txt`, `values.schema.json`.
- **Probes**: liveness → `GET /healthz`, readiness → `GET /readyz`.
- **SQLite guardrails** baked in and documented: single replica (no HPA),
  `Recreate` rollout (RollingUpdate would double-write the WAL), one worker,
  ReadWriteOnce block storage (not NFS).
- **Simple tier** (`values-simple.yaml`): Deployment + Service + PVC + probes; no
  ingress/auth; OTel off; modest resources. Reachable via the Service / port-forward.
- **Advanced tier** (`values-advanced.yaml`): adds an `Ingress` with **basic auth
  via ingress-nginx annotations** (`nginx.ingress.kubernetes.io/auth-type: basic`,
  `auth-secret`, `auth-realm`) + an htpasswd `Secret` the chart generates from
  values (Sprig `htpasswd`) or references an existing one; optional TLS; OTel on with
  `OTEL_EXPORTER_OTLP_ENDPOINT` pointing at a **bring-your-own** collector; API-key
  Secret populated; CPU/memory requests+limits; optional backup `CronJob`
  (`sqlite3 .backup` of the WAL triple to a second volume — off by default).

**CI (`.github/workflows/ci.yml`):** add a lightweight deploy-validation job —
`helm lint`, `helm template` for both tiers, `kubectl apply --dry-run=client` on the
rendered manifests, and a `docker build` of the **light** image (build-smoke only,
**no registry publish** — the full/torch build is documented, not built in CI due to
size).

## Impact

- Affected specs: **deployment** (ADDED: container image + Helm chart requirements).
- New files: `Dockerfile`, `.dockerignore`, `deploy/helm/mintmory/**`, a deploy
  README; CI job additions. No application code changes (MM-42 covered those).
- Migrations: none. Nothing in the running app changes; this is packaging.
- Explicit non-goals: horizontal scaling / multi-writer (needs a Postgres/libsql
  backend — future); GHCR image publishing (deferred; build-smoke only); MCP-SSE
  exposure (API-only v1); oauth2-proxy/SSO (basic auth is the chosen gate).
