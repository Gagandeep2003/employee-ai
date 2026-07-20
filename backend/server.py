import logging
import traceback

from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

import config
from db import client, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("ai-employee")

app = FastAPI(title="AI Employee", version="1.0.0")
api = APIRouter(prefix="/api")

# Rate limiting
from ratelimit import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Routers
from routers import auth as auth_router
from routers import businesses as biz_router
from routers import knowledge as kb_router
from routers import chat as chat_router
from routers import conversations as conv_router
from routers import analytics as ana_router
from routers import billing as billing_router
from routers import referrals as ref_router
from routers import owner_chat as oc_router
from routers import admin as admin_router
from storage import init_storage
from auth import seed_admin
from scheduler import start_scheduler, stop_scheduler

for r in [
    auth_router.router, biz_router.router, kb_router.router, chat_router.router,
    conv_router.router, ana_router.router, billing_router.router,
    ref_router.router, oc_router.router, admin_router.router,
]:
    api.include_router(r)


@api.get("/")
async def root():
    return {"service": "AI Employee", "status": "ok"}


@api.get("/health")
async def health():
    """Unauthenticated liveness/readiness check for load balancers & uptime monitors."""
    try:
        await db.command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": "up" if db_ok else "down"}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # The customer-facing widget page (served by the frontend at /widget/{id} and
    # /talk/{id}, not by this backend) is DESIGNED to be embedded in an <iframe>
    # on any third-party business website. This backend has no HTML routes of its
    # own to exempt, but the check is kept in case a future route serves one.
    path = request.url.path
    if not (path.startswith("/widget/") or path.startswith("/talk/")):
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Avoid leaking stack traces / internals to clients in production."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    if not config.IS_PRODUCTION:
        logger.error(traceback.format_exc())
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.on_event("startup")
async def startup():
    backend = init_storage()
    logger.info("Storage initialized (%s backend)", backend)
    # Indexes
    await db.users.create_index("user_id", unique=True)
    await db.users.create_index("email", unique=True)
    await db.businesses.create_index("business_id", unique=True)
    await db.businesses.create_index("owner_user_id")
    await db.knowledge_chunks.create_index([("business_id", 1)])
    await db.conversations.create_index([("business_id", 1), ("created_at", -1)])
    await db.messages.create_index([("conversation_id", 1)])
    await db.files.create_index("business_id")
    await db.notifications.create_index([("business_id", 1), ("created_at", -1)])
    await db.referrals.create_index("code", unique=True)
    await db.payment_orders.create_index("razorpay_order_id", unique=True)
    await db.invoices.create_index([("business_id", 1), ("created_at", -1)])
    await db.appointments.create_index([("business_id", 1), ("start_time", 1)])
    await db.appointments.create_index("reference")
    await seed_admin()
    start_scheduler()
    logger.info("Indexes ensured; admin seed checked")


@app.on_event("shutdown")
async def shutdown():
    stop_scheduler()
    client.close()


# make db accessible to routers via app.state
app.state.db = db
