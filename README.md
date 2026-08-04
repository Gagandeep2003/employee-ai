# Roviq Ai

An AI front desk for small businesses. Connect a website (or add knowledge by
hand), and it answers customer questions, books appointments, and hands off to
a human when it matters -- embedded on the business's site with one script tag.

This repo was hardened for production from an MVP scaffold: real payments, real
email, no third-party proxies, tenant isolation, rate limiting, and a working
offline test suite. See [`DEPLOYMENT.md`](./DEPLOYMENT.md) for how to run it,
and [`SECURITY.md`](./SECURITY.md) for what changed and why.

## What it does

- **Learns your business** -- crawls your website, or takes knowledge you type/upload
  (PDF, DOCX, plain text), and answers customer questions from it via hybrid retrieval
  (Gemini embeddings + BM25, semantic search falling back to BM25 automatically whenever
  an embedding isn't available) + Gemini generation. Structured, owner-confirmed data
  (Quick Facts, appointment settings, business profile) is always given highest priority
  and can't be overridden by retrieved content or the model's own knowledge -- see
  `context_builder.py`.
- **Reviewable before it goes live** -- onboarding has a second step: an AI-written
  summary of what it learned, plus every knowledge entry with edit/delete, so you
  catch anything wrong before customers see it.
- **Books appointments** -- turn it on with your services and working hours, and
  the AI checks real availability and books directly in the chat (every booking
  is re-validated server-side against actual working hours and existing bookings
  -- the AI can't double-book or invent a slot). All scheduling is timezone-aware
  (a business's hours are always interpreted in *their* timezone, converted to
  UTC only for storage), with holiday/closure dates it won't book over. When a
  business's website is crawled, the crawler also tries to extract hours,
  services, and holidays as a draft -- reviewed and explicitly published by the
  owner, never applied automatically.
- **Hands off to a human** -- when it can't answer, it asks what the visitor needs
  and emails the business owner directly with their contact info.
- **ChatGPT-style conversation management** -- every conversation gets an
  auto-generated title, and owners can rename, pin, archive, delete, search,
  and export (JSON or plain-text transcript) any of them. Long-running
  conversations get a rolling AI-generated summary so context isn't lost once
  a thread runs past the last few raw messages.
- **A separate assistant for the owner** -- a private, authenticated chat that can
  read conversation stats, leads, and bookings, and can write changes ("update our
  hours to 9-6", "add a new service") -- a completely different trust boundary
  from the public customer-facing chat, which can only book appointments within
  configured rules and never sees or touches business settings.
- **One script tag to install** -- `<script src=".../embed.js" data-business="...">`
  drops a floating bubble on any site, no build step, works with any stack. A
  hosted link (`/talk/{business_id}`) and step-by-step platform guides
  (WordPress, Shopify, Wix, Squarespace, GoDaddy, Webflow) cover businesses
  without a developer.
- **Real billing** -- Razorpay checkout (INR/domestic) with signature-verified
  payments and a webhook safety net; usage resets automatically each billing month.
  GST-compliant invoicing (sequential numbering, CGST/SGST/IGST split, downloadable
  PDF), prorated plan upgrades, scheduled downgrades, admin-initiated refunds, and a
  daily lifecycle job that sends renewal reminders and gives a grace period before
  auto-downgrading an unrenewed subscription to free -- see `gst.py`, `invoicing.py`,
  `subscriptions.py`, and `scheduler.py`'s `billing_lifecycle_job`.
- **Stays current automatically** -- a weekly background job re-crawls every
  business's website; Quick Facts let an owner override anything that
  changes fast (today's hours, a promo, a closure) in ten seconds, always
  trusted over older crawled content; owners who've gone quiet for 30+ days
  get a nudge email. The AI also hedges its own answers on stale, volatile
  info (pricing/stock/hours) instead of stating it as flat fact.
- **Inventory-aware** -- upload a product CSV (name/price/stock/description)
  and the AI can answer real stock and pricing questions; re-uploading
  replaces the list, so refreshing it is the entire update workflow.
- **Google sign-in** -- "Continue with Google" alongside email/password,
  auto-linking to an existing account by email if one exists.
- **Account security** -- password reset, email verification, brute-force
  lockout, and two-factor authentication for any account (not just admins).
  Sessions use short-lived access tokens with rotating refresh tokens, so an
  owner can see every signed-in device (Settings → Security) and revoke one
  or all of them, with login history and new-device email alerts.
- **Business API keys** -- scoped, expiring, rate-limited API keys so a
  business's own systems (a booking bot, a Zapier/n8n workflow) can read
  their profile/appointments/conversations/analytics or create appointments
  without a browser session. Shown once at creation, hashed at rest.
- **Platform-tunable, not hardcoded** -- an admin can adjust plan limits, the
  AI's confidence threshold, upload size caps, crawl depth, and flip on
  maintenance mode from the admin panel, and every part of the app that
  matters actually reads those live values.
- **Legal CMS** -- admin-managed Privacy Policy, Terms of Service, Refund/
  Cookie/Acceptable Use/Security policies, GDPR statement, and DPA, each with
  full version history (every save creates a new immutable version; publish
  makes one live) and user acceptance tracking for ToS/Privacy -- a banner
  prompts re-acceptance if either changes after a user last accepted.
- **Admin reporting & exports** -- MRR/ARR/revenue trends, growth (new
  signups and paying-business conversions per month), an approximate churn
  rate computed from real cancellation events, and a transparent customer
  health score (usage, setup completeness, payment status) -- all exportable
  as CSV, Excel, or PDF alongside the businesses and invoices reports.

## Stack

- **Backend**: FastAPI + Motor (async MongoDB), Gemini via `google-genai` (direct,
  no proxy), Razorpay, S3-compatible object storage (falls back to local disk),
  SMTP email (any provider), slowapi rate limiting.
- **Frontend**: React (CRA + Craco) + Tailwind + shadcn/ui.
- **Deploy**: Docker Compose (single VPS) or any container host + MongoDB Atlas.

## Repo layout

```
backend/
  server.py           FastAPI app, middleware, startup/shutdown, indexes
  config.py           all env vars, read and validated once at startup
  db.py                Motor client
  auth.py, ratelimit.py, email_sender.py, storage.py, llm.py, booking.py, usage.py
  actions.py           owner-chat action grammar (write access, authenticated)
  crawler.py, retrieval.py, embeddings.py, context_builder.py   site crawling +
                        hybrid (semantic + BM25) retrieval + priority-tiered context
  routers/             one file per resource (auth, businesses, knowledge, chat,
                        conversations, analytics, billing, owner_chat, admin, ...)
  tests/               pytest suite (fake in-memory Mongo, mocked LLM -- offline)
frontend/
  src/pages/           Landing, Login, Onboarding (2-step), DashboardHome,
                        Conversations, KnowledgeBase, Appointments, Analytics,
                        WidgetSettings, Billing, Referrals, Settings, admin/*
  src/components/ChatWidget.jsx   the actual widget (bubble + chat + teaser)
  public/embed.js      the vanilla-JS loader businesses paste into their site
```

## Quick start (local dev)

```bash
# Backend
cd backend
cp .env.example .env        # fill in MONGO_URL, JWT_SECRET, GEMINI_API_KEY at minimum
pip install -r requirements.txt
uvicorn server:app --reload

# Frontend
cd frontend
cp .env.example .env
npm install
npm start
```

Or skip both and run `docker compose up --build` from the repo root (see
DEPLOYMENT.md for the env vars it needs).

## Running tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

The suite runs against an in-memory fake MongoDB and mocked Gemini calls, so it
needs no real database, API key, or network access -- fast and free to run in CI.
The appointment-booking slot math (the trickiest logic in this codebase) has
dedicated tests for working-hours enforcement, timezone conversion, holiday
closures, double-booking prevention, and cancel/rebook.

## What's intentionally out of scope

- **International payments** -- Razorpay Checkout defaults to Indian payment
  methods for INR; adding Stripe/international is a separate, later project.
- **Live POS/Shopify inventory sync** -- the CSV upload solves "the AI knows
  current stock and pricing" without needing a platform-specific integration;
  a direct Shopify/POS sync (via their own APIs) would keep it current
  without a manual re-upload, but needs a specific platform picked and its
  own OAuth app, so it wasn't built speculatively here.
- **Calendar sync** (Google Calendar, Outlook) -- appointments are booked into
  this app's own database, not a real external calendar. Fine for a solo
  practice; a multi-staff clinic will want calendar sync eventually -- the
  `booking.py` module is a clean seam to add that against.
- **Real sales/profit analytics** -- there's no POS/accounting integration, so
  the app doesn't fabricate revenue numbers. What it does track: leads,
  bookings, and lost conversations, taggable by the owner and usable by the
  owner-chat assistant for real trend analysis.
- **Visitor cross-device identity** -- a visitor's conversation history is
  tied to a browser-local visitor_id today, not an authenticated identity
  that follows them to a new device. Building real cross-device continuity
  (e.g. an emailed magic link that resumes the conversation elsewhere)
  without adding a full customer-account system is a well-scoped follow-up,
  not done in this pass.
- **Overage billing collection** -- when enabled (off by default), overage
  past a plan's monthly limit is recorded as a real, GST-numbered "due"
  invoice and the owner is emailed, but it's collected by folding it into
  the amount charged at their next plan purchase/renewal -- there's no
  stored payment method to auto-charge (this app never stores card details,
  by design), so nothing gets charged without the owner going through
  checkout again.
- **GST reference data** -- the state-code table and the default rate/SAC
  code (`gst.py`, `platform_settings.py`) were verified against current
  public guidance while building this, but tax rates and classifications do
  change; treat the defaults as a starting point to confirm with your CA,
  not as tax advice.
- **Churn rate is an approximation, labeled as one.** This app doesn't keep
  historical plan-state snapshots, so `/admin/churn` compares real
  cancellation events against total signups-to-date rather than a true paid
  cohort size. Good enough to see a trend; the admin UI says so directly
  rather than presenting it as a precise SaaS-metrics-grade number.
- **A plugin framework and integration-monitoring dashboard** were considered
  and deliberately not built -- nothing in the current feature set needs
  third-party plugin extensibility yet, and building the scaffolding
  speculatively (with no real plugin to validate it against) would be
  architecture built for a use case that doesn't exist. Worth revisiting if
  a concrete integration need comes up.
- **Cloudinary** -- evaluated and not adopted. The existing S3-compatible
  storage layer (falls back to local disk) already covers this app's actual
  file storage needs (uploaded knowledge documents, generated invoice PDFs)
  without a new vendor dependency; nothing here does image
  transformation/CDN-heavy work that would justify the switch.
