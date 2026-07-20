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
