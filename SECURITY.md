# Security notes

What changed from the original MVP, and why. Written so a future reader (or
future you) doesn't have to reverse-engineer the reasoning from diffs.

## Fixed

**Admin privilege escalation.** The original app granted admin access to
whichever user account was created first, as a fallback when no `ADMIN_EMAIL`
was configured. On a public-signup app, that means anyone who registers first
on a misconfigured deployment gets full platform access -- including
impersonating any business owner. Fixed: admin status now comes *only* from
`ADMIN_EMAIL`/`ADMIN_PASSWORD` seeding at startup, or from an existing admin
promoting someone via the admin panel. There is deliberately no bootstrap
fallback. See `backend/auth.py:seed_admin` and `backend/routers/admin.py:_ensure_admin`.

**JWT stored in localStorage.** The frontend was persisting the session token
in `localStorage` on every login/signup, in addition to the httpOnly cookie the
backend already set. `localStorage` is readable by any JS on the page, which
defeats the point of an httpOnly cookie (specifically designed to survive XSS).
Fixed: normal login/signup no longer returns the raw token in the response
body at all -- the cookie is sufficient. The one deliberate exception is admin
impersonation, which needs a token the frontend can hand off in the same tab;
that flow is authenticated, audited, and narrow. See `backend/routers/auth.py`
and `frontend/src/lib/api.js`.

**Unauthenticated public endpoints with no rate limit.** `/chat` and
`/chat/handoff` took unlimited requests from anyone, with no auth -- an open
door for cost-abuse (every message triggers a paid Gemini call) and basic
scripted flooding. Fixed: `slowapi` rate limiting on `/chat` (30/min),
`/chat/handoff` (10/min), `/auth/login` (10/min), `/auth/signup` (10/hour),
and `/owner-chat/ask` (20/min). In-memory by default; set `REDIS_URL` if you
run multiple backend replicas (see DEPLOYMENT.md).

**Billing bug: usage never reset monthly.** `monthly_used` was incremented on
every chat but nothing ever reset it -- a business that hit its plan limit
stayed locked out forever until an admin manually intervened. Fixed with a
lazy rollover (`backend/usage.py`): usage resets automatically the first time
a business is read or incremented after its billing month changes. No cron
needed.

**Billing bug: refunding an invoice didn't downgrade the plan.** An admin
refunding a payment left the business on the paid plan indefinitely. Fixed --
`refund_invoice` now downgrades to Free, matching what the Razorpay webhook's
`refund.processed` handler already did.

**Payments were entirely mocked.** `/billing/subscribe` just flipped the plan
in the database with no real charge. Replaced with real Razorpay order
creation, signature verification (`/billing/verify`), and a webhook handler
(`payment.captured`/`payment.failed`/`refund.processed`) as a safety net for
browser-closed-mid-checkout cases.

**Undisclosed third-party session recording.** `index.html` loaded a hardcoded
PostHog key pointed at the platform vendor's own analytics project, with
`recordCrossOriginIframes: true` -- meaning every deployment silently recorded
user sessions *including inside the embedded customer-facing widget iframe*,
sent to a third party neither the business owner nor their customers knew
about or consented to. Removed entirely.

**Proprietary LLM/storage proxy.** The app routed every Gemini call and every
file upload through a platform vendor's proxy service (`emergentintegrations`,
requiring a vendor-issued key), rather than talking to Google/S3 directly. This
meant paying a middleman markup and depending on a vendor-specific SDK that
isn't on public PyPI. Replaced with direct `google-genai` calls (your own
`GEMINI_API_KEY`) and standard S3-compatible storage via `boto3` (works with
AWS S3, Cloudflare R2, Backblaze, MinIO -- your own keys).

**Widget embed blocked clicks on the host site.** The original server-generated
loader (`/api/widget/loader.js`) created a permanently-sized 420x680px iframe on
the business's site regardless of whether the chat was open or just showing the
small bubble -- silently swallowing clicks in that entire bottom-right region of
the host page even while the widget was closed, since `pointer-events` inside an
iframe's own document can't selectively "pass through" clicks to the parent page
around it. Replaced with a static loader (`frontend/public/embed.js`) that starts
at bubble-size (96x96px) and resizes via `postMessage` only when the widget
actually needs more space (a teaser bubble, or the open chat window) -- see
`ChatWidget.jsx`'s `reportSize`. The old server-rendered route is removed.

## Fixed in the follow-up pass

**No password reset.** Signup/login only -- anyone locked out of their account
had no way back in. Added `/auth/forgot-password` and `/auth/reset-password`,
using a JWT with its own `type: password_reset` claim and a 30-minute expiry.
`get_current_user` now explicitly checks `type == "access"`, so a leaked
reset (or email-verify, or MFA-pending) token can never be replayed as a
login session -- previously `decode_token` didn't check token type at all.

**No email verification.** Any email was accepted at face value with nothing
confirming the owner actually controls it. Added a verify-email flow (sent on
signup, resendable from a dashboard banner); unverified accounts are nudged,
not blocked, since hard-blocking felt too aggressive for existing users on an
upgrade.

**Admin accounts had no MFA option.** Given impersonation is available to any
admin, added TOTP-based two-factor: `/admin/mfa/setup` → scan or manually
enter the key → confirm a code → enabled. Login for an MFA-enabled admin now
returns `mfa_required` + a short-lived pending token instead of a session,
and a session is only issued after `/auth/mfa/verify` confirms the code.
Not force-enabled (would risk locking out a freshly-seeded admin before
they've set it up) -- available and strongly recommended instead.

**Admin-configurable settings didn't do anything.** The admin panel had a
full settings UI (confidence threshold, upload size cap, crawl page limit,
per-plan chat limits, a maintenance-mode toggle, a "require branding on
free plan" toggle) that saved to Mongo -- but nothing outside the admin panel
ever read those values back. Changing them in the UI silently had zero
effect; `chat.py`, `knowledge.py`, `businesses.py`, and `billing.py` all used
their own hardcoded constants instead. Added `platform_settings.py` as the
one shared reader, and wired every one of those hardcoded spots to use it.
`maintenance_mode` now actually returns a friendly "back soon" message from
`/chat` instead of doing nothing.

**Branding removal wasn't actually enforced.** A Free-plan business (or its
owner-chat AI, via `update_widget`) could set `show_branding: false` and the
badge would simply disappear -- nothing re-checked plan on the read side.
Fixed at the one place the widget actually fetches its config from
(`GET /chat/business/{id}/widget-config`), gated by the platform's
(admin-configurable) `watermark_required_on_free` setting.

**The business's configured language was collected but never used.** Selected
at onboarding, shown to the owner's own AI assistant, but never passed into
the customer-facing prompt -- the AI just replied in whatever language Gemini
defaulted to. Now injected into `rag_answer()`'s system prompt.

**No way to tag a conversation as a lead/booking/lost sale.** The backend
endpoint existed from the previous pass but had no button anywhere in the
UI. Added outcome-tagging controls to the Conversations page.

## Fixed in the enterprise auth pass

**Single 7-day token, no revocation.** The original session model was one JWT,
valid for 7 days, with no way to end a specific session early short of
waiting out the expiry or invalidating everyone's secret -- no visibility
into which devices were signed in, no way to sign out a stolen device
without also nuking every other session, and no refresh path to begin with.
Replaced with a standard access+refresh model: a short-lived (30-minute)
access token plus an opaque, server-tracked refresh token that rotates on
every use. Sessions live in `db.sessions` with device/IP metadata, so an
owner can see every signed-in device (Settings → Security) and revoke one or
all of them independently. Rotation includes reuse detection -- replaying an
already-rotated-away refresh token (a strong signal of token theft) revokes
the session immediately instead of silently accepting it. See
`backend/sessions.py` and `backend/routers/auth.py`.

**No brute-force protection on login.** `authenticate()` accepted unlimited
password guesses against a single account (the existing `/auth/login` rate
limit was per-IP, not per-account -- a distributed attempt would sail
through). Added an admin-tunable lockout: after `max_failed_login_attempts`
(default 5) consecutive failures, the account locks for `lockout_minutes`
(default 15), independent of IP. Successful login clears the counter.

**No visibility into sign-ins.** Added login history (`/auth/login-history`)
recording every attempt -- success, wrong password, lockout, MFA required/
failed -- with device and IP, plus a new-device email alert the first time a
login is seen from a device never used on that account before. This is
device-based, not geo/IP-based -- see "Still worth doing" below.

**MFA was admin-only.** Two-factor was wired up for admin accounts in the
previous pass but had no equivalent for business owners, even though an
owner's account holds customer data, billing, and the live widget on their
site. Setup/enable/disable logic is now shared (`auth.py`'s
`mfa_setup_for`/`mfa_enable_for`/`mfa_disable_for`) between `/admin/mfa/*`
(unchanged, backward compatible) and the new `/auth/mfa/*`, open to every
account.

**No way for a business's own systems to call the API.** Everything required
a logged-in browser session. Added Business API Keys (`backend/api_keys.py`,
`routers/api_keys.py`) scoped to a fixed permission vocabulary
(`business:read`, `appointments:read/write`, `conversations:read`,
`analytics:read`), shown once at creation/rotation and stored only as a
SHA-256 hash afterward, with a per-key configurable rate limit and usage
logging. Backed by a small external surface (`routers/public_api.py`,
`/api/v1/...`) that reuses `booking.py` and `analytics.py` rather than
re-implementing them -- an API key gets no special trust the browser-session
booking flow doesn't already enforce. A key can only ever act on the one
business it was created for (`test_api_key_cannot_be_created_for_someone_elses_business`).

**Password reset didn't end other sessions.** Resetting a password left every
existing session valid -- exactly the scenario where you'd want the
opposite, whether the reset happened because the account was compromised or
because the owner is deliberately locking out a stolen session.
`reset-password` now revokes every other session.

**Caught in testing, not shipped: revoking a session didn't actually revoke
it.** An early version of this pass only checked session validity when the
refresh token was used, so a "sign out this device" click had no visible
effect until that device's access token happened to expire naturally (up to
30 minutes later). `get_current_user` now checks server-side revocation on
every request for tokens carrying a session id.

**Also caught in testing: the scheduler crashed on a second app lifespan in
the same process.** `start_scheduler()`/`stop_scheduler()` weren't
idempotent -- a second startup (two `TestClient`s against the same app in one
test, or certain ASGI reload scenarios) silently replaced the module-global
scheduler without stopping the first, and a later shutdown on the
by-then-already-stopped scheduler raised `SchedulerNotRunningError` instead
of no-op'ing. Fixed to check `.running` before acting either way.

**Also caught in testing: knowledge chunking silently dropped short
entries.** Any manually-typed knowledge entry, or short crawled/uploaded
document, whose *entire* text was 40 characters or fewer produced zero
chunks with no error -- the 40-char floor was meant to trim a tiny leftover
tail fragment from splitting a long document, not reject short inputs
outright. An owner typing a short quick fact ("We're open Sundays too.") got
silent data loss with a 200 OK response. Fixed to only trim a tail fragment
when there's more than one chunk.

**Also caught in testing: rate-limiter state leaked across test runs.**
Unrelated to production behavior, but worth noting: the backend test suite
was flaky -- `slowapi`'s in-memory limiter is a module-level singleton not
reset between tests, so per-IP counters (e.g. `10/hour` on signup)
accumulated across the whole suite and started failing unrelated later tests
once enough requests had been made in aggregate. Fixed by resetting it (and
the API-key rate limiter) in the test fixture alongside the fake DB.

## Fixed in the GST billing, appointments, and reporting pass

**A dangerous duplicate refund endpoint.** `/admin/invoices/{id}/refund` only flipped a
database status flag to "refunded" -- it never called Razorpay. An admin using it would
have believed a customer was refunded while their money never moved. Found while wiring up
the reporting pass, not while touching billing directly. Now delegates to the real refund
flow (`routers/billing.py`), which actually calls Razorpay's refund API and handles
GST-aware partial refunds, instead of a second, incorrect implementation of the same thing.

**Referral rewards re-fired on every purchase, not just the first.** The reward filter
didn't exclude already-rewarded referrals, so a referrer would be "rewarded" (and, once the
email was wired up, re-emailed) on every subsequent purchase by the same referred business
-- an upgrade, a renewal, anything -- not just the intended first conversion. Fixed the
filter to be idempotent.

**The test double didn't support MongoDB's dot-notation for nested updates.** `{"$set":
{"legal_acceptances.privacy_policy": 1}}` is standard, idiomatic Mongo for a nested field
update; the fake DB was treating the dotted string as a literal flat key instead of nested
path notation. The application code was correct against real MongoDB the whole time -- this
was a gap in the test double's fidelity, caught because the acceptance-tracking feature's
own tests failed against it. Fixed to interpret dot-notation like real MongoDB does.

**Booking times were always interpreted as UTC, regardless of the business's actual
timezone.** `Business.timezone` existed as a field (settable at signup) but was never once
read by the booking logic -- a business in India with 9am-5pm hours was actually bookable
9am-5pm *UTC* (2:30pm-10:30pm IST), silently wrong for every non-UTC business on the
platform. Rewrote `booking.py` to interpret working hours in the business's own timezone
(stdlib `zoneinfo`, no new dependency) and convert to UTC only for storage/comparison.

**A proration bug that would have overcharged every upgrade.** The first version of the
mid-cycle upgrade formula charged the full new-plan price *plus* the prorated top-up,
nearly double-charging. Caught by a test asserting the charged amount stayed under the full
price, not just "some proration was applied" -- see `test_upgrade_mid_cycle_is_prorated`.

**A GST-compliance bug in the invoice PDF.** The generated invoice labeled both the CGST and
SGST columns at the *full* combined rate (e.g. "18%" on each) instead of half each -- caught
by actually rendering a test invoice and reading the text back out, not by trusting the
code. `cgst_paise + sgst_paise` was always correct; only the on-page label was wrong.

## Hardened

- **Tenant isolation**: every owner-facing query filters by `owner_user_id`;
  spot-checked in tests (`test_other_owner_cannot_see_business`,
  `test_knowledge_cannot_be_edited_by_other_owner`).
- **CORS**: no wildcard allowed in production; must be an explicit origin list.
- **Security headers**: `X-Content-Type-Options`, `Referrer-Policy` on every
  response; `X-Frame-Options: SAMEORIGIN` on everything *except* `/widget/*`
  and `/talk/*`, which are designed to be embedded cross-site.
- **Fail-fast config**: `backend/config.py` validates all required env vars
  and secret strength once at startup, instead of failing confusingly on the
  first request that happens to touch a missing var.
- **Generic error responses in production**: unhandled exceptions return a
  generic 500 in production (full detail still logged server-side and shown
  in development) instead of leaking stack traces to clients.
- **Booking write-path is independently validated**: the customer-facing AI can
  only book within services/hours the owner actually configured, and every
  booking is re-checked server-side (working hours, double-booking) regardless
  of what the model claims -- see `backend/booking.py` and its tests.
- **File uploads**: size cap retained (now admin-configurable); consider adding
  malware scanning on the upload path if you expect adversarial uploads at
  scale (not done here -- out of scope for this pass).
- **Google OAuth CSRF protection**: the login flow generates a random `state`,
  stored in a short-lived httpOnly cookie and compared against what Google
  echoes back on callback -- a mismatch (or a missing/reused state) is
  rejected outright, closing the standard OAuth login-CSRF attack where an
  attacker tricks a victim into completing *the attacker's* auth flow.
- **Google account linking is email-based, not blind**: signing in with
  Google links to an existing password account with the same email rather
  than creating a duplicate -- but this does mean if someone else's email
  provider account is compromised, they could gain access to a matching
  account here too. Same trust model as "sign in with Google" everywhere
  else; worth knowing rather than assuming.

## Still worth doing before a large-scale launch

- A staging environment (a separate deploy + separate Mongo/keys) -- this is a
  process/ops decision, not something a code change can set up for you. See
  DEPLOYMENT.md for the recommended shape.
- Structured log aggregation / APM if you outgrow reading `docker logs`.
- Prompt-injection is mitigated (system prompts explicitly instruct the model
  to ignore embedded instructions in retrieved content) but not adversarially
  red-teamed -- treat it as a reasonable baseline, not a guarantee.
- A real frontend test suite (Jest/React Testing Library) -- the backend has
  one (`pytest`, runs offline against a fake DB); the React side doesn't yet.
- Calendar sync (Google Calendar etc.) for appointments -- see README's
  "intentionally out of scope" section for why this wasn't built here.
- Real geo/IP-based anomaly detection ("this login is from a new country").
  What's implemented is device-based ("this login is from a device we've
  never seen"), which is the useful 80% without adding a GeoIP dataset or
  third-party lookup dependency -- worth revisiting if that's a priority.
- The Business API Keys' external surface (`routers/public_api.py`) is
  deliberately small -- business profile, appointments, conversations, and
  an analytics summary. Extend `AVAILABLE_SCOPES` and the router together if
  a specific integration needs more.
- A dedicated `sid`-carrying migration path for tokens issued before this
  pass isn't needed -- old 7-day tokens simply keep working under the old
  rules (no revocation check, since they carry no session id) until they
  naturally expire within a week, after which every login goes through the
  new flow. No data migration required.
