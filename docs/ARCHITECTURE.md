# Save Flight — System Architecture

## Overview

Save Flight is a three-module secure airport operations platform: a passenger booking/check-in portal, a staff operations console (check-in, crew manifests, security incidents), and an admin analytics dashboard — all served by one FastAPI backend and one React frontend, backed by Postgres, with a hardened Docker/Nginx/Prometheus/Grafana infrastructure layer for self-hosted deployment (a combined single-container variant runs on Railway).

```
                          ┌─────────────────────────────┐
                          │        React SPA (CRA)      │
                          │  passenger / staff / admin   │
                          │  views, JWT in localStorage  │
                          └───────────────┬─────────────┘
                                          │ HTTPS (Authorization: Bearer <jwt>)
                          ┌───────────────▼─────────────┐
                          │      nginx (edge, TLS)       │
                          │ security headers, rate limit │
                          │ HTTP→HTTPS redirect           │
                          └───────────────┬─────────────┘
                                          │
                          ┌───────────────▼─────────────┐
                          │       FastAPI backend        │
                          │  auth · booking · payment     │
                          │  staff · admin · analytics     │
                          │  seat map · flight status       │
                          └───────┬───────────────┬───────┘
                                  │               │
                     ┌────────────▼───┐   ┌───────▼────────┐
                     │   PostgreSQL    │   │  Resend (email) │
                     │ (encrypted PII) │   │   2FA OTP send   │
                     └────────────┬────┘   └─────────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │ postgres_exporter →      │
                     │ Prometheus → Grafana      │
                     └───────────────────────────┘
```

## Modules and ownership boundaries

The system is deliberately organized so each of the three project roles owns a distinct, independently reviewable layer:

| Module | Owns | Key files |
|---|---|---|
| Backend/Database Security | Data model, cryptography, authN/authZ, business-logic integrity | `backend/src/security.py`, `models.py`, `auth_routes.py`, `booking_routes.py`, `payment_routes.py`, `audit.py` |
| Frontend/API Security | Client-side defense-in-depth, API contract, CORS, session handling | `frontend/src/config/api.config.js`, `utils/sanitizer.js`, `utils/validators.js`, `components/ProtectedRoute.jsx` |
| DevOps/Infrastructure Security | Transport security, container hardening, network segmentation, observability, backups | `docker-compose.yml`, `infrastructure/nginx/`, `infrastructure/prometheus/`, `infrastructure/backup/` |

Each module's interface to the others is narrow and explicit: the frontend only ever talks to the backend's versioned REST API (`/api/v1/...`) over HTTPS with a bearer token; the backend only ever talks to Postgres via SQLAlchemy through a single `DATABASE_URL`; infrastructure only ever touches the other two as opaque containers with declared health checks and resource limits — no module reaches into another's internals.

## Backend architecture

FastAPI app (`backend/src/main.py`) composed of per-domain routers, each mounted with its own prefix and, where relevant, a router-level RBAC dependency:

- `auth_routes.py` (`/api/v1/auth`) — register, login, 2FA verify/enroll, logout
- `passenger_routes.py` (`/api/v1/passenger`, `/api/v1/flights`) — own bookings, flight search, check-in
- `booking_routes.py` (`/api/v1/booking`) — seat-aware booking creation with collision/restriction checks
- `payment_routes.py` (`/api/v1/payment`) — server-derived payment amount, tokenized card storage
- `staff_routes.py` (`/api/v1/staff`) — check-in redemption, crew manifests, security incidents (role-gated per endpoint)
- `admin_routes.py` (`/api/v1/admin`) — user/staff management, audit log access + integrity verification
- `seat_routes.py` (`/api/v1/flights/{id}/seats`) — lazy seat-map generation, class-based pricing
- `flight_status_routes.py` (`/api/v1/flights/{id}/status`) — real timeline + explicitly-labeled simulated live tracking
- `analytics_routes.py` (`/api/v1/admin/analytics`) — admin-only, all figures computed from real DB rows (no fabricated metrics)

Cross-cutting concerns are middleware, not per-route code: `SecurityHeadersMiddleware` and `SlowAPIMiddleware` (`middleware.py`) apply to every response/request uniformly; `CORSMiddleware` is configured once with an explicit origin allow-list.

Persistence (`database.py`, `models.py`) uses SQLAlchemy ORM exclusively for all request-serving code paths — no raw SQL is built from request input anywhere. A small, deliberately lightweight in-house migration system (`run_lightweight_migrations()`) adds new columns idempotently on startup rather than depending on Alembic, since the schema changes needed during this project were additive and didn't require complex migration chains.

## Frontend architecture

A single-page React app (Create React App) with route-based code organization under `frontend/src/components/`. `ProtectedRoute.jsx` gates every role-restricted route client-side (UX layer only — the real boundary is server-side RBAC); `Layout.jsx` renders role-appropriate navigation (desktop top nav, mobile hamburger + bottom nav). All API access goes through a single configured `axios` instance (`config/api.config.js`) so token attachment, base URL, and 401-triggered logout are handled in exactly one place rather than duplicated per component.

## Data model (core entities)

- `User` — auth identity: email, Argon2 hash, role, TOTP secret, email-OTP hash/expiry, lockout state
- `Passenger` — encrypted PII (name, passport, address) linked 1:1 to a passenger-role `User`
- `Staff` — department/employee ID linked 1:1 to a staff-role `User`
- `Flight` — schedule, route, gate/terminal, base price, status
- `Seat` — per-flight generated seat map (class, position, exit-row/restricted flags)
- `Booking` — passenger × flight × seat, status lifecycle (`active` → `checkedin` / `cancelled`)
- `PaymentRecord` — tokenized card + server-derived amount, linked to a booking
- `AuditLog` — append-only, hash-chained security event log

## Deployment topologies

Two deployment shapes exist for this project, deliberately:

1. **Full docker-compose stack** (`docker-compose.yml`) — separate `backend`, `frontend`, `nginx`, `postgres`, `prometheus`, `grafana` containers on an isolated bridge network. This is the "real" target architecture and was verified by actually running the full stack, not just reviewing the compose file.
2. **Combined single-container Railway deployment** (`Dockerfile.railway`) — backend + built frontend static assets served from one process, chosen specifically because the available Railway account's free-tier service quota couldn't accommodate 5+ separate services. Both topologies apply the *same* security headers and rate limits redundantly at the application layer (`SecurityHeadersMiddleware`, `slowapi`) specifically so neither depends on nginx being present in front of it.

See `docs/DEPLOYMENT.md` for the exact steps to run either topology.
