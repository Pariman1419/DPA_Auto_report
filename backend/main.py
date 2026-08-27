from dotenv import load_dotenv
load_dotenv()  # must run before any service module is imported

import os
import time
import uvicorn
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from logger import get_logger, _configure
_configure()  # init logging before routers import

from routers.product_request import router as product_request_router
from routers.auth import router as auth_router
from routers.account_admin import router as account_admin_router
from services.auth_service import decode_token
from services import telemetry_service
from services.db_connector import initialize_dpa_pool, close_dpa_pool

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Own the DPA database pool's lifecycle for the app's lifetime:
    construct it once at startup, close it once at shutdown."""
    initialize_dpa_pool()
    try:
        yield
    finally:
        close_dpa_pool()


app = FastAPI(
    title="DPA QA Test Manager API",
    description="Backend API for reading Product Request Excel files",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — loaded from env; no hardcoded localhost:5173 in production
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(product_request_router)
app.include_router(account_admin_router)


_COOKIE_NAME = "dpa_token"
_RESET_PATH_PREFIX = "/api/auth/reset-password/"


def _safe_request_path(request: Request) -> str:
    """Return a log-safe, templated path without URL-embedded secrets."""
    path = request.url.path
    if path.startswith(_RESET_PATH_PREFIX):
        return "/api/auth/reset-password/{token}"
    route = request.scope.get("route")
    return route.path if route else path


def _extract_telemetry_identity(request: Request):
    """
    Best-effort JWT decode for telemetry attribution: cookie first, then
    Authorization: Bearer header, mirroring get_current_user's extraction
    order (routers/auth.py). Never raises -- any missing/invalid token
    simply yields None. This is observability, not an auth gate.
    """
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
    if not token:
        return None, None
    try:
        payload = decode_token(token)
        return payload.get("sub"), payload.get("sid")
    except JWTError:
        return None, None
    except Exception:
        return None, None


def _record_telemetry(request: Request, safe_path: str, status_code: int, elapsed: float) -> None:
    """Shared telemetry-recording step for both the success and exception
    paths of request_log_middleware. Skips /health (never had telemetry).
    telemetry_service.record_request_telemetry is itself fail-open, so no
    try/except is needed here."""
    if request.url.path == "/health":
        return
    actor_user_id, session_id = _extract_telemetry_identity(request)
    telemetry_service.record_request_telemetry(
        request_id=request.state.request_id,
        user_id=actor_user_id,
        session_id=session_id,
        route=safe_path,
        method=request.method,
        status_code=status_code,
        duration_ms=elapsed,
    )


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    request.state.request_id = str(uuid4())
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # An unhandled exception in a route handler raises past call_next
        # instead of yielding a Response. Without this except block, the
        # exception would propagate past the log line and telemetry call
        # below (and past this whole middleware function) straight to
        # Starlette's ServerErrorMiddleware, so this request would never be
        # logged or recorded -- see PH-08. _safe_request_path() is used here
        # too so the reset-password path stays templated on the failure path
        # as well as the success path -- see PH-09.
        elapsed = (time.perf_counter() - start) * 1000
        safe_path = _safe_request_path(request)
        log.exception(
            "%s %s  →  500 (unhandled exception)  (%.0fms) request_id=%s",
            request.method, safe_path, elapsed, request.state.request_id,
        )
        _record_telemetry(request, safe_path, 500, elapsed)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": str(request.state.request_id),
            },
        )

    elapsed = (time.perf_counter() - start) * 1000
    safe_path = _safe_request_path(request)
    log.info("%s %s  →  %s  (%.0fms)", request.method, safe_path, response.status_code, elapsed)
    _record_telemetry(request, safe_path, response.status_code, elapsed)

    return response


@app.get("/health")
def health(request: Request):
    """Public liveness/readiness probe -- stays DB-independent.

    `gitSha` is only included when the caller presents a valid JWT with
    role=admin (decoded straight from the token, no DB round-trip). This
    deliberately skips the `sv` (session_version) revocation check that
    get_current_user normally performs -- unlike get_current_user, this
    endpoint never hits the DB, so a revoked admin's still-unexpired token
    can leak a short git SHA here. That's an accepted tradeoff to keep
    `/health` DB-independent (a plan goal), not an oversight.
    A missing/invalid/expired token is never an error here: it just means
    `gitSha` is omitted.
    """
    body = {"status": "ok"}

    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

    if token:
        try:
            payload = decode_token(token)
        except Exception:
            payload = None
        if payload and payload.get("role") == "admin":
            body["gitSha"] = os.getenv("APP_GIT_SHA", "unknown")

    return body


if __name__ == "__main__":
    port = int(os.getenv("PORT", 9090))
    log.info("Starting DPA backend on port %s", port)
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
