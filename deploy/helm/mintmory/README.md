# MintMory Helm chart

Deploys the MintMory REST API to Kubernetes. The default `image.repository` is
`ghcr.io/welikecode/mint-mory`, the **light** image CI publishes to GHCR (MM-44);
override it to build/mirror your own from the repo-root `Dockerfile`.

## Pulling the image (GHCR)

CI publishes the light image on pushes to the default branch (tags `main`,
`sha-<sha>`, and `latest`) and on release tags `vX.Y.Z` as the image tag `X.Y.Z`
(e.g. `0.1.0`, the chart's default `appVersion`). `latest` tracks only the default
branch. It uses the built-in `GITHUB_TOKEN` with `packages: write` — no extra
registry secret.

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

## Storage modes (read this first)

The chart supports two mutually-exclusive storage backends, selected via
`storage.backend`. The value is validated by `values.schema.json` — the schema
applies **conditional guardrails** using JSON Schema `if/then/else` so that the
SQLite constraints are strictly enforced in SQLite mode and relaxed only when the
backend is Postgres.

### SQLite mode (default — `storage.backend: sqlite`)

MintMory's store is a **single SQLite file** (`/data/memories.db` + its WAL/SHM
sidecars). SQLite is a **single writer**. This chart therefore hard-codes a
single-writer-safe topology that you cannot override in sqlite mode — the schema
hard-rejects any attempt:

| Concern            | Setting                          | Why                                            |
| ------------------ | -------------------------------- | ---------------------------------------------- |
| Replicas           | `1` (schema `maximum: 1`)        | Two pods writing the same file corrupt the WAL |
| Rollout            | `strategy: Recreate`             | RollingUpdate briefly runs two writers         |
| Workers            | 1 uvicorn worker (in the image)  | Multiple workers = multiple writers            |
| Volume             | `ReadWriteOnce`, **block** storage | WAL uses `mmap`; NFS is unsafe               |
| Horizontal scaling | not supported in SQLite mode     | Switch to Postgres for real HA                 |

The `min()` guard in `deployment.yaml` is a belt-and-braces second lock: even if
schema validation were somehow bypassed, the template clamps replicas to 1.

### Postgres mode (`storage.backend: postgres`)

With an external PostgreSQL database the API pods are **stateless** — they carry no
local data. The chart's HA constraints relax conditionally:

| Concern            | SQLite mode                  | Postgres mode                                  |
| ------------------ | ---------------------------- | ---------------------------------------------- |
| Replicas           | 1 (schema `maximum: 1`)      | 1–20 (schema relaxes; set as desired or use HPA) |
| Rollout            | `Recreate`                   | `RollingUpdate` (maxUnavailable 0, maxSurge 1) |
| PVC                | `ReadWriteOnce`, required    | None — `persistence.enabled` is ignored        |
| `/readyz`          | trivial DB file check        | Real PG ping via pool; blip → 503, not crash-loop |
| PDB                | not rendered (pointless at 1) | `PodDisruptionBudget` (maxUnavailable 1)       |
| Pod anti-affinity  | not rendered                 | Prefer spreading across nodes (soft, overridable) |

**Schema self-creation:** at pod startup the `PostgresBackend.initialise()` runs
runtime DDL (CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS) under a
`pg_advisory_xact_lock`. This is race-safe across N replicas starting simultaneously
— only one lock-holder runs DDL; the others wait, then see the schema already present
and proceed. **No pre-deploy migration Job is required or shipped.** The first replica
to start creates the schema; subsequent replicas (or restarts) are no-ops.

**BYO Postgres:** the chart never vendors a StatefulSet Postgres or a Postgres operator.
You bring your own managed Postgres (RDS, CloudSQL, Azure Database, self-hosted
[CloudNativePG](https://cloudnative-pg.io/), etc.) and provide the DSN. The chart
creates a Secret from `storage.postgres.dsn`, or you reference an operator-managed
Secret via `storage.postgres.existingSecret`. **The DSN is never in a ConfigMap or
plain env.**

## Tiers

### Simple (SQLite)

Deployment + Service + PVC + health probes. No ingress, no auth, OTel off.

```sh
helm install mm deploy/helm/mintmory -f deploy/helm/mintmory/values-simple.yaml
kubectl port-forward svc/mm-mintmory 8080:8080
curl -sf http://localhost:8080/healthz   # {"status":"ok"}
```

### Advanced (SQLite)

Adds an ingress-nginx Ingress with HTTP basic auth (`auth.mode: basic`,
chart-generated htpasswd Secret), OpenTelemetry export to a bring-your-own OTLP
collector, API-key Secret, and resource requests/limits. Still single-replica,
Recreate, RWO — the SQLite guardrails are not overridable.

```sh
helm install mm deploy/helm/mintmory -f deploy/helm/mintmory/values-advanced.yaml
```

### Postgres (HA)

Stateless pods, external Postgres, N replicas. See `values-postgres.yaml`.

```sh
# Pass the real DSN at install time; do NOT commit it in a values file.
helm install mm deploy/helm/mintmory \
  -f deploy/helm/mintmory/values-postgres.yaml \
  --set-string storage.postgres.dsn="postgresql://mintmory:s3cr3t@pg-host:5432/mintmory"
```

Or reference an existing Secret (e.g. from CloudNativePG):

```sh
helm install mm deploy/helm/mintmory \
  -f deploy/helm/mintmory/values-postgres.yaml \
  --set storage.postgres.existingSecret=cnpg-mintmory-app \
  --set storage.postgres.existingSecretKey=uri \
  --set storage.postgres.dsn=""   # clear the placeholder
```

Keep real secrets out of git — override with `--set-string storage.postgres.dsn=...`
or a private values file that is never committed.

## Key values

| Key                                | Default          | Notes                                                    |
| ---------------------------------- | ---------------- | -------------------------------------------------------- |
| `storage.backend`                  | `sqlite`         | `sqlite` or `postgres` — controls topology and schema guardrails. |
| `storage.postgres.dsn`             | `""`             | libpq DSN — stored in a Secret. Set this OR existingSecret. |
| `storage.postgres.existingSecret`  | `""`             | Reference an operator-managed Secret containing the DSN.  |
| `storage.postgres.existingSecretKey` | `"dsn"`        | Key inside existingSecret that holds the DSN.             |
| `storage.postgres.pool.min/max`    | `2` / `10`       | psycopg3 connection pool bounds.                         |
| `replicaCount`                     | `1`              | SQLite: schema-enforced maximum 1. Postgres: up to 20.   |
| `image.repository` / `image.tag`  | `mintmory` / ""  | Empty tag → `Chart.appVersion`.                          |
| `persistence.size`                 | `1Gi`            | PVC size (SQLite mode only).                             |
| `persistence.storageClassName`     | `""`             | Block storage class; empty = cluster default.            |
| `persistence.existingClaim`        | `""`             | Reuse an existing PVC instead of creating one.           |
| `resources`                        | `{}`             | Requests/limits (set in advanced/postgres tiers).        |
| `config`                           | `{}`             | Non-secret `MINTMORY_*` → ConfigMap.                     |
| `secrets`                          | `{}`             | API keys → Secret (only if any non-empty).               |
| `otel.enabled` / `otel.endpoint`   | `false` / `""`   | OTLP export to a BYO collector.                          |
| `ingress.enabled`                  | `false`          | Advanced/Postgres tier.                                  |
| `auth.mode`                        | `none`           | `none` \| `basic` \| `oauth2proxy` (exclusive).          |
| `auth.basic.existingSecret`        | `""`             | Reference an htpasswd Secret instead of generating.      |
| `auth.oauth2proxy.oidcIssuerUrl`   | `""`             | BYO OIDC issuer (required for oauth2proxy).              |

### Config vs secrets

Non-secret settings go in `config` (rendered into a ConfigMap, one key each, only
when set). API keys go in `secrets` and are rendered into an Opaque Secret **only
when at least one is non-empty**. The Postgres DSN goes into a dedicated Secret
(never in `config`). With everything empty the pod still runs — MintMory defaults to
a fully offline configuration.

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

The oauth2-proxy pods carry their own selector label
`app.kubernetes.io/name: <chart name>-oauth2-proxy`, so the application Service
and PodDisruptionBudget never select them. A release installed earlier in
`oauth2proxy` mode must delete its `<release>-mintmory-oauth2-proxy` Deployment
before `helm upgrade`: a Deployment selector is immutable, so the changed labels
of the oauth2-proxy Deployment cannot be applied in place:

```sh
kubectl delete deployment mm-mintmory-oauth2-proxy
helm upgrade mm deploy/helm/mintmory -f your-values.yaml
```

## Backups

### SQLite mode

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

### Postgres mode

Backups are the responsibility of your **external database**, not this chart. Use
your Postgres operator's built-in backup:

- **CloudNativePG**: configure `Cluster.spec.backup` with a barman object store.
- **Managed PG** (RDS, CloudSQL, Azure Database): use the provider's automated snapshot.
- **Self-hosted**: `pg_dump`, WAL archiving, pgBackRest — standard Postgres tooling.

No in-cluster chart hook is needed or provided. The schema is small and recreates
automatically at startup, so a plain `pg_dump | psql` restore is sufficient for
disaster recovery.

## Runbooks

### Switch from SQLite to Postgres (one-time migration)

1. Scale down the SQLite deployment to zero (ensures a clean SQLite file):
   ```sh
   kubectl scale deploy/mm-mintmory --replicas=0
   ```
2. Copy the SQLite file locally:
   ```sh
   POD=$(kubectl get pod -l app.kubernetes.io/instance=mm -o name | head -1)
   kubectl cp "${POD#pod/}:/data/memories.db" ./memories.db
   ```
3. Run the migration CLI (on a machine with access to both the file and PG):
   ```sh
   mintmory migrate-storage \
     --from sqlite:./memories.db \
     --to   postgres://mintmory:s3cr3t@pg-host:5432/mintmory
   ```
   This streams rows in FK order, converts types (bool/timestamp/json/embeddings),
   and prints row-count + checksum verification at the end.
4. Upgrade the Helm release to postgres mode:
   ```sh
   helm upgrade mm deploy/helm/mintmory \
     -f deploy/helm/mintmory/values-postgres.yaml \
     --set-string storage.postgres.dsn="postgresql://mintmory:s3cr3t@pg-host:5432/mintmory"
   ```
5. Verify:
   ```sh
   kubectl rollout status deploy/mm-mintmory
   curl -sf https://mintmory.example.com/healthz
   curl -sf https://mintmory.example.com/readyz
   ```

**DSN safety:** pass the DSN via `--set-string` at install/upgrade time, or store it
in a private values file that is **never committed to git**. The chart creates an
Opaque Secret from it; or use `storage.postgres.existingSecret` to reference an
operator-managed Secret (e.g. CNPG's app Secret) — in that case the chart emits no
Secret of its own.

### CloudNativePG recipe

CloudNativePG (CNPG) manages the Postgres cluster lifecycle and creates a `<cluster>-app`
Secret with keys `uri` (libpq URI), `user`, `password`, etc. Reference it:

```sh
helm install mm deploy/helm/mintmory \
  -f deploy/helm/mintmory/values-postgres.yaml \
  --set storage.postgres.existingSecret=mintmory-app \
  --set storage.postgres.existingSecretKey=uri \
  --set storage.postgres.dsn=""
```

The chart's Deployment `secretKeyRef` points at `mintmory-app` and key `uri` — no
chart-owned Secret is created. CNPG rotates credentials in the Secret automatically;
the pods pick up the new DSN on restart (or immediately if the app re-reads the env
at connection time).

## Validate locally (no cluster needed)

```sh
helm lint deploy/helm/mintmory

# sqlite (default) tier — guardrails must hold:
helm template t deploy/helm/mintmory | kubeconform -strict -summary -kubernetes-version 1.29.0 -
helm template t deploy/helm/mintmory -f deploy/helm/mintmory/values-advanced.yaml \
  | kubeconform -strict -summary -kubernetes-version 1.29.0 -

# postgres tier — HA mode:
helm template t deploy/helm/mintmory -f deploy/helm/mintmory/values-postgres.yaml \
  | kubeconform -strict -summary -kubernetes-version 1.29.0 -

# Guardrail negative test (MUST fail — schema rejects replicaCount=2 in sqlite mode):
helm template t deploy/helm/mintmory --set storage.backend=sqlite --set replicaCount=2

# Postgres positive test (MUST succeed — schema allows replicaCount=3 in postgres mode):
helm template t deploy/helm/mintmory \
  --set storage.backend=postgres \
  --set-string storage.postgres.dsn="postgresql://u:p@host:5432/db" \
  --set replicaCount=3
```

## Image variants

The `Dockerfile` builds a `light` (default, `[otel]`, ~700 MB — numpy + FastAPI +
uvicorn + OTel + the workspace, no torch) or `full` (`[otel]` + `[local]` =
sentence-transformers/torch, ~2 GB) image via `--build-arg VARIANT=`. CI
build-smokes only `light`.
