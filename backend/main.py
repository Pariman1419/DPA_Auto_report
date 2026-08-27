from dotenv import load_dotenv
load_dotenv()  # must run before any service module is imported

import os
import time
import uvicorn
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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

log = get_logger("main")

app = FastAPI(
    title="DPA QA Test Manager API",
    description="Backend API for reading Product Request Excel files",
    version="1.0.0",
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


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    request.state.request_id = uuid4()
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    safe_path = _safe_request_path(request)
    log.info("%s %s  →  %s  (%.0fms)", request.method, safe_path, response.status_code, elapsed)

    if request.url.path != "/health":
        actor_user_id, session_id = _extract_telemetry_identity(request)
        telemetry_service.record_request_telemetry(
            request_id=request.state.request_id,
            user_id=actor_user_id,
            session_id=session_id,
            route=safe_path,
            method=request.method,
            status_code=response.status_code,
            duration_ms=elapsed,
        )

    return response


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 9090))
    log.info("Starting DPA backend on port %s", port)
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
