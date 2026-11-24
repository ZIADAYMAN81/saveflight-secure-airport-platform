# Save Flight — Threat Model (STRIDE)

**System:** Save Flight (formerly "Secure Airport Operations Platform")
**Scope:** Passenger booking/check-in portal, staff/security operations, admin analytics — FastAPI backend, React frontend, Postgres, Docker/Nginx/Prometheus/Grafana infrastructure.

This document enumerates the 14 threats identified across the six STRIDE categories, the actual mitigation implemented for each (with file references), and the automated test that verifies it. Every entry below maps to real, running code — not aspirational controls. Where a mitigation is partial or a residual risk remains, that is stated explicitly rather than omitted.

---

## Spoofing (identity)

### S1 — Fraudulent passenger login (credential stuffing / brute force)
- **Attack:** An attacker with a leaked or guessed password list attempts repeated logins against a passenger account.
- **Mitigation:** Argon2 password hashing (`security.py:hash_password`) makes offline cracking of a leaked DB expensive; progressive account lockout after 5 failed attempts (`auth_routes.py:login`, `MAX_FAILED_LOGIN_ATTEMPTS`) stops online brute force; dual-layer rate limiting (nginx `limit_req` + `slowapi` `@limiter.limit("5/minute")`) throttles request volume before lockout logic even runs.
- **Residual risk:** None significant for a single-account attack; a distributed (many-IP) credential-stuffing campaign would bypass the per-IP rate limit and rely on lockout alone.
- **Test:** `test_auth.py::test_account_lockout_after_repeated_failures`, `test_login_rate_limited_after_five_attempts`.

### S2 — Staff credential compromise (phishing, password reuse)
- **Attack:** A staff password is phished or reused from a breached third-party site; the attacker attempts to log in as that staff member.
- **Mitigation:** Mandatory 2FA for all staff roles (`agent`/`crew`/`security`/`admin`) — password alone is never sufficient (`auth_routes.py:login`, `STAFF_ROLES` check forces `requires_2fa: true` and withholds the JWT). TOTP (RFC 6238) is the primary factor; a bootstrapped emailed OTP exists only as a fallback for accounts that haven't enrolled an authenticator yet, and both paths burn the code on first use.
- **Residual risk:** SIM-swap or email-account compromise could defeat the emailed-OTP bootstrap path specifically (not TOTP) — acceptable for a one-time enrollment window, not the steady-state login path.
- **Test:** `test_staff_login_requires_2fa_step`, `test_staff_2fa_verify_success`, `test_emailed_otp_is_single_use`.

### S3 — System/service impersonation (fake API endpoint, MITM)
- **Attack:** An attacker positions between the client and server (rogue Wi-Fi AP, DNS spoofing) to impersonate the API and harvest credentials or tokens.
- **Mitigation:** TLS termination at the edge (nginx `ssl_certificate`, TLS 1.2/1.3 only — `infrastructure/nginx/nginx.conf`) plus HSTS (`Strict-Transport-Security: max-age=31536000; includeSubDomains`) forces HTTPS on return visits, closing the SSL-stripping downgrade window. The live Railway deployment terminates TLS at Railway's edge.
- **Residual risk:** First-visit-before-HSTS-is-cached window (classic TOFU limitation of HSTS) — mitigated by the domain not needing to be typed as bare HTTP anywhere in the product.
- **Test:** Manual verification (`curl -I` showing HSTS header on both the local nginx and the live Railway URL); not unit-testable in the traditional sense since it's a transport-layer property.

---

## Tampering (data/message integrity)

### T1 — Boarding pass forgery
- **Attack:** A passenger (or third party) fabricates a boarding-pass token to board without a valid check-in, or a compromised database credential is used to directly edit a boarding pass's underlying booking (e.g., reassigning it to a different flight/seat) after legitimate issuance.
- **Mitigation:** Two independent layers. (1) Boarding pass tokens are server-generated opaque values tied 1:1 to a specific `Booking` row created only by the real check-in flow; redemption looks the token up server-side and verifies it against the booking's actual state - there is no client-constructible token format to forge, and a token cannot be redeemed twice. (2) A genuine RSA-2048/PSS/SHA-256 digital signature (`security.py:sign_boarding_pass`) is computed over the booking/flight/seat values at issuance and re-verified at redemption (`staff_routes.py`) - this specifically catches the direct-DB-tamper case that the token lookup alone would miss, since the signature commits to the *original* values, not whatever the row currently contains. The public key is independently obtainable (`GET /api/v1/boarding-pass/public-key`, deliberately unauthenticated) so verification doesn't require trusting whoever presents the pass.
- **Residual risk:** None identified for the current design. Note this is additive, not a replacement: the signature proves authenticity/integrity, not "not already redeemed" - the DB-backed single-use check still does that job.
- **Test:** `test_staff_flow.py::test_boarding_pass_cannot_be_reused`, `test_invalid_boarding_pass_token_rejected`; `test_security_properties.py::test_boarding_pass_rsa_signature_roundtrip`, `test_tampered_boarding_pass_fails_staff_redemption`, `test_boarding_pass_public_key_endpoint_is_unauthenticated`.

### T2 — Flight/booking data modification by unauthorized parties
- **Attack:** A passenger or lower-privileged staff role attempts to directly modify flight schedules, gates, or another passenger's booking.
- **Mitigation:** All mutating flight/booking endpoints are gated by `require_role()` (`deps.py`) server-side, independent of any client-side UI gating; booking mutations are additionally scoped to the authenticated user's own `passenger_id` (row-level filtering), so even a valid passenger token cannot touch another passenger's row.
- **Residual risk:** None identified; verified per-role.
- **Test:** `test_rbac.py::test_unauthorized_flight_modification_blocked`, `test_passenger_cannot_view_others_bookings`.

### T3 — Payment/price manipulation
- **Attack:** A malicious client intercepts and edits the payment request to pay less than the actual fare (classic price-tampering via proxy/dev-tools).
- **Mitigation:** `PaymentRequest` schema has no `amount` field at all (`schemas.py`) — the server always derives the charge from the real `Flight.base_price` × the booked seat's class multiplier (`payment_routes.py:process_payment`), so there is no client-supplied value to tamper with in the first place.
- **Residual risk:** None identified.
- **Test:** `test_payment_and_audit.py::test_payment_amount_is_derived_from_flight_price_not_client_input`, `test_payment_amount_reflects_seat_class`.

---

## Repudiation (denying an action occurred)

### R1 — Staff member denying they performed an action (check-in override, incident report, staff creation)
- **Attack:** A staff member (or attacker using their compromised session) performs a sensitive action, then denies having done it, and there's no reliable record to contradict them.
- **Mitigation:** Every authentication event, booking/payment mutation, staff-management action, and check-in is appended to a SHA-256 hash-chained audit log (`audit.py:log_security_event`) recording user ID, action, resource, IP, status, and UTC timestamp. The chain construction (`entry_hash` commits to `prev_hash`) means a later attempt to selectively delete or edit one row to manufacture deniability breaks the hash chain for every subsequent row — detectable via `GET /admin/audit-logs/verify`.
- **Residual risk:** A compromise that occurs and is *immediately* reverted before the next legitimate log entry (i.e., the very last row in the table) has no "next row" to detect the tamper against yet — inherent to any append-only hash chain, mitigated by verifying the chain frequently rather than only at incident time.
- **Test:** `test_payment_and_audit.py::test_audit_chain_is_intact_after_normal_activity`, `test_tampering_with_audit_log_breaks_chain`.

---

## Information Disclosure (confidentiality)

### I1 — Passenger PII leak (database compromise, backup theft, insider access)
- **Attack:** An attacker gains read access to the `passengers` table (via SQL injection elsewhere, a stolen backup, or a malicious insider with DB credentials) and reads full names, passport numbers, and addresses in plaintext.
- **Mitigation:** All three fields are encrypted at rest with AES-256-GCM before the row is ever written (`security.py:encrypt_data`, called from `auth_routes.py:register`) — a fresh random nonce per encryption, authenticated so tampering is detectable, never Fernet/AES-128. Database backups are themselves additionally encrypted with AES-256-CBC+PBKDF2 (`infrastructure/backup/backup-postgres.sh`), so a stolen backup file is doubly protected.
- **Residual risk:** The encryption key (`DATA_ENCRYPTION_KEY`) itself must be protected — it lives in Railway's environment variable store / a local `.env`, never in source control (confirmed via `.gitignore`). Anyone who obtains both the DB *and* the key can decrypt; this is inherent to any at-rest-encryption design where the app itself must decrypt for legitimate use.
- **Test:** `test_security_properties.py::test_encryption_roundtrip`; manual verification that `passengers.passport_number` is an opaque base64 blob when inspected directly.

### I2 — Payment card data exposure
- **Attack:** An attacker with database or log access recovers full card numbers from a past transaction.
- **Mitigation:** The raw card number is used only in-memory for the single payment request and is never persisted, logged, or echoed back; `mask_card_number()` (`security.py`) generates an opaque token plus last-4 digits, and only those are written to `PaymentRecord`. Audit log entries explicitly redact to `****<last4>`.
- **Residual risk:** None identified — no full PAN exists anywhere at rest.
- **Test:** `test_payment_and_audit.py::test_payment_persists_token_not_raw_card_number`, `test_payment_succeeds_and_never_returns_full_card_number`.

### I3 — Operational data leak (flight manifests, staff rosters, audit logs to the wrong role)
- **Attack:** A lower-privileged role (e.g., `agent`) queries an endpoint meant for a higher-privileged role (e.g., `crew`'s flight manifest or `admin`'s audit log) and receives data they shouldn't see.
- **Mitigation:** Every staff/admin endpoint is wrapped in `require_role([...])` with an explicit allow-list per route — there is no "any authenticated staff" catch-all; each role boundary is enforced and tested independently (agent cannot see crew manifests, non-admin cannot see audit logs).
- **Residual risk:** None identified for currently-defined roles.
- **Test:** `test_rbac.py::test_agent_cannot_view_flight_manifest_crew_only`, `test_non_admin_cannot_view_audit_logs`.

---

## Denial of Service

### D1 — Flood/DDoS targeting the check-in or login endpoint
- **Attack:** A volumetric flood of requests against the highest-value endpoints (login, check-in) degrades availability for legitimate passengers, especially during peak check-in windows.
- **Mitigation:** Two independent rate-limiting layers — nginx `limit_req`/`limit_conn` at the edge (rejects excess traffic before it reaches the Python process at all) and `slowapi` at the application layer (`5/minute` on auth endpoints, `100/minute` general default) so the limit still holds even in the single-container Railway deployment where nginx isn't in front of the app.
- **Residual risk:** A large-scale distributed volumetric attack (thousands of source IPs) would exceed what per-IP rate limiting alone can absorb — that class of attack typically requires a CDN/WAF layer (e.g., Cloudflare) in front of the whole stack, which is out of scope for this deployment's budget/infrastructure.
- **Test:** `test_auth.py::test_login_rate_limited_after_five_attempts`.

### D2 — Resource-exhaustion attack against the database or containers
- **Attack:** A compromised or malicious process (e.g., via a vulnerable dependency) consumes unbounded CPU/memory/disk, starving other services on the same host.
- **Mitigation:** Every container in `docker-compose.yml` has explicit `deploy.resources.limits` (1.0 CPU / 512M memory) and capped logging (`max-size: 10m, max-file: 3`), so a single compromised or runaway container cannot exhaust host resources or fill disk via log flooding.
- **Residual risk:** Resource limits bound impact but don't prevent the compromise itself — this is a containment control, not a prevention control (prevention is covered under T2/S1/S2).
- **Test:** Manual verification — the hardened stack was actually run under `docker-compose up --build` and observed staying within configured limits; not unit-testable.

---

## Elevation of Privilege

### E1 — Passenger escalating to a staff-only endpoint
- **Attack:** A passenger account attempts to call an `agent`/`crew`/`security`/`admin`-only endpoint directly (bypassing the UI, since a hidden nav item is not a security boundary).
- **Mitigation:** `require_role()` re-checks the *live* database role on every request (not just the JWT claim in isolation, though the claim is itself signed and unforgeable) — a passenger token is rejected with `403` before the route body executes, regardless of what the frontend does or doesn't render.
- **Test:** `test_rbac.py::test_passenger_cannot_access_staff_dashboard`, `test_passenger_cannot_access_admin_users`.

### E2 — Staff escalating to admin-only functions
- **Attack:** A compromised `agent`/`crew`/`security` account attempts to reach admin-only functions (user management, audit log access, staff creation).
- **Mitigation:** Same `require_role(["admin"])` mechanism, plus admin accounts specifically carry the highest 2FA bar (mandatory TOTP/email-OTP as for all staff) — there's no separate "admin trust" that bypasses 2FA. `create-staff` — the one endpoint that could itself grant privilege — is itself admin-gated, closing the loop (a non-admin cannot mint new privileged accounts).
- **Test:** `test_rbac.py::test_agent_cannot_access_admin_endpoints`, `test_admin_can_create_staff_account`, `test_non_admin_cannot_create_staff_account`.

### E3 — Application-to-database privilege escalation
- **Attack:** A compromised application process attempts to use its database credentials beyond what the app actually needs (e.g., dropping tables, reading unrelated schemas) — relevant if a dependency vulnerability grants code execution inside the backend container.
- **Mitigation:** The application connects to Postgres with a single dedicated `DB_USER`/`DB_PASSWORD` credential set (env-injected, never hardcoded) rather than a superuser account; the container itself runs with `read_only: true` and `no-new-privileges:true`, so even a successfully-escalated process can't persist a webshell to disk or gain OS-level privileges beyond its starting set. Postgres itself is unreachable from outside the Docker host (no host port mapping) — network segmentation limits blast radius even if credentials leak.
- **Residual risk:** The current DB user is not further restricted with fine-grained Postgres role permissions (e.g., `REVOKE` on unrelated tables) — a full least-privilege Postgres role setup (separate read-only vs. read-write DB users per service) would be a natural next hardening step, not yet implemented.
- **Test:** Manual verification — `docker port airport_postgres` shows no host binding; the read-only-filesystem constraint was verified by actually running the hardened container (`docs/TESTING_VALIDATION.md §3.3`).

---

## Explicitly Out of Scope / Not Applicable

**CSRF (Cross-Site Request Forgery):** No CSRF token mechanism exists in this codebase, and none is needed given the current architecture — authentication is a bearer token attached explicitly via the `Authorization` header from JavaScript (`frontend/src/config/api.config.js`), not an ambient cookie the browser auto-attaches to cross-site requests. A forged cross-site form or `<img>` tag cannot read `localStorage` or set an `Authorization` header, so the classic CSRF attack vector doesn't apply here. If a future version moved the JWT into an `HttpOnly` cookie for XSS-hardening reasons, CSRF tokens would become necessary at that point and are not implemented today.

**Malware / Firewalls (module topic list):** No traditional host-based antivirus/EDR exists - there's no file-upload feature anywhere in SAOP for one to have anything to scan. The practical equivalent that's actually implemented and was actually run (`docs/SECURITY.md` § Supply-chain scanning) is dependency vulnerability scanning: `pip-audit`/`npm audit` via `infrastructure/security/dependency_audit.sh`, which found and fixed 37 real CVEs across 7 backend packages. A host-based firewall *is* implemented (`infrastructure/firewall/ufw_rules.sh` - default-deny inbound, rate-limited SSH); network-level segmentation is Docker's bridge isolation (`secure_network`, no host port mapping for Postgres) rather than a separate traditional network-firewall ACL layer.
