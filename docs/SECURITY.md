# Save Flight — Security Overview

This document summarizes the security posture of the system as a whole: what's implemented, how secrets are managed, and — just as importantly — what is *not* implemented and why, so reviewers aren't left guessing whether an absence is an oversight or a deliberate scoping decision. For a threat-by-threat breakdown, see `docs/THREAT_MODEL.md`. For per-mechanism test evidence, see `docs/TESTING_VALIDATION.md`.

## Cryptography

| Purpose | Algorithm | Location |
|---|---|---|
| Password storage | Argon2id (via `passlib`) | `backend/src/security.py:hash_password` |
| PII at rest (name, passport, address) | AES-256-GCM, random 12-byte nonce per call | `security.py:encrypt_data`/`decrypt_data` |
| Session tokens | JWT, HS256, algorithm pinned at decode time | `security.py:create_access_token`/`decode_access_token` |
| 2FA (staff/admin) | TOTP (RFC 6238) + CSPRNG-generated 6-digit emailed OTP fallback | `security.py`, `pyotp` |
| Payment card data | Never stored — opaque token + last 4 digits only | `security.py:mask_card_number` |
| Database backups | AES-256-CBC + PBKDF2 (via `openssl enc`) | `infrastructure/backup/backup-postgres.sh` |
| Transport (browser ↔ edge) | TLS 1.2/1.3, HSTS | `infrastructure/nginx/nginx.conf` |
| Boarding pass authenticity | RSA-2048, PSS padding, SHA-256 (true asymmetric digital signature) | `security.py:sign_boarding_pass`/`verify_boarding_pass_signature` |

AES-256-GCM was chosen deliberately over the Python `cryptography` library's `Fernet` recipe: Fernet's default cipher is AES-128-CBC+HMAC, which does not satisfy an explicit "AES-256" requirement even though it's a reasonable authenticated-encryption scheme in its own right. Using `AESGCM` directly with a 32-byte key closes that gap.

**On "digital signatures" specifically:** JWT's `HS256` is a symmetric HMAC, not a true digital signature — the server holds one secret for both signing and verifying, so it provides authentication but not non-repudiation. The boarding-pass mechanism above is a genuine asymmetric signature: the private key (server-only) signs at check-in, and the public key (freely exposed at `GET /api/v1/boarding-pass/public-key`) can verify authenticity independently, without database access or trust in whoever presents the pass. This is deliberately additive, not a replacement for the existing single-use-token DB check (`staff_routes.py` still verifies `used_at`) — a signature proves *authenticity/integrity*, not *"not already redeemed"*; those are different properties. It also closes a specific gap the DB-only design had: if a booking row were altered directly via a compromised DB credential (bypassing the app), the token would still match, but the signature — computed over the original values at issuance — would not, and redemption is rejected (`409`).

## Secrets management

No secret (JWT signing key, encryption key, database password, Resend API key) is hardcoded in source. All are read from environment variables (`os.getenv`) with `.env` files excluded from version control via `.gitignore`. `.env.example` files document the *names* of required variables with placeholder values only.

The demo/seed account passwords (`init_db.py`, `seed_demo_data.py`) are an intentional exception — they are test fixtures for grading/demo purposes, documented in plaintext by design, and are not treated as sensitive (they grant access only to synthetic demo data on a project deployment, not a real production system with real user data).

## Authentication & session model

- Passenger JWTs: 60-minute TTL. Staff/admin JWTs: 240-minute TTL (a deliberate difference — staff sessions are used for longer operational shifts; the trade-off is a longer exposure window if a staff token is stolen, which mandatory 2FA on issuance is intended to offset).
- Tokens are bearer tokens sent via `Authorization: Bearer <jwt>`, stored client-side in `localStorage`, **not** cookies.
- `decode_access_token` passes an explicit `algorithms=["HS256"]` allow-list to `jose.jwt.decode` — a token claiming `"alg": "none"` or any other algorithm is rejected outright, not silently accepted.

## CSRF — explicitly not implemented, and why that's the correct call here

**There are no CSRF tokens anywhere in this codebase.** This is a deliberate architectural consequence, not an oversight: CSRF is an attack against *ambient* credentials a browser attaches automatically (cookies) to a forged cross-site request. This API never relies on that — the JWT is attached manually, in JavaScript, via an `Authorization` header (`frontend/src/config/api.config.js`). A malicious third-party page cannot read this app's `localStorage` (same-origin policy) and cannot make the victim's browser attach an `Authorization` header to a forged request the way it can with cookies. The classic CSRF vector simply doesn't exist for this design.

The trade-off this choice makes: storing the token in `localStorage` instead of an `HttpOnly` cookie means a successful XSS bug *would* be able to exfiltrate the token (whereas `HttpOnly` cookies are inaccessible to JavaScript, including injected JavaScript). This system's answer to that trade-off is investing in XSS prevention instead (React's default JSX escaping + DOMPurify + a strict CSP with `script-src 'self'`) rather than in CSRF tokens, which would defend against a threat that doesn't apply to this design in the first place.

## Database transport encryption

The `backend`↔`postgres` connection is TLS-encrypted and the server actively enforces it, not just opportunistically offers it. `infrastructure/postgres/Dockerfile` generates a self-signed server certificate at build time (proper `postgres`-owned, `0600`-permissioned key - Postgres refuses to start with a world/group-readable key file); `infrastructure/postgres/pg_hba.conf` uses `hostssl` (not `host`) for every network-reachable rule, so a client that doesn't negotiate TLS is rejected outright with `FATAL: no pg_hba.conf entry ... no encryption`, not silently downgraded. Both `backend`'s `DATABASE_URL` and `postgres_exporter`'s `DATA_SOURCE_NAME` use `sslmode=require`.

This was verified by actually running the stack, not just reviewing the config: `SHOW ssl;` reports `on`; a deliberate `sslmode=disable` connection attempt from another container is rejected with the exact "no encryption" error above; `pg_stat_ssl` shows the backend's live connections with `ssl = t`. The one `ssl = f` row observed is the local `psql` session over the unix socket, which `hostssl` doesn't apply to by design (`local all all trust` - a unix socket connection never leaves the container's own filesystem namespace, so TLS wouldn't add anything there).

The certificate itself is self-signed and generated fresh on every image build - appropriate for this project's local/network-isolated deployment, not for a real production system across the open internet, which would need a CA-issued certificate and `verify-full` client verification instead of `require`.

## Firewall

`infrastructure/firewall/ufw_rules.sh` provides host-level firewall rules (default-deny inbound, rate-limited SSH, HTTP/HTTPS allowed, Postgres restricted to localhost) for a bare-metal or VM deployment target. This is layered on top of, not a replacement for, Docker's own network segmentation (`secure_network` bridge network, no host port mapping for internal-only services) — the two controls address different deployment models (host-level vs. container-level isolation) and both are present.

## Supply-chain / dependency vulnerability scanning (the practical "malware" equivalent)

There's no file-upload feature anywhere in SAOP, so traditional antivirus/malware scanning has no real attack surface to defend — there's nothing a user submits that could contain a malicious payload for an AV engine to detect. The realistic equivalent threat for a project like this is a **known-vulnerable or compromised dependency** (a genuine, common supply-chain attack class), so that's what's actually scanned and fixed: `infrastructure/security/dependency_audit.sh` runs `pip-audit` against `backend/requirements.txt` and `npm audit` against the frontend.

Running this for real (not just writing the script) found **37 known CVEs across 7 backend packages** — including `cryptography` (the library both AES-256-GCM encryption and the new RSA boarding-pass signing depend on) and `python-jose` (used for every JWT operation in the system). These were fixed by upgrading pinned versions in `requirements.txt` (`cryptography` 41.0.4→48.0.1+, `python-jose` 3.3.0→3.4.0, `fastapi` 0.115.2→0.141.1 to pull a patched `starlette`, plus `python-multipart` and `python-dotenv`), each verified against the full 85-test suite before and after to confirm no regression.

Three findings remain, deliberately not force-fixed, with reasoning:
- **`ecdsa` 0.19.2** — a known, upstream-acknowledged issue with no patched version available (pure-Python ECDSA has known timing-side-channel limitations the maintainers have stated won't be fully resolved). It's a transitive dependency of `python-jose` used only for its `ES256`/`ECDSA` code path — this system exclusively uses `HS256`, so the vulnerable code path is never exercised.
- **`pyasn1` 0.4.8** — `python-jose` 3.4.0 explicitly requires `pyasn1<0.5.0`; forcing the patched 0.6.4 creates a genuine, pip-flagged dependency conflict. Verified this isn't a live risk the same way (ASN.1/RSA-key-parsing edge cases, not relevant to our HS256-only usage) and chose to respect the library's own declared constraint over forcing an incompatible upgrade.
- **`pytest` 8.3.5** — a major-version fix (9.0.3) exists, but `pytest` is a test-only dependency that never runs in the deployed container (the Dockerfile's `CMD` is `uvicorn`, never `pytest`), so it has zero production exposure; the upgrade risk (pytest-asyncio/pytest-cov plugin compatibility across a major version) wasn't worth taking for a dependency with no runtime attack surface.

On the frontend, `npm audit --omit=dev` reports 72 findings, but all trace to `react-scripts`'s internal build tooling (webpack plugins, its dev server) — confirmed empirically by grepping the actual production `build/` bundle for the flagged package names (`jsonpath`, `serialize-javascript`, `rollup-plugin-terser`): none appear. These packages run during `npm run build` on a developer/CI machine and are never shipped to, or executed by, an end user's browser.

## What is intentionally out of scope

- **WAF / DDoS-scale mitigation:** rate limiting here defends against single-source brute force and moderate load, not a distributed volumetric attack. That class of defense (e.g., Cloudflare in front of the stack) is an infrastructure/budget decision beyond this project's scope.
- **Fine-grained Postgres role permissions:** the application connects with one database user with full read/write on its own schema, not a set of least-privilege per-service roles. Acceptable for this project's single-application-owns-its-schema model; would be a real next step for a system where multiple independent services shared one database.

## Observability

Prometheus scrapes `backend`'s `/metrics` endpoint (`failed_login_attempts_total`, `successful_login_total`, `unauthorized_access_attempts_total`) and `postgres_exporter`. Grafana visualizes these. The admin analytics dashboard (`/admin/analytics/*`) is a separate, application-level (not infrastructure-level) view — it computes real figures from actual booking/payment/check-in rows and deliberately does not fabricate figures it has no real data source for (e.g., no invented uptime percentage or queue-wait-time metric).
