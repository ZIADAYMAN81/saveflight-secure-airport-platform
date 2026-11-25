# SaveFlight: Secure Airport Operations Platform

[![tests](https://github.com/ZIADAYMAN81/saveflight-secure-airport-platform/actions/workflows/tests.yml/badge.svg)](https://github.com/ZIADAYMAN81/saveflight-secure-airport-platform/actions/workflows/tests.yml)

> University coursework, The British University in Egypt, 2026. Author: Ziad Ayman.

A full-stack airport management system built security-first: a **React** passenger and staff portal, a **FastAPI** back-end over an encrypted **PostgreSQL** database, and a hardened **Docker / Nginx / Prometheus / Grafana** deployment stack.

Passengers search flights, pick seats, pay and receive a digitally signed QR boarding pass. Check-in agents, crew, security staff and administrators each get a role-specific dashboard behind mandatory two-factor authentication.

## Highlights
- **Defence in depth:** Argon2 hashing, account lockout and rate limiting, JWT with server-side role-based access control for five roles, and mandatory TOTP / emailed-OTP 2FA for staff.
- **Data protection:** passenger PII encrypted at rest with AES-256-GCM; card numbers are never stored (tokenised reference and last 4 digits only).
- **Tamper evidence:** a SHA-256 hash-chained audit log, and RSA-2048 signatures on boarding passes.
- **Tested:** 85 back-end tests (pytest, against a real database, with no security mechanism mocked) plus a Jest / React Testing Library suite for the front-end.
- **Documented:** architecture, threat model, security controls, deployment and test evidence in [`docs/`](docs/).

## Tech stack
React 18 · JavaScript (ES6+) · HTML5 / CSS3 · React Router · Axios · Recharts · Python · FastAPI · SQLAlchemy · PostgreSQL · Docker Compose · Nginx · Prometheus · Grafana · pytest · Jest

## Features

- **Authentication**: Argon2 password hashing, JWT bearer tokens (1h passengers / 4h staff), mandatory TOTP
  2FA for staff/admin roles, account lockout after 5 failed attempts, rate-limited login (5/min).
- **RBAC**: five roles — `passenger`, `agent` (check-in), `crew`, `security`, `admin` — enforced server-side
  on every endpoint via `require_role`.
- **Data protection**: passenger PII (name, passport, address) encrypted at rest with AES-256-GCM (raw, not
  Fernet - Fernet's default cipher is AES-128); payment card numbers are never stored, only a tokenized
  reference + last 4 digits (PCI-DSS style tokenization).
- **Tamper-evident audit log**: every security event is chained via SHA-256 (`prev_hash` → `entry_hash`), so
  editing any historical row is detectable (`GET /api/v1/admin/audit-logs/verify`).
- **API security**: CORS locked to the configured frontend origin, OWASP security headers on every response,
  global + per-route rate limiting (slowapi), Prometheus metrics for failed logins / unauthorized access.
- **Infrastructure**: Postgres (encrypted volume + pgcrypto), Nginx reverse proxy (TLS 1.2+, HSTS, rate
  limiting, hidden-path denial), Prometheus + Grafana + postgres-exporter, encrypted backup/restore scripts.

## Repository Layout

```
backend/         FastAPI app (auth, passenger, staff, admin, booking, payment routes)
frontend/        React SPA (passenger portal, staff dashboard, admin panel)
infrastructure/  nginx, prometheus, backup, firewall configs
docker-compose.yml
.env.example     root env vars consumed by docker-compose
```

## Backend — run locally

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows; use `source venv/bin/activate` on Linux/macOS
pip install -r requirements.txt
copy .env.example .env         # then edit DATA_ENCRYPTION_KEY/JWT_SECRET for anything beyond local dev
python -m src.init_db          # seeds a passenger + one staff account per role; prints each 2FA QR/URI
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

Seeded accounts (see console output from `init_db` for the staff TOTP provisioning URIs — scan with any
authenticator app, e.g. Google Authenticator/Authy):

| Role      | Email                   | Password           | 2FA |
|-----------|-------------------------|--------------------|-----|
| passenger | passenger@example.com   | SecureP@ssw0rd!    | no  |
| agent     | agent@example.com       | AgentP@ssw0rd1!    | yes |
| crew      | crew@example.com        | CrewP@ssw0rd1!     | yes |
| security  | security@example.com    | SecP@ssw0rd1!      | yes |
| admin     | admin@example.com       | AdminP@ssw0rd1!    | yes |

### Backend tests

```bash
cd backend
python -m pytest tests -v
```

85 tests covering registration/login/lockout, mandatory staff 2FA, RBAC across all five roles, booking +
check-in + boarding-pass flows (including row-level-security and reuse prevention), payment tokenization,
audit-log tamper detection, encryption round-trip integrity, JWT expiry enforcement, and SQL-injection
resistance.

## Frontend — run locally

```bash
cd frontend
npm install
copy .env.example .env
npm start
```

Routes: `/login`, `/register`, `/2fa-verify`, `/dashboard` (passenger bookings), `/flights` (search/book/pay),
`/boarding-pass/:token` (QR code), `/staff/dashboard` (role-conditional agent/crew/security tools),
`/admin` (user + audit-log management).

### Frontend tests

```bash
cd frontend
npm test
```

Tests cover input validators, `ProtectedRoute` (expired/invalid/wrong-role tokens), Login (2FA redirect,
lockout/rate-limit messaging), Register, and the staff dashboard's role-conditional rendering.

## Docker Compose (full stack)

```bash
cp .env.example .env                              # edit DB_PASSWORD and other secrets first
bash infrastructure/nginx/generate-dev-cert.sh     # self-signed cert for local HTTPS
docker compose up --build
```

> Windows Git Bash users: run the cert script as `MSYS_NO_PATHCONV=1 bash infrastructure/nginx/generate-dev-cert.sh`
> to stop Git Bash from mangling the `-subj` path.

- App via Nginx (TLS): https://localhost
- Backend directly: http://localhost:8000
- Frontend directly: http://localhost:3000
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (admin / `$GRAFANA_PASSWORD`)

Services: `postgres`, `postgres_exporter`, `backend`, `frontend`, `nginx`, `prometheus`, `grafana`. Backend
container runs as a non-root user with a read-only root filesystem; Postgres data, Prometheus data, and
Grafana data persist in named volumes.

### Backups

```bash
DB_USER=... DB_NAME=... BACKUP_PASSWORD=... bash infrastructure/backup/backup-postgres.sh
DB_USER=... DB_NAME=... BACKUP_PASSWORD=... bash infrastructure/backup/restore-postgres.sh <file.sql.gz.enc>
```

Schedule the backup script daily via cron/systemd-timer on the Docker host.

### Firewall (bare-metal host, outside Docker's own network isolation)

```bash
sudo bash infrastructure/firewall/ufw_rules.sh
```

## Security notes / known trade-offs

- JWTs are kept in `localStorage` and sent via `Authorization: Bearer`, not cookies — this avoids CSRF
  entirely (no ambient credential is attached to requests automatically) at the cost of XSS-exfiltration
  risk if a script-injection bug existed; React's default JSX escaping plus the CSP header mitigate that.
- Rate limiting and account lockout share the same threshold (5/min) in this setup, so a locked-out account
  and a rate-limited IP surface similar HTTP statuses (423 vs 429) by design.
- The Nginx TLS listener needs a certificate before it will start; `generate-dev-cert.sh` produces a
  self-signed one for local testing. Use Let's Encrypt/certbot for anything internet-facing.

## License
MIT, see [LICENSE](LICENSE).
