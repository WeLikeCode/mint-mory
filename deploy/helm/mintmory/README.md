# MintMory Helm chart

Deploys the MintMory REST API to Kubernetes. Packaging only (MM-43) — the app
image is built from the repo-root `Dockerfile`.

## The SQLite constraint (read this first)

MintMory's store is a **single SQLite file** (`/data/memories.db` + its WAL/SHM
sidecars). SQLite is a **single writer**. This chart therefore hard-codes a
single-writer-safe topology that you should not try to override:

| Concern            | Setting                          | Why                                            |
| ------------------ | -------------------------------- | ---------------------------------------------- |
| Replicas           | `1` (schema `maximum: 1`)        | Two pods writing the same file corrupt the WAL |
| Rollout            | `strategy: Recreate`             | RollingUpdate briefly runs two writers         |
| Workers            | 1 uvicorn worker (in the image)  | Multiple workers = multiple writers            |
| Volume             | `ReadWriteOnce`, **block** storage | WAL uses `mmap`; NFS is unsafe               |
| Horizontal scaling | not supported                    | Needs a Postgres/libsql backend (future work)  |

## Tiers

### Simple

Deployment + Service + PVC + health probes. No ingress, no auth, OTel off.

```sh
helm install mm deploy/helm/mintmory -f deploy/helm/mintmory/values-simple.yaml
kubectl port-forward svc/mm-mintmory 8080:8080
curl -sf http://localhost:8080/healthz   # {"status":"ok"}
```

### Advanced

Adds an ingress-nginx Ingress with HTTP basic auth (chart-generated htpasswd
Secret), OpenTelemetry export to a bring-your-own OTLP collector, API-key Secret,
and resource requests/limits.

```sh
helm install mm deploy/helm/mintmory -f deploy/helm/mintmory/values-advanced.yaml
```

Keep real secrets out of git — override with `--set-string secrets.MINTMORY_LLM_API_KEY=...`
or a private values file.

## Key values

| Key                              | Default          | Notes                                            |
| -------------------------------- | ---------------- | ------------------------------------------------ |
| `replicaCount`                   | `1`              | Must stay 1 (schema-enforced).                   |
| `image.repository` / `image.tag` | `mintmory` / ""  | Empty tag -> `Chart.appVersion`.                 |
| `persistence.size`               | `1Gi`            | PVC size.                                        |
| `persistence.storageClassName`   | `""`             | Block storage class; empty = cluster default.    |
| `persistence.existingClaim`      | `""`             | Reuse an existing PVC instead of creating one.   |
| `resources`                      | `{}`             | Requests/limits (set in advanced).               |
| `config`                         | `{}`             | Non-secret `MINTMORY_*` -> ConfigMap.            |
| `secrets`                        | `{}`             | API keys -> Secret (only if any non-empty).      |
| `otel.enabled` / `otel.endpoint` | `false` / `""`   | OTLP export to a BYO collector.                  |
| `ingress.enabled`                | `false`          | Advanced tier.                                   |
| `ingress.basicAuth.enabled`      | `false`          | ingress-nginx basic auth.                        |
| `ingress.basicAuth.existingSecret` | `""`           | Reference an htpasswd Secret instead of generating. |

### Config vs secrets

Non-secret settings go in `config` (rendered into a ConfigMap, one key each, only
when set). API keys go in `secrets` and are rendered into an Opaque Secret **only
when at least one is non-empty**. With everything empty the pod still runs —
MintMory defaults to a fully offline configuration.

## Basic auth

`ingress.basicAuth.enabled` adds the ingress-nginx annotations
(`auth-type: basic`, `auth-secret`, `auth-realm`) and generates an htpasswd Secret
(key `auth`) from `username`/`password` via Sprig's `htpasswd`. Set
`ingress.basicAuth.existingSecret` to reference a Secret you manage yourself
(nothing is generated then). The app has no built-in auth — the gate is entirely
at the ingress.

## Backups

An automated backup CronJob is **intentionally not shipped**. A `ReadWriteOnce`
PVC can only be mounted by one pod at a time, so a CronJob pod would sit `Pending`
forever waiting for the volume the app already holds — a broken, deadlocking
design. Back up manually against the running pod instead:

The runtime image is `python:3.12-slim` and does **not** ship the `sqlite3` CLI, so
back up via Python's stdlib online-backup API (no extra package, consistent snapshot
while the DB stays live):

```sh
kubectl exec deploy/mm-mintmory -- python -c \
  "import sqlite3; s=sqlite3.connect('/data/memories.db'); d=sqlite3.connect('/tmp/backup.db'); s.backup(d); d.close(); s.close()"
POD=$(kubectl get pod -l app.kubernetes.io/instance=mm -o name | head -1)
kubectl cp "${POD#pod/}:/tmp/backup.db" ./backup-$(date +%F).db
```

`Connection.backup()` is SQLite's online backup — safe against the live WAL. For
scheduled backups, run this from an external job (CI, a controller with `exec`
rights) rather than an in-cluster CronJob competing for the RWO volume.

## Validate locally (no cluster needed)

```sh
helm lint deploy/helm/mintmory
# kubeconform validates rendered manifests offline (cluster-less `kubectl apply
# --dry-run=client` still needs a reachable API server); this is what CI runs.
helm template t deploy/helm/mintmory | kubeconform -strict -summary -
helm template t deploy/helm/mintmory -f deploy/helm/mintmory/values-advanced.yaml \
  | kubeconform -strict -summary -
```

## Image variants

The `Dockerfile` builds a `light` (default, `[otel]`, ~700 MB — numpy + FastAPI +
uvicorn + OTel + the workspace, no torch) or `full` (`[otel]` + `[local]` =
sentence-transformers/torch, ~2 GB) image via `--build-arg VARIANT=`. CI
build-smokes only `light`.
