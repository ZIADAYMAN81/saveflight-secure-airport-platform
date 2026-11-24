# Frontend / API Security

## Design

The frontend's security job is narrower than the backend's, and it's important to be precise about that: **nothing the client does is a security boundary** — every check in the React app exists to give a legitimate user a fast, clear experience (don't let them click into booking a landed flight, redirect them before a restricted page even renders, show a validation error before a round-trip), while the actual enforcement always happens again, independently, on the server. The design goal was defense-in-depth without confusing UX-layer checks for security-layer checks: a passenger manually navigating to `/admin` should be redirected instantly (good UX), but even if that redirect were somehow bypassed, the API calls the admin page would make still fail server-side with `403` — the frontend check is a convenience, not a control.

## Component / API Specification

A single-page app (Create React App, React Router) with one configured `axios` instance (`config/api.config.js`) as the sole gateway to the backend — token attachment, base URL, and centralized 401-handling (auto-logout + redirect) all live in exactly one place, so there's no risk of a component forgetting to attach the auth header or forgetting to handle an expired session. `ProtectedRoute.jsx` wraps every role-restricted route: it decodes (not verifies — decoding is enough here, since the actual trust decision is server-side) the JWT client-side via `jwt-decode`, checks expiry against `Date.now()`, and checks the role claim against an `allowedRoles` list before the guarded component ever mounts. `Layout.jsx` renders navigation conditionally by role, so a passenger never even sees a staff/admin nav item to begin with.

## Security Implementation

Three layers work together. **CORS** is configured on the backend with an explicit origin allow-list (never a wildcard, which wouldn't even be legal alongside `allow_credentials=True` per the CORS spec) and a minimal `allow_headers` list — this actually surfaced a real production bug during testing: the frontend's `axios` instance originally sent a custom `X-Requested-With` header that wasn't in the backend's allow-list, so every real browser's CORS preflight silently failed, blocking every API call from the deployed frontend. `curl`-based smoke testing never caught this, because `curl` doesn't perform CORS preflight the way a browser does — it was only caught by actually driving the deployed frontend in a real browser. The fix was to remove the unnecessary header rather than widen the backend's allow-list, keeping the allowed surface minimal.

**XSS defense-in-depth**: React's JSX auto-escaping is the primary defense and requires no opt-in, but `utils/sanitizer.js` wraps `DOMPurify.sanitize(input, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] })` as an explicit second layer for free-text fields that get rendered in more than one place (boarding pass passenger name, staff incident reports) — this is actually called (not dead code) in `BoardingPass.jsx` and `StaffDashboard.jsx`, verified by grep. A strict `Content-Security-Policy` (`script-src 'self'`) backstops both.

**Client + mandatory server-side re-validation**: `utils/validators.js` defines the same shape of rules (password strength, passport format, email, phone) that the backend's Pydantic schemas enforce independently — the client-side copy exists purely for instant UX feedback, and every rule is proven to also be enforced server-side by tests that call the API directly, bypassing the React form entirely (simulating exactly the attacker who skips the UI).

A real bug found and fixed during this project: the flight search UI originally let a user click "Select Flight" and proceed into the booking flow for a flight that had already landed or departed, only to be rejected at the final payment step — wasted effort, not a security hole, but bad UX that also revealed the UI wasn't checking a state the backend already enforced. Fixed by adding a `BOOKABLE_STATUSES` guard in both the search list (disables the button, shows "Not bookable") and the booking form itself (guards direct URL navigation to `/book/:flightId` too, not just the button).

## Testing Approach and Results

60 Jest/React Testing Library tests across 8 suites, covering: `ProtectedRoute` (expired/malformed/missing token, wrong role — each a distinct test, not one generic "auth check"), `Login`/`Register` (validation errors, lockout/rate-limit response handling, successful-login redirect), `FlightSearch`/`BookingForm`/`SeatMap` (search filtering, seat selection state, 409 seat-conflict handling sending the user back to seat selection), and `StaffDashboard` (role-conditional rendering — confirms agent tools are hidden for crew role, etc.). Tests render real components against a mocked API layer (mocking the network boundary, not the security logic itself) so the actual validation/redirect logic under test is the real code, not a stand-in.

## Setup & Deployment

```bash
cd frontend && npm install
copy .env.example .env
npm start
```
Production build: `npm run build`. See `docs/DEPLOYMENT.md` for how the built assets are served (standalone via nginx in the Docker Compose stack, or bundled into the same container as the backend for the Railway deployment).
