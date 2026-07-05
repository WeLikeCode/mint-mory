# MintMory Helm chart

Deploys the MintMory REST API to Kubernetes. The default `image.repository` is
`ghcr.io/welikecode/mint-mory`, the **light** image CI publishes to GHCR (MM-44);
override it to build/mirror your own from the repo-root `Dockerfile`.

## Pulling the image (GHCR)

CI publishes the light image on pushes to the default branch (tags `main`,
`sha-<sha>`, and `latest`) and on release tags (the version, e.g.
`v0.1.0-beta.2`). It uses the built-in `GITHUB_TOKEN` with `packages: write` — no
extra registry secret.

```sh
docker pull ghcr.io/welikecode/mint-mory:latest
# helm install pulls it automatically (image.repository default). Private package?
# create a docker-registry pull secret and set imagePullSecrets.
```

One-time org setting: the **first** publish creates the GHCR package via
`GITHUB_TOKEN`. If the org restricts token-created packages, enable
*Settings → Packages → "Allow GITHUB_TOKEN to create and publish packages"* (or
pre-create the package and grant the repo write access). This is an org/repo
setting, not a code change. The **full/torch** image (~2 GB) is never
auto-published — build it on demand with `--build-arg VARIANT=full`.

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

Adds an ingress-nginx Ingress with HTTP basic auth (`auth.mode: basic`,
chart-generated htpasswd Secret), OpenTelemetry export to a bring-your-own OTLP
collector, API-key Secret, and resource requests/limits.

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
| `auth.mode`                      | `none`           | `none` \| `basic` \| `oauth2proxy` (exclusive).  |
| `auth.basic.existingSecret`      | `""`             | Reference an htpasswd Secret instead of generating. |
| `auth.oauth2proxy.oidcIssuerUrl` | `""`             | BYO OIDC issuer (required for oauth2proxy).       |

### Config vs secrets

Non-secret settings go in `config` (rendered into a ConfigMap, one key each, only
when set). API keys go in `secrets` and are rendered into an Opaque Secret **only
when at least one is non-empty**. With everything empty the pod still runs —
MintMory defaults to a fully offline configuration.

## Ingress authentication (`auth.mode`)

The app has **no built-in auth** — the gate is entirely at the ingress. Pick one
mutually-exclusive mode (default `none`). Health probes are unaffected: the
kubelet hits the pod directly, not through the ingress, so `/healthz`/`/readyz`
stay reachable under any mode.

### `none` (default)

No auth annotations. Reach the API via `kubectl port-forward` or a trusted
network. Do not expose an unauthenticated ingress to the internet.

### `basic`

```sh
helm install mm deploy/helm/mintmory --set ingress.enabled=true \
  --set auth.mode=basic --set auth.basic.username=admin --set-string auth.basic.password=...
```

Adds the ingress-nginx annotations (`auth-type: basic`, `auth-secret`,
`auth-realm`) and generates an htpasswd Secret (key `auth`) from
`auth.basic.username`/`password` via Sprig's `htpasswd`. Set
`auth.basic.existingSecret` to reference a Secret you manage yourself (nothing is
generated then).

### `oauth2proxy` (OIDC SSO)

```sh
helm install mm deploy/helm/mintmory --set ingress.enabled=true \
  --set auth.mode=oauth2proxy \
  --set auth.oauth2proxy.oidcIssuerUrl=https://accounts.google.com \
  --set auth.oauth2proxy.clientId=... --set-string auth.oauth2proxy.clientSecret=...
```

Deploys an [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/)
Deployment + ClusterIP Service (`:4180`) + Secret, and wires the ingress
external-auth annotations (`auth-url` → oauth2-proxy `/oauth2/auth`,
`auth-signin` → `/oauth2/start`) plus an extra `/oauth2` ingress path so the
sign-in/callback flow works on the same host. You **bring your own OIDC
provider**: set the issuer URL, client id, and client secret. The cookie secret
is chart-generated (`randAlphaNum 32 | b64enc`) unless you set
`auth.oauth2proxy.cookieSecret`. MintMory is single-tenant — SSO gates *access*,
it is not per-user tenancy.

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
