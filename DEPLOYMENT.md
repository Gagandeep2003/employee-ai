# Deployment

## Lowest-cost path (recommended to start)

1. **Database**: MongoDB Atlas free tier (M0) -- 512MB, enough for thousands of
   conversations. Get the connection string, use it as `MONGO_URL`.
2. **Storage**: Cloudflare R2 free tier -- 10GB storage, no egress fees. Create a
   bucket + API token, fill in the `S3_*` vars in `backend/.env`.
3. **Email**: Resend free tier (3,000 emails/month) or Brevo (300/day) -- either
   gives you SMTP credentials, fill in `SMTP_*`.
4. **LLM**: Gemini API, pay-as-you-go. `gemini-3.1-flash-lite` (the default) costs
   roughly $0.25/M input + $1.50/M output tokens -- a typical chat turn with RAG
   context costs well under $0.001. See the cost math in `routers/admin.py`.
5. **Payments**: Razorpay (free to integrate, they take a per-transaction cut).
6. **Hosting**: one small VPS (~$6/mo droplet) running `docker compose up -d`
   handles the backend + frontend for a meaningful number of businesses. Scale up
   the VPS size, not the architecture, until you have a real reason to.

Total fixed cost to start: **the VPS only** (~$6/mo). Everything else is free
until you have real usage, then scales with usage, not with a flat SaaS bill.

## Environment variables

See `backend/.env.example` for the full list with descriptions. The ones that
matter most:

| Variable | Required? | Notes |
|---|---|---|
| `MONGO_URL`, `DB_NAME` | Yes | |
| `JWT_SECRET` | Yes | 32+ random chars in production (the app refuses to boot otherwise) |
| `CORS_ORIGINS` | Yes in production | exact origins, no wildcard |
| `GEMINI_API_KEY` | Yes in production | https://aistudio.google.com/apikey |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Strongly recommended | the *only* way an account becomes admin -- see SECURITY.md |
| `S3_*` | No | falls back to local disk (fine for a single instance, won't survive redeploys on most PaaS) |
| `RAZORPAY_*` | No | paid plans return a clean 503 until set; Free plan works regardless |
| `SMTP_*` | No | handoff/booking/verification emails silently skip (still logged in-app) until set |
| `FRONTEND_URL` | Strongly recommended | used to build the links inside password-reset and email-verification messages |
| `GOOGLE_CLIENT_ID` / `SECRET` / `REDIRECT_URI` | No | enables "Continue with Google"; needs a Google Cloud OAuth client, see below |
| `ENABLE_SCHEDULER` | No | default true; set false on all but one replica if running multiple instances (see below) |
| `REDIS_URL` | No | only needed if you run more than one backend replica (shares rate-limit counters) |

Set `ENV=production` when you deploy for real -- it turns on the strict
validation above and tightens cookie settings (`Secure`, `SameSite=None`).

## Docker Compose (single VPS)

```bash
cp backend/.env.example backend/.env   # fill in real values
REACT_APP_BACKEND_URL=https://api.yourdomain.com docker compose up --build -d
```

This runs Mongo + backend + frontend on one machine. Swap the `mongo` service
for Atlas once you outgrow it (just point `MONGO_URL` there and drop the service
from `docker-compose.yml`) -- no application code changes needed.

Frontend and backend can also be split across two machines/services (e.g.
frontend on Vercel/Netlify, backend on Render/Railway/Fly.io) -- just set
`REACT_APP_BACKEND_URL` to wherever the backend ends up, and `CORS_ORIGINS` on
the backend to wherever the frontend ends up.

## Google OAuth ("Continue with Google")

This needs an OAuth 2.0 Client ID from Google Cloud Console -- an external
setup step, since only you can create it under your own Google account:

1. [console.cloud.google.com](https://console.cloud.google.com) → create/select
   a project → **APIs & Services → Credentials → Create Credentials → OAuth
   client ID** (type: Web application).
2. Under **Authorized redirect URIs**, add:
   `https://<your-backend-domain>/api/auth/google/callback`
3. Copy the generated Client ID and Client Secret into `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET`, and set `GOOGLE_REDIRECT_URI` to the exact URL from
   step 2.
4. You'll also need to configure the OAuth consent screen (app name, support
   email) before Google will let real users through -- a one-time setup in
   the same Console section.

Until these are set, the "Continue with Google" button on the login page
simply isn't offered -- password signup/login keeps working regardless.

## Scheduled jobs (weekly re-crawl + staleness nudges)

Runs in-process via APScheduler by default -- no extra infrastructure needed
for a single backend instance. Two things worth knowing:

- **First run happens one week after the server starts**, not immediately --
  so a restart doesn't trigger a burst re-crawl of every business.
- **If you run more than one backend replica**, each would otherwise run
  these jobs independently (duplicate re-crawls, duplicate nudge emails).
  Set `ENABLE_SCHEDULER=false` on all replicas and instead point an external
  cron (a scheduled GitHub Actions workflow, or your host's cron feature) at
  `POST /api/admin/cron/run-weekly-jobs` (requires an admin session) once a week.

## Razorpay webhook

After deploying, create a webhook in the Razorpay dashboard pointing at:
```
https://<your-backend-domain>/api/billing/webhook
```
Subscribe to `payment.captured`, `payment.failed`, `refund.processed`. Copy the
webhook secret into `RAZORPAY_WEBHOOK_SECRET`. This is a safety net for cases
where the browser closes before the in-app `/billing/verify` call completes --
the main checkout flow doesn't strictly require it, but you should still set it up.

## Scaling past one instance

The one thing that needs attention: **rate limiting is in-memory by default**,
so each backend replica enforces its own counters independently. If you run
more than one replica behind a load balancer, set `REDIS_URL` (a free Upstash
Redis instance is enough) so all replicas share the same limits.

Knowledge retrieval (BM25) is also per-business and rebuilt lazily in memory --
this is fine at any number of replicas since each request re-fetches from Mongo
on a cache miss, just be aware the first request after a deploy is slightly
slower per business.

## A staging environment, cheaply

You don't need a second server to get real value here -- the cheapest version
that still catches real problems:

1. A second MongoDB Atlas free-tier cluster (separate from production data).
2. A second `.env` with test-mode Razorpay keys (`rzp_test_...`, which never
   move real money) and a second Gemini key if you want cost isolation.
3. Deploy the same Docker image to a second small VPS or a free-tier host
   (Render/Railway's free tier is enough for staging traffic).
4. Point `CORS_ORIGINS`/`FRONTEND_URL` at the staging frontend domain.

That's enough to catch "does this actually boot and run" issues before they
hit real businesses, without paying for a second production-grade environment.

## Before you consider this "launched"

- [ ] `ADMIN_EMAIL` / `ADMIN_PASSWORD` set (see SECURITY.md for why this matters)
- [ ] Admin has enabled two-factor auth (Admin → Settings → Two-factor authentication)
- [ ] `JWT_SECRET` is a real random value, not the example
- [ ] `CORS_ORIGINS` is your real frontend domain, not `*`
- [ ] `FRONTEND_URL` is set to your real frontend domain -- password-reset and
      email-verification links are built from this; leaving it blank sends
      broken relative links in those emails
- [ ] Razorpay is in live mode (not test keys) with the webhook configured
- [ ] S3-compatible storage configured if you're on a PaaS that wipes disk on redeploy
- [ ] SMTP configured so handoff/booking/verification emails actually get delivered
- [ ] `ENV=production` set
