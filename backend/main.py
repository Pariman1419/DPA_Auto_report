from dotenv import load_dotenv
load_dotenv()  # must run before any service module is imported

import os
import time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from logger import get_logger, _configure
_configure()  # init logging before routers import

from routers.product_request import router as product_request_router
from routers.auth import router as auth_router

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


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    log.info("%s %s  →  %s  (%.0fms)", request.method, request.url.path, response.status_code, elapsed)
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 9090))
    log.info("Starting DPA backend on port %s", port)
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
