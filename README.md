# AI Employee

An AI front desk for small businesses. Connect a website (or add knowledge by
hand), and it answers customer questions, books appointments, and hands off to
a human when it matters -- embedded on the business's site with one script tag.

This repo was hardened for production from an MVP scaffold: real payments, real
email, no third-party proxies, tenant isolation, rate limiting, and a working
offline test suite. See [`DEPLOYMENT.md`](./DEPLOYMENT.md) for how to run it,
and [`SECURITY.md`](./SECURITY.md) for what changed and why.

## What it does

- **Learns your business** -- crawls your website, or takes knowledge you type/upload
  (PDF, DOCX, plain text), and answers customer questions from it via retrieval
  (BM25) + Gemini.
- **Reviewable before it goes live** -- onboarding has a second step: an AI-written
  summary of what it learned, plus every knowledge entry with edit/delete, so you
  catch anything wrong before customers see it.
- **Books appointments** -- turn it on with your services and working hours, and
  the AI checks real availability and books directly in the chat (every booking
  is re-validated server-side against actual working hours and existing bookings
  -- the AI can't double-book or invent a slot).
- **Hands off to a human** -- when it can't answer, it asks what the visitor needs
  and emails the business owner directly with their contact info.
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
- **Account security** -- password reset, email verification, and optional
  two-factor authentication for admin accounts (impersonation makes those
  high-value targets).
- **Platform-tunable, not hardcoded** -- an admin can adjust plan limits, the
  AI's confidence threshold, upload size caps, crawl depth, and flip on
  maintenance mode from the admin panel, and every part of the app that
  matters actually reads those live values.

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
  crawler.py, retrieval.py   site crawling + BM25 retrieval
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
dedicated tests for working-hours enforcement, double-booking prevention, and
cancel/rebook.

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
