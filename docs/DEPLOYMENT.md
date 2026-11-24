# Save Flight — Deployment Guide

Two deployment paths exist. Both have been actually run and verified end-to-end during this project (not just written and assumed to work) — see `docs/TESTING_VALIDATION.md` for the specific bugs each run surfaced and fixed.

## Path 1 — Full Docker Compose stack (the target architecture)

**Prerequisites:** Docker Desktop running, Git Bash (Windows) or a POSIX shell.

```bash
cp .env.example .env                              # then edit DB_PASSWORD, JWT_SECRET, DATA_ENCRYPTION_KEY, GRAFANA_PASSWORD
bash infrastructure/nginx/generate-dev-cert.sh     # self-signed TLS cert for local HTTPS
docker compose up --build
```

> Windows Git Bash: run the cert script as `MSYS_NO_PATHCONV=1 bash infrastructure/nginx/generate-dev-cert.sh` so Git Bash doesn't mangle the `-subj` argument's path-like syntax.

This starts 6 containers on an isolated bridge network (`secure_network`, `172.20.0.0/16`):

| Service | Purpose | Host port |
|---|---|---|
| `postgres` | Primary database | none (internal only) |
| `postgres_exporter` | Metrics for Grafana | none (internal only) |
| `backend` | FastAPI app | `8000` |
| `frontend` | React SPA (nginx-served static build) | `3000` |
| `nginx` | TLS edge, rate limiting, security headers | `80`, `443` |
| `prometheus` | Metrics store | `9090` |
| `grafana` | Dashboards | `3001` |

- App via the hardened edge: `https://localhost`
- Grafana: `http://localhost:3001` (`admin` / `$GRAFANA_PASSWORD`)
- Prometheus: `http://localhost:9090`

**Seed data:**
```bash
docker compose exec backend python -m src.init_db          # 1 passenger + 1 staff per role
docker compose exec backend python -m src.seed_demo_data   # 10 flights / 25 passengers / 40 bookings / 15 check-ins
```

**Backups:**
```bash
DB_USER=... DB_NAME=... BACKUP_PASSWORD=... bash infrastructure/backup/backup-postgres.sh
DB_USER=... DB_NAME=... BACKUP_PASSWORD=... bash infrastructure/backup/restore-postgres.sh <file.sql.gz.enc>
```
Schedule `backup-postgres.sh` via cron/systemd-timer on the Docker host for daily backups (not automated inside `docker-compose.yml` itself — the script is designed to be invoked externally against the running `postgres` container).

**Host firewall** (only relevant on a bare-metal/VM host — Docker's own network segmentation already isolates the containers from each other):
```bash
sudo bash infrastructure/firewall/ufw_rules.sh
```
Denies all inbound by default, explicitly allows SSH (rate-limited), HTTP/HTTPS, and Postgres only from localhost.

**What was actually found running this stack for real** (not just reviewing the YAML): the frontend and backend Dockerfile `HEALTHCHECK` directives originally used `http://localhost:...`, which resolves to `::1` first under Alpine/musl — but nginx and Prometheus/Grafana only bind IPv4, so every healthcheck failed despite the app serving traffic correctly. Fixed by hardcoding `127.0.0.1`. The `prometheus` service also had no `ports:` mapping at all in an earlier revision (unreachable from the host despite internal scraping working) — fixed by adding `9090:9090`. `seed_demo_data.py` crashed under the backend's `read_only: true` filesystem when it tried to write a reference JSON file outside `/tmp` — fixed with a fallback path.

## Path 2 — Combined single-container deployment (Railway)

Used specifically because the available Railway account's free-tier service quota couldn't fit 5+ separate services (Postgres + backend + frontend + reverse proxy + metrics). `Dockerfile.railway` builds the React app and serves its static output from the same FastAPI process that serves the API, so the whole product fits in one deployable unit.

```bash
railway up          # from repo root; builds Dockerfile.railway, deploys to the linked service
```

Environment variables (set once via `railway variables set` or the dashboard, not committed to the repo): `DATABASE_URL` (Railway-provisioned Postgres), `JWT_SECRET`, `DATA_ENCRYPTION_KEY`, `RESEND_API_KEY`, `EMAIL_FROM`, `FRONTEND_ORIGIN`.

`preDeployCommand` runs `python -m src.init_db` on every deploy (idempotent — only creates seed accounts/flights if they don't already exist) via the service's Railway configuration.

**What was actually found deploying this for real:** the service's public domain initially had `targetPort: null`, producing a `502 Application failed to respond` even though the app ran fine internally — fixed via `railway domain update --port 8000`. The first `railway up` attempt tried to upload `backend/venv/` and `frontend/node_modules/` before a `.railwayignore` was added. A new `User.email_otp_hash`/`email_otp_expires_at` column was missing on the already-existing live table after a schema change (SQLAlchemy's `create_all()` never alters existing tables) — required adding an explicit lightweight migration step (`run_lightweight_migrations()`), and it had to be wired into *both* `main.py`'s startup path and `init_db.py`'s standalone path, since Railway's `preDeployCommand` uses the latter.

## Verifying a deployment (either path)

1. `GET /healthz` → `200`
2. Register a passenger, log in, search flights, book a seat, pay, check in, view the boarding pass QR
3. Log in as a seeded staff account → confirm 2FA is required (`requires_2fa: true`) before a usable token is issued
4. `GET /api/v1/admin/audit-logs/verify` (as admin) → `{"intact": true}`
5. `curl -I` the public URL → confirm `Strict-Transport-Security`, `X-Frame-Options`, `Content-Security-Policy` headers are present
