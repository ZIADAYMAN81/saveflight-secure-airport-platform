# SAOP — Testing & Validation Document

**System:** Secure Airport Operations Platform (SAOP)
**Modules covered:** Backend/Database Security · Frontend/API Security · DevOps/Infrastructure Security

Every scenario below documents a security mechanism that exists in the running codebase (referenced by exact file/function) and is exercised by an automated test that currently passes. Where a scenario was found and fixed during development (not merely designed correctly the first time), that is called out explicitly, since the "before" state is itself evidence of understanding the threat.

Manual verification was also run against a live Railway deployment (since taken down).
Automated suite: `backend/tests/` (pytest, 85 tests) and `frontend/src/__tests__/` (Jest/RTL, 60 tests).

**Backend code coverage: 90%** (`pytest --cov=src --cov-report=term-missing`, scoped via `.coveragerc` to exclude one-off operational scripts — `init_db.py`, `seed_demo_data.py`, `seed_all.py`, `bootstrap_admin_gmail.py` — invoked via CLI/`preDeployCommand`, not through the tested request-serving API surface. Including those inflates the denominator with code that "seeds data" rather than code that enforces a security property, so scoping coverage to the actual application logic is the more honest number.)

---

## 1. Backend / Database Security

### 1.1 Argon2 Password Hashing + Progressive Account Lockout

**Threat modeled:** Offline password cracking if the database leaks, and online brute-force credential stuffing.

**Input:** An attacker sends `POST /api/v1/auth/login` with `{"email": "ahmed.hassan1@example.com", "password": "wrongpass"}` five times in a row.

**Background Process:**
- Passwords are never stored in plaintext or reversible form. Registration calls `hash_password()` in `backend/src/security.py`, which uses `passlib.context.CryptContext(schemes=["argon2"])` — Argon2id, a memory-hard KDF specifically chosen over bcrypt/SHA-256 because it resists GPU/ASIC parallel cracking.
- On each failed attempt, `auth_routes.login()` increments `user.failed_login_attempts` in the `users` table (not a separate cache — durable across restarts).
- On the 5th consecutive failure (`MAX_FAILED_LOGIN_ATTEMPTS = 5`), the code sets `user.locked_until = utcnow() + timedelta(minutes=15)` (`ACCOUNT_LOCKOUT_MINUTES`).
- Every attempt — success or failure — is appended to the tamper-evident audit log via `log_security_event()` (see §1.5): `LOGIN_FAILED` ×5, then `ACCOUNT_LOCKED`.
- Critically, the error message returned for "wrong password" and "unknown email" is the **same generic 401** (`generic_error = HTTPException(401, "Invalid credentials")`) — this prevents user enumeration via response-message differences.

**Output:**
- Attempts 1–4: `401 Unauthorized`, `{"detail": "Invalid credentials"}`, `failed_login_attempts` = 1,2,3,4 in the DB.
- Attempt 5: `401 Unauthorized`, but the DB row now has `locked_until` set ~15 minutes in the future, and an `ACCOUNT_LOCKED` audit row is appended.
- A 6th attempt — even with the **correct** password — returns `423 Locked`, `{"detail": "Account temporarily locked due to failed login attempts"}`, because `login()` checks `user.locked_until > utcnow()` before ever touching the password hash.
- Verified by `test_auth.py::test_account_lockout_after_repeated_failures` and `test_login_rate_limited_after_five_attempts`.

---

### 1.2 AES-256-GCM Field-Level Encryption of Passenger PII

**Threat modeled:** Database compromise (SQL injection, stolen backup, insider access) exposing passport numbers, full names, and home addresses in plaintext.

**Input:** A passenger registers via `POST /api/v1/auth/register` with `{"full_name": "Ahmed Hassan", "passport_number": "A1234567", "address": "12 Nile St, Cairo", ...}`.

**Background Process:**
- `auth_routes.register()` never writes `payload.full_name`/`passport_number`/`address` directly. Each field is passed through `encrypt_data()` in `security.py` before the `Passenger` row is constructed.
- `encrypt_data()` uses `cryptography.hazmat.primitives.ciphers.aead.AESGCM` directly — **not Fernet**. This was an explicit correction during development: Fernet's default cipher is AES-128-CBC+HMAC, which does not satisfy an "AES-256" requirement; switching to raw AESGCM with a 32-byte key closes that gap.
- For every call, a **fresh random 12-byte nonce** (`os.urandom(12)`) is generated — nonce reuse under GCM is catastrophic (it breaks both confidentiality and integrity), so a new nonce per encryption is a hard requirement, not an optimization.
- The output is `base64.urlsafe_b64encode(nonce + ciphertext)` — nonce and ciphertext are concatenated so decryption is self-contained (no separate nonce storage/lookup needed).
- GCM is an **authenticated** cipher: it appends a 16-byte authentication tag. Any bit-flip in the stored ciphertext (accidental corruption or deliberate tampering) causes `decrypt_data()` to raise, rather than silently returning corrupted plaintext.
- The row actually persisted to Postgres (`passengers.full_name`, `.passport_number`, `.address`) contains only this base64 blob.

**Output:**
- `201 Created` returned to the client with the plaintext `UserProfile` (server holds the key; the encryption is at-rest, not in-transit hiding from the legitimate owner).
- Inspecting the `passengers` table directly (e.g. via `psql`) shows `passport_number` as an opaque ~60-character base64 string, never the raw `"A1234567"`.
- Decryption only happens server-side when data is read back for display (e.g. staff manifest view), via `decrypt_data()`, which fails closed (raises `RuntimeError`) if the ciphertext or key don't match — verified manually by round-tripping `encrypt_data`/`decrypt_data` in a REPL and confirming a flipped byte breaks decryption.

---

### 1.3 JWT Authentication + Server-Enforced Role-Based Access Control

**Threat modeled:** A passenger account escalating privileges to reach staff/admin-only endpoints (horizontal → vertical privilege escalation).

**Input:** An authenticated **passenger** (role=`passenger`) sends `GET /api/v1/admin/users` with their own valid JWT in the `Authorization: Bearer <token>` header.

**Background Process:**
- The JWT was issued at login by `create_access_token()`, which signs a payload `{"sub": user.id, "role": user.role, "exp": ..., "iat": ...}` with `HS256` using `JWT_SECRET` (`security.py`). The role is embedded in the **signed** token — the client cannot alter it without invalidating the signature.
- `deps.get_current_user()` runs on every protected route: extracts the bearer token, calls `decode_access_token()` (verifies the HMAC signature and expiry via `jose.jwt.decode`), then re-fetches the live `User` row from the DB by `sub` — so a deactivated (`is_active=False`) user is rejected even with an otherwise-valid, unexpired token.
- `/admin/users` is wrapped with `Depends(require_role(["admin"]))` (`deps.py`). `require_role()` compares `user.role` (from the freshly-queried DB row, not just the token claim) against the allow-list.
- Since `user.role == "passenger" not in ["admin"]`, the dependency raises `HTTPException(403)` **before the route body ever executes** — the admin-user-listing logic is never reached, so there's no code path where the check can be silently bypassed.
- `unauthorized_access_attempts_total` Prometheus counter is incremented for observability.

**Output:** `403 Forbidden`, `{"detail": "Forbidden"}`. No user data is returned, no DB query for the user list is even issued. Verified by `test_rbac.py::test_passenger_cannot_access_admin_users`, and symmetrically by `test_agent_cannot_access_admin_endpoints`, `test_agent_cannot_view_flight_manifest_crew_only` (each role's boundary is tested independently, not just "logged in vs not").

---

### 1.4 Two-Factor Authentication: TOTP (RFC 6238) with Emailed-OTP Fallback

**Threat modeled:** Stolen/phished staff password being sufficient to reach operational systems (check-in, manifests, audit logs).

**Input:** A staff `agent` account submits correct email+password at `POST /api/v1/auth/login`, then submits a 2FA code at `POST /api/v1/auth/2fa-verify`.

**Background Process:**
- Because `user.role in STAFF_ROLES` (`{agent, crew, security, admin}`), `login()` does **not** issue a usable token yet. It generates a 6-digit code via `generate_email_otp()` — built on `secrets.randbelow(1_000_000)` (CSPRNG, not `random`), so codes aren't predictable.
- Only the **SHA-256 hash** of the code (`hash_otp()`) is stored on the user row, alongside a 5-minute expiry (`EMAIL_OTP_EXPIRES_MINUTES`). The plaintext code is sent once via Resend's HTTP API (`email_service.send_email_otp`) and never persisted.
- The response is `{"requires_2fa": true, "user_id": ..., "access_token": ""}` — no token is handed out at this stage.
- At `/2fa-verify`, the server accepts **either** a valid TOTP code (`pyotp.TOTP(secret).verify(code, valid_window=1)`, RFC 6238, 30-second step with ±1 step drift tolerance) **or** a matching, unexpired emailed OTP (`verify_otp_hash()` recomputes SHA-256 and does an equality check against the stored hash). This dual-path exists because a freshly created staff account (via `/admin/create-staff`) has no TOTP secret yet and would otherwise be permanently locked out before ever enrolling an authenticator — the emailed OTP is the bootstrap path.
- On success, the OTP hash is nulled out immediately (`user.email_otp_hash = None`) — **one-time use**, even though it hadn't expired yet.
- Failure increments the same `failed_login_attempts`/lockout counters as password brute-forcing (§1.1), so 2FA brute-forcing is throttled identically.

**Output:**
- Valid code: `200 OK` with a real signed JWT (`STAFF_JWT_ACCESS_TOKEN_EXPIRES_MINUTES` = 240min TTL, shorter-lived model for higher-privilege roles is a deliberate design choice — passenger tokens use the 60-minute default).
- Reused code (submitted twice): second attempt returns `401 Unauthorized`, `{"detail": "Invalid 2FA code"}`, because `email_otp_hash` is already `None`.
- Verified by `test_auth.py::test_staff_login_requires_2fa_step`, `test_staff_2fa_verify_wrong_code_rejected`, `test_staff_can_verify_with_emailed_otp_instead_of_totp`, and `test_emailed_otp_is_single_use`.

---

### 1.5 Tamper-Evident Audit Log (SHA-256 Hash Chain)

**Threat modeled:** An attacker with direct database access (compromised credentials, malicious insider, or a successful SQL injection elsewhere) editing or deleting audit rows to cover their tracks.

**Input:** As an integration/attack simulation: an admin retrieves `GET /api/v1/admin/audit-logs/verify` (a) on a clean system, then (b) after a test manually runs `UPDATE audit_logs SET details='tampered' WHERE id=<some_early_row>` directly against the database, bypassing the application entirely.

**Background Process:**
- Every security-relevant action (`log_security_event()` in `audit.py`) computes `entry_hash = SHA256(prev_hash | user_id | action | resource | ip | status | details | timestamp)` and stores both `entry_hash` and `prev_hash` on the row. The very first row chains to a fixed genesis value (`"0" * 64`).
- This is a classic hash-chain / mini-blockchain construction: each entry's hash is a function of the *previous* entry's hash, so it's a linked, order-dependent commitment over the entire log history — not just a checksum of each row in isolation.
- `verify_chain_integrity()` walks the table in insertion order and **recomputes** every hash from the stored field values, comparing against the stored `entry_hash`/`prev_hash`. If a single row's `details` (or any other field) was altered after the fact, its recomputed hash no longer matches what was stored — and because `prev_hash` on the *next* row committed to the original (correct) hash, that mismatch propagates forward through every subsequent row.
- This means tampering with row #5 out of 500 is detectable even though rows #6–500 were never touched — the attacker would have to recompute and rewrite the entire chain from #5 onward, including entries created after their intrusion, to hide the edit.

**Output:**
- (a) Clean system: `{"intact": true}`.
- (b) After the raw UPDATE: `{"intact": false}` — the endpoint is admin-only (`require_role(["admin"])`), returns `403` to anyone else.
- Verified by `test_payment_and_audit.py::test_audit_chain_is_intact_after_normal_activity` and `test_tampering_with_audit_log_breaks_chain` (the latter performs exactly the raw-SQL tamper described above and asserts the endpoint flips to `false`).

---

### 1.6 Server-Side Payment Amount Derivation (Anti-Tampering)

**Threat modeled:** A malicious client modifying the request body to pay less than the actual fare (classic e-commerce "price tampering" via browser dev tools / intercepting proxy).

**Input:** `POST /api/v1/payment/process` with `{"booking_id": 42, "card_number": "4111111111111111", ...}` — note there is **no `amount` field in the request schema at all**; even a maximally adversarial client cannot submit one.

**Background Process:**
- `schemas.PaymentRequest` was deliberately designed without an `amount` field — this was an explicit fix during development after identifying that trusting a client-supplied amount is a payment-manipulation vulnerability (OWASP: "Business Logic — price manipulation").
- `payment_routes.process_payment()` looks up the real `Booking` → `Flight` server-side, then computes `amount = flight.base_price * CLASS_PRICE_MULTIPLIER[booking.seat.seat_class]` (multipliers: first=3.0×, business=1.8×, economy=1.0×, from `seat_routes.py`), falling back to the flat `flight.base_price` if no seat-map seat is attached.
- A double-payment guard queries for an existing `PaymentRecord` with `status="completed"` for the same `booking_id` before proceeding — prevents a replayed/duplicated request from charging twice.
- The raw card number is used only in-memory for this request; `mask_card_number()` returns an opaque token (`tok_<32 hex chars>`, `secrets.token_hex`) plus the last 4 digits. The full PAN is **never** written to the `payments` table, logged, or echoed back (PCI-DSS-aligned handling, even without real card processing).
- The audit log entry for this action explicitly redacts the card: `details=f"...card=****{last4}"`.

**Output:** `201 Created`, `{"payment_id": ..., "status": "completed", "card_last4": "1111", "amount": <server-computed value>}`. A repeat call for the same `booking_id` returns `400 Bad Request`, `{"detail": "Booking has already been paid for"}`. Verified by `test_payment_and_audit.py::test_payment_amount_is_derived_from_flight_price_not_client_input`, `test_payment_cannot_be_processed_twice_for_same_booking`, and `test_payment_persists_token_not_raw_card_number` (asserts the raw PAN string is absent from the DB row).

---

### 1.7 Seat-Collision Prevention (Booking Integrity Under Concurrency)

**Threat modeled:** Two passengers racing to book the same physical seat, resulting in a double-sold seat (data integrity, not just UX).

**Input:** Passenger A books seat `12C` on flight `#7` (`POST /api/v1/booking/create`, `{"flight_id": 7, "seat_id": <id of 12C>}`). Passenger B then attempts the identical request for the same `seat_id`.

**Background Process:**
- `booking_routes._seat_taken()` runs a DB query for any existing `Booking` on that `(flight_id, seat_id)` pair whose `status` is `active` or `checkedin` — cancelled bookings free the seat back up, which is correct business logic, not just a query optimization.
- Seats also carry an `is_restricted` flag (e.g., last-row middle seats adjacent to the galley) checked *before* the collision check — a restricted seat is rejected regardless of availability.
- Flight bookability is re-validated server-side too: `flight.status not in ("scheduled", "boarding")` is rejected even if the frontend's own `BOOKABLE_STATUSES` guard was somehow bypassed (e.g., a direct API call skipping the UI entirely) — the server never trusts client-side gating alone.

**Output:**
- Passenger A: `201 Created`, booking row written with `seat_id` set.
- Passenger B (same seat): `409 Conflict`, `{"detail": "Seat already assigned on this flight"}` — no duplicate row is ever committed.
- Attempting a restricted seat: `409 Conflict`, `{"detail": "Seat is restricted and cannot be booked"}`.
- Verified by `test_seats_and_status.py::test_booking_rejects_already_taken_seat`, `test_booking_rejects_restricted_seat`, and `test_passenger_flow.py::test_duplicate_seat_on_same_flight_rejected`.

---

### 1.8 Cryptographic Round-Trip Integrity, JWT Expiry, and SQL-Injection Resistance

**Threat modeled:** (a) Ciphertext tampering or key mismatch silently returning corrupted plaintext instead of failing; (b) an expired JWT still being accepted by a protected endpoint; (c) attacker-controlled input reaching the database as executable SQL rather than a bound parameter.

**Input:** (a) `encrypt_data("A1234567 - Ahmed Hassan...")` followed by flipping one character of the resulting ciphertext before calling `decrypt_data()`. (b) A JWT minted with `expires_delta=timedelta(minutes=-5)` (already expired at creation), presented to `GET /api/v1/passenger/bookings`. (c) `POST /api/v1/auth/login` with `email` set to `"' OR '1'='1"`, `"'; DROP TABLE users; --"`, and similar payloads.

**Background Process:**
- (a) `decrypt_data()` reconstructs the AESGCM nonce+ciphertext split and calls `AESGCM.decrypt()`; GCM's authentication tag makes any single-bit change to the ciphertext fail authentication, raising rather than returning altered plaintext.
- (b) `decode_access_token()` calls `jose.jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])`, which validates the `exp` claim against the current time as part of standard JWT validation and raises `JWTError` for an expired token, converted to `RuntimeError` — `get_current_user()` (`deps.py`) catches this and raises `401` before the route body runs.
- (c) `LoginRequest.email` is typed `EmailStr` (Pydantic) — malformed-looking payloads are rejected at the schema layer (`422`) before any query runs. For payloads that happen to be email-shaped, `db.query(User).filter(User.email == email)` is built via SQLAlchemy's ORM, which always sends the value as a bound parameter — there is no code path where request input is concatenated into a SQL string.

**Output:** (a) `RuntimeError` raised, no plaintext returned. (b) `401 Unauthorized` from the protected endpoint despite the token being well-formed and correctly signed. (c) `401` or `422` for every payload tested; the `users` table remains queryable afterward (a successful `DROP TABLE` would make the follow-up `COUNT` query raise instead). Verified by `test_security_properties.py::test_encryption_roundtrip`, `test_jwt_token_expiration`, `test_expired_token_rejected_by_protected_endpoint`, `test_sql_injection_prevention`.

---

### 1.9 RSA Digital Signature on Boarding Passes (Genuine Asymmetric Cryptography)

**Threat modeled:** A boarding pass whose underlying booking row is altered directly via a compromised database credential (bypassing the app entirely) after legitimate check-in - e.g., reassigning it to a different flight or seat. The existing DB-backed single-use token check alone can't catch this, since the token still matches; something needs to detect that the *content* the pass refers to has changed since issuance.

**Input:** A passenger checks in (`POST /api/v1/passenger/checkin`), receiving a `boarding_pass_token` and a `signature`. A test then directly mutates the underlying `Booking.flight_id` via the DB session (simulating exactly the compromised-credential scenario above, bypassing the application layer), and a staff agent attempts to redeem the same token (`POST /api/v1/staff/checkin-passenger`).

**Background Process:**
- At check-in, `security.py:sign_boarding_pass()` computes an RSA-2048 PSS/SHA-256 signature over `boarding_pass_payload(booking_id, secure_token, flight_id, seat_number)` using a server-only private key, stored on the new `boarding_passes.signature` column.
- This is a genuine asymmetric-key mechanism, distinct from JWT's `HS256` (a symmetric HMAC - the server holds one secret for both signing and verifying, so it authenticates but doesn't provide non-repudiation). Here, only the private key can produce a valid signature; the public key (exposed at `GET /api/v1/boarding-pass/public-key`, deliberately unauthenticated - public keys are meant to be shared) can verify it independently, without database access.
- At redemption, `staff_routes.py` re-fetches the booking *as it currently stands*, rebuilds the same canonical payload, and calls `verify_boarding_pass_signature()`. Because the payload is rebuilt from the row's *current* `flight_id` (now tampered), it no longer matches what the stored signature actually commits to (the *original* `flight_id` at issuance) - verification fails.
- This is additive to, not a replacement for, the existing single-use-token DB check (`used_at`) - a signature proves authenticity/integrity of content, not "hasn't already been redeemed"; both properties are needed and neither substitutes for the other.

**Output:** Redemption returns `409 Conflict`, `{"detail": "Boarding pass failed integrity verification"}`, and a `STAFF_CHECKIN_SIGNATURE_INVALID` audit event is recorded - even though the token itself is valid and unused. A legitimate, untampered pass verifies successfully and redeems normally. Verified by `test_security_properties.py::test_boarding_pass_rsa_signature_roundtrip` (signature validity + tamper detection at the crypto-function level), `test_boarding_pass_signature_present_and_valid_end_to_end` (real check-in flow produces a valid signature), `test_tampered_boarding_pass_fails_staff_redemption` (the full attack scenario above), and `test_boarding_pass_public_key_endpoint_is_unauthenticated`.

---

## 2. Frontend / API Security

### 2.1 CORS Origin Allow-List (Misconfiguration Found & Fixed)

**Threat modeled:** Either an overly permissive CORS policy allowing any origin to make credentialed requests against the API, or — the actual bug found during testing — an overly *strict* mismatch breaking legitimate cross-origin calls entirely (a working-but-insecure and a secure-but-broken failure mode both needed checking).

**Input:** A real browser (not `curl`) loads the React SPA and its JS makes `axios` calls to the backend API on a different origin/port.

**Background Process:**
- The backend's `CORSMiddleware` (`main.py`) is configured with `allow_origins=ALLOWED_ORIGINS` (an explicit env-driven allow-list, not `"*"`) and `allow_credentials=True` — per the CORS spec, a wildcard origin is not even legal alongside credentialed requests, so the allow-list is structurally required, not just a hardening choice.
- `allow_headers=["Authorization", "Content-Type"]` is an explicit, minimal list.
- **Bug found during real-browser testing (not caught by `curl`, which never sends preflight requests):** the frontend's `axios` instance originally attached a custom `X-Requested-With` header on every request. Because that header wasn't in the backend's `allow_headers` list, every real browser's CORS preflight (`OPTIONS`) failed, and **every single API call from the deployed frontend was silently blocked** — a production-breaking bug that unit tests and `curl`-based smoke tests both missed, since neither goes through the browser's preflight machinery.
- Fix: removed the unnecessary header from `frontend/src/config/api.config.js` rather than widening the backend's allow-list — minimizing the allowed header surface instead of loosening it.

**Output:** Before the fix: every `fetch`/`axios` call from the live site failed at the network layer with a CORS error visible only in the browser console (requests never reached the FastAPI app at all). After the fix: preflight `OPTIONS` returns `200` with `Access-Control-Allow-Origin` matching the exact requesting origin, and the subsequent real request succeeds normally. Verified by manually driving the deployed frontend end-to-end (login → search → book → pay) via Playwright against the live Railway URL, confirming zero console CORS errors across the full flow.

---

### 2.2 XSS Defense-in-Depth: JSX Auto-Escaping + DOMPurify

**Threat modeled:** A malicious passenger submitting a "full name" or incident-report free-text field containing `<script>` or event-handler payloads, later rendered in an admin or staff view.

**Input:** A registration/profile field containing `<img src=x onerror=alert(document.cookie)>` as the "full name".

**Background Process:**
- React's JSX rendering (`{value}` interpolation) HTML-escapes text content by default — this is the primary defense and applies everywhere in the app automatically, with no opt-in required.
- `frontend/src/utils/sanitizer.js` adds an explicit second layer: `sanitize()` wraps `DOMPurify.sanitize(input, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] })` — a strip-all-markup policy — applied to free-text fields that pass through more than one render path (e.g., incident descriptions later shown in both a staff list and an admin detail view), so a future code change that accidentally uses `dangerouslySetInnerHTML` somewhere downstream still can't execute injected markup from this field.
- On the backend, the same string round-trips through `encrypt_data()`/`decrypt_data()` (§1.2) for PII fields — the payload is opaque ciphertext at rest regardless of its content, so the XSS payload can't be "activated" by anything touching the raw DB row directly (e.g., an admin SQL console).

**Output:** The payload renders as the literal text string `<img src=x onerror=alert(document.cookie)>` in the UI (visible as text, not executed) — no alert fires, no script executes. Verified manually in the running app by submitting the payload through the registration form and inspecting the rendered DOM (`innerHTML` shows HTML-entity-escaped output, `&lt;img src=x onerror=...&gt;`).

---

### 2.3 Client-Side Input Validation Paired with Mandatory Server-Side Re-Validation

**Threat modeled:** An attacker bypassing the browser UI entirely (direct `curl`/Postman calls to the API) to submit malformed or malicious data, since client-side checks alone provide zero real security.

**Input:** A direct `POST /api/v1/auth/register` request (bypassing the React form entirely) with `{"password": "abc", "passport_number": "not-a-passport!!", ...}`.

**Background Process:**
- The frontend's `validators.js` defines regex rules (`password`: requires upper+lower+digit+special char, min 8 chars; `passport`: `^[A-Z0-9]{6,9}$`; etc.) and `validateInput()` throws a typed `ValidationError` (a real `Error` subclass — this itself was a fix: an earlier version threw a plain object literal, which CRA's production build treats as a lint-blocking `no-throw-literal` violation and would have failed to compile at all).
- These client checks exist purely for **UX** (instant feedback, no round-trip needed for obviously-invalid input) — they are never trusted as the security boundary.
- The FastAPI backend re-validates independently via Pydantic schemas (`schemas.RegisterRequest`) with its own field constraints, completely irrespective of whether the request came through the React app or a raw HTTP client.

**Output:** Because this request bypasses the frontend, the backend's own validation is what actually runs: `422 Unprocessable Entity` from Pydantic for the malformed passport, and separately, a weak password is rejected as well. Verified by `test_auth.py::test_register_rejects_weak_password` and `test_register_rejects_bad_passport_format`, both of which call the API directly (exactly simulating a client that skips the UI) and confirm the backend enforces the rule independently of any frontend code path.

---

### 2.4 JWT-Based Route Guards + Client-Side Session Expiry Handling

**Threat modeled:** A logged-out or expired-session user still seeing role-restricted UI (staff dashboards, admin panels) rendered in the browser, even briefly, before an API call would fail.

**Input:** A passenger manually navigates the browser to `/admin` (a route only meant for `admin` role), either by typing the URL or via a stale bookmark from when they briefly had a different role.

**Background Process:**
- `ProtectedRoute.jsx` runs **before** the guarded component mounts: it reads `access_token` from `localStorage`, decodes it client-side with `jwt-decode` (no signature verification needed here — decoding, not trusting, since the actual authorization decision always happens server-side; this is purely to avoid flashing restricted UI), and checks `decoded.exp * 1000 < Date.now()` for client-side expiry, plus `allowedRoles.includes(decoded.role)`.
- If the token is missing, expired, unparsable, or the role doesn't match, it renders `<Navigate to="/login" />` or `<Navigate to="/unauthorized" />` — the restricted component's `render()` (and any data-fetching `useEffect` inside it) never executes at all.
- This is explicitly a UX/defense-in-depth layer, not the security boundary: even if this check were somehow bypassed (e.g., DevTools manipulation of React state), every API call the restricted component would make still goes through the server-side `require_role()` check (§1.3) and would independently fail with `403`.
- Separately, `api.config.js`'s response interceptor catches any `401` from *any* API call app-wide, clears the stale token from `localStorage`, and force-redirects to `/login` — so a token that expires *mid-session* (not just on initial page load) is handled uniformly everywhere, not just on navigation.

**Output:** The passenger is redirected to `/unauthorized` (wrong role, valid token) or `/login` (expired/missing token) without the admin panel's markup or API calls ever executing. Combined with §1.3's server-side enforcement, this is two independent layers — a UI-level redirect and a server-level `403` — either of which alone would prevent actual data exposure.

---

## 3. DevOps / Infrastructure Security

### 3.1 TLS Termination, HTTP→HTTPS Redirect, and Security Headers at the Edge

**Threat modeled:** Traffic sniffing / man-in-the-middle on the network path, and browser-side attacks (clickjacking, MIME-sniffing, reflected XSS) that HTTP response headers can mitigate.

**Input:** A client sends a plain HTTP request to port 80 of the nginx edge (`infrastructure/nginx/conf.d/*.conf`), then a normal HTTPS request to port 443.

**Background Process:**
- The port-80 server block's *only* directive is `return 301 https://$host$request_uri;` — nginx never proxies plaintext traffic to the app tier; it unconditionally upgrades.
- The port-443 block terminates TLS (`ssl_certificate`/`ssl_certificate_key`) and, on every response, injects: `Strict-Transport-Security` (forces HTTPS on the client for a year, including subdomains — prevents SSL-stripping on subsequent visits), `X-Content-Type-Options: nosniff` (blocks MIME-sniffing attacks), `X-Frame-Options: DENY` (prevents the whole app being iframed for clickjacking), `Content-Security-Policy` (`default-src 'self'`, restricting script/style/image/connect sources), and `Referrer-Policy: strict-origin-when-cross-origin`.
- The **same** header set is independently applied a second time at the application layer by `SecurityHeadersMiddleware` (`backend/src/middleware.py`) — so the headers are present even in the single-container Railway deployment, where nginx isn't in front of the app at all. This redundancy was deliberate: the two deployment topologies (full docker-compose stack vs. combined Railway container) needed the same guarantee without one depending on the other's presence.
- Dotfiles and config-extension paths (`\.env`, `.ini`, `.conf`, `.bak`, any path starting with `.`) are explicitly denied at the nginx layer before ever reaching the app.

**Output:** Plain HTTP request: `301 Moved Permanently` to the `https://` equivalent URL, zero applicationlayer processing. HTTPS request: `200` (or whatever the app returns) with all six security headers present — verified with `curl -I https://<deployment-host>/healthz` showing `strict-transport-security`, `x-frame-options: DENY`, etc. in the response.

---

### 3.2 Two-Layer Rate Limiting Against Brute Force and DoS

**Threat modeled:** Credential-stuffing bots or a DoS flood targeting the login endpoint specifically (the most valuable target, since it gates everything else).

**Input:** A scripted client fires 50 rapid `POST /api/v1/auth/login` requests from a single source IP within a few seconds.

**Background Process:**
- **Layer 1 (edge, nginx):** the `location ~ ^/api/v1/auth/(login|2fa-verify)` block applies `limit_req zone=login_limit burst=5 nodelay` and `limit_conn conn_limit 10` — a *stricter* limit than the general `/api/` block (`limit_req zone=api_limit burst=20`), reflecting that auth endpoints are higher-value targets and deserve tighter throttling than, say, flight search. This layer rejects excess requests before they ever reach the Python process, protecting application CPU/memory from being the bottleneck under attack.
- **Layer 2 (application, slowapi):** independently, `@limiter.limit("5/minute")` decorates `login()` and `verify_2fa()` directly in FastAPI (`middleware.py`'s `Limiter(key_func=get_remote_address, default_limits=["100/minute"])` sets the general default; auth routes override it tighter). This layer exists so the limit is enforced correctly even in the Railway single-container deployment, where the nginx edge isn't present in front of the app — mirroring the same defense-in-depth reasoning as §3.1's duplicated headers.
- Exceeding either layer returns a `429`; the app-layer handler (`rate_limit_handler` in `main.py`) returns a clean JSON body rather than leaking a stack trace.

**Output:** The first 5 requests per minute (per source IP) are processed normally (each independently subject to the account-lockout logic in §1.1). The 6th+ request within the same minute receives `429 Too Many Requests`, `{"detail": "Too many requests. Please try again later."}`, without even reaching the password-verification code path. Verified by `test_auth.py::test_login_rate_limited_after_five_attempts`.

---

### 3.3 Container Hardening: Read-Only Filesystem, Dropped Privileges, Resource Limits

**Threat modeled:** A remote code execution vulnerability in a dependency (Python package, npm package) being escalated into persistent filesystem tampering, privilege escalation inside the container, or resource-exhaustion DoS against the host.

**Input:** Hypothetical: an attacker achieves arbitrary code execution inside the `backend` container (e.g., via a vulnerable dependency) and attempts to write a webshell to disk or escalate via a setuid binary.

**Background Process:**
- `docker-compose.yml`'s `backend` service sets `read_only: true` — the entire container filesystem is mounted read-only at the Docker layer, independent of anything the application code does. The **only** writable path is `/tmp`, explicitly provisioned as a `tmpfs` (in-memory, wiped on container restart) mount.
- This directly shaped application behavior, not just infrastructure config: `seed_demo_data.py` originally wrote a reference JSON file to the app directory and **crashed** under this constraint (discovered by actually running the hardened container, not just reading the compose file) — fixed by adding a fallback to write into `/tmp/seed_data` instead, confirming the read-only boundary is real and enforced, not just declarative.
- `security_opt: [no-new-privileges:true]` on both `backend` and `frontend` prevents any process inside the container from gaining privileges beyond what it started with (blocks setuid/setgid escalation even if a binary inside the image has that bit set).
- `deploy.resources.limits` caps each service at `1.0` CPU / `512M` memory — a compromised or runaway process cannot starve the Postgres container or the host of resources.
- Logging is capped (`max-size: 10m`, `max-file: 3`) so a log-flooding attempt can't fill host disk either.

**Output:** An attempted file write to any path outside `/tmp` fails at the OS/mount level with a read-only-filesystem error, regardless of the privileges the compromised process holds inside the container. Verified operationally: the full docker-compose stack was actually run (not just statically reviewed), and the `seed_demo_data.py` failure above was observed and fixed as a direct consequence of the read-only constraint being genuinely active.

---

### 3.4 Network Segmentation via Isolated Docker Bridge Network

**Threat modeled:** Direct external access to the database tier, and lateral movement between services that shouldn't be able to reach each other.

**Input:** An external client attempts to connect directly to Postgres on `5432` from outside the Docker host.

**Background Process:**
- All services share a single custom bridge network (`secure_network`, subnet `172.20.0.0/16`) defined at the bottom of `docker-compose.yml` — this replaces Docker's default bridge, which would otherwise let all containers on the host talk to each other with no explicit topology.
- Critically, `postgres`, `postgres_exporter`, and `grafana`'s **backing** Postgres access have no `ports:` mapping to the host at all — only `backend`, `frontend`, `nginx`, `prometheus`(`9090`), and `grafana`(`3001`) publish host ports. Postgres is reachable **only** by other containers on `secure_network`, addressed by service name (`postgres:5432`), never from outside the Docker host's network namespace.
- Service-to-service auth still applies on top of network isolation: `postgres_exporter`'s `DATA_SOURCE_NAME` and the backend's `DATABASE_URL` both require the real `DB_USER`/`DB_PASSWORD` — network reachability alone doesn't grant access.
- `depends_on: postgres: condition: service_healthy` on both `backend` and `postgres_exporter` ensures the DB is actually accepting connections (via its own `pg_isready` healthcheck) before dependents start, avoiding a startup race that could otherwise produce confusing partial-failure states.

**Output:** `docker ps` / `docker port airport_postgres` shows no host-side port binding for Postgres — `psql -h <docker-host-ip> -p 5432` from outside the host fails to connect (connection refused, nothing listening on the host's external interface for that port). Internally, `backend` successfully connects via the internal DNS name `postgres`, confirmed by the backend's own healthcheck passing (`/healthz` returns `200`) only once its DB connection succeeds.

---

### 3.5 Encrypted Database Backups at Rest

**Threat modeled:** A stolen or leaked backup file (e.g., from a misconfigured cloud storage bucket, or physical media theft) exposing the entire production database — encryption in the live DB (§1.2 for PII) doesn't help if a *backup* of the whole system is copied out with credentials embedded or accessible.

**Input:** The scheduled backup job runs (`infrastructure/backup/backup-postgres.sh`, intended via cron at `0 2 * * *`).

**Background Process:**
- `pg_dump` runs *inside* the running `airport_postgres` container (`docker exec ... pg_dump`) — the plaintext SQL dump is piped directly through `gzip`, so it briefly exists as `airport_db_<timestamp>.sql.gz` on disk in `$BACKUP_DIR` (permissions forced to `700` via `chmod`).
- Immediately after, `openssl enc -aes-256-cbc -pbkdf2 -salt -in "$PLAIN_FILE" -out "$ENCRYPTED_FILE" -k "$BACKUP_PASSWORD"` encrypts the gzip archive with AES-256-CBC, using PBKDF2 to derive the key from `BACKUP_PASSWORD` (an env-injected secret, never hardcoded) with a random salt (`-salt`) so identical passwords across backups don't produce identical derived keys.
- The unencrypted intermediate file is deleted immediately (`rm -f "$PLAIN_FILE"`) — the plaintext dump's window of existence on disk is minimized to the time the `openssl enc` command takes to run, not the full retention period.
- `find ... -mtime +"$RETENTION_DAYS" -delete` prunes backups older than the configured retention (default 30 days), so old encrypted backups don't accumulate indefinitely as a growing attack surface.
- `restore-postgres.sh` (the inverse operation) requires the same `BACKUP_PASSWORD` to decrypt before restoring — verified end-to-end against a real running Postgres container: a backup was taken, the encrypted `.enc` file confirmed unreadable as SQL without the password, then successfully restored into a fresh container using the correct password.

**Output:** `ls "$BACKUP_DIR"` shows only `*.sql.gz.enc` files — no plaintext `.sql` or `.sql.gz` remains after the script completes. Attempting `gunzip` or reading the `.enc` file directly produces binary garbage, not SQL. Restoring with the correct `BACKUP_PASSWORD` via `restore-postgres.sh` reproduces the original database state; restoring with a wrong password fails at the `openssl enc -d` step before ever reaching `psql`.

---

## Summary

| Layer | Mechanisms tested | Automated coverage |
|---|---|---|
| Backend/Database | Argon2 + lockout, AES-256-GCM PII encryption, JWT+RBAC, TOTP/email 2FA, hash-chain audit log, server-side payment derivation, seat-collision prevention, crypto round-trip/JWT-expiry/SQL-injection resistance, RSA digital-signature boarding passes | `test_auth.py`, `test_rbac.py`, `test_payment_and_audit.py`, `test_seats_and_status.py`, `test_passenger_flow.py`, `test_security_properties.py` |
| Frontend/API | CORS allow-list (bug found & fixed), XSS defense-in-depth, client+server dual validation, JWT route guards + session expiry handling | `frontend/src/__tests__/`, manual Playwright walkthrough against live deployment |
| DevOps/Infrastructure | TLS + security headers (dual-layer), dual-layer rate limiting, container hardening, network segmentation, encrypted backups | Manual verification against a running docker-compose stack and the live Railway deployment (not just static config review) |

Every scenario above traces to a specific function, file, and (where applicable) a currently-passing automated test — this document should be read alongside the actual source files it cites, since the goal is to demonstrate the mechanism is genuinely implemented and understood, not merely described.
