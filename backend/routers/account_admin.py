"""
Account Admin Router
Exposes /api/admin/accounts/* -- account lifecycle actions (approve, disable,
restore, permanent delete, one-time reset links), plus listing / activity /
performance views. Every handler is gated to role == 'admin'.

Self/last-admin protection lives here, not in the service layer, because it
depends on "who is asking" (the authenticated actor from the JWT), which is
HTTP-request context -- account_admin_service only knows what it's told.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from routers.auth import require_role
from services import account_admin_service
from models.schemas import PermanentDeleteRequest
from logger import get_logger

log = get_logger("account_admin")

router = APIRouter(prefix="/api/admin", tags=["Account Admin"])

require_admin = require_role("admin")
limiter = Limiter(key_func=get_remote_address)


def _raise_from_value_error(e: ValueError) -> None:
    """Translate a ValueError raised by account_admin_service into an HTTP
    error. 'user not found: ...' becomes 404; everything else (invalid
    status, blank delete reason, confirmUserId mismatch) becomes 400."""
    msg = str(e)
    if msg.startswith("user not found"):
        raise HTTPException(status_code=404, detail="Account not found")
    raise HTTPException(status_code=400, detail=msg)


def _guard_self_and_last_admin(actor: dict, target_user_id: str, action: str) -> None:
    """
    Reject (409) a disable/delete action that would either:
      - act on the caller's own account (self-disable / self-delete), or
      - drop the system to zero active admins (disabling/deleting the last
        currently-active admin).

    Approve/restore never call this -- turning an account back on can't lock
    anyone out or destroy the last admin.
    """
    if actor.get("sub") == target_user_id:
        raise HTTPException(status_code=409, detail=f"Cannot {action} your own account")

    target = account_admin_service.get_account(target_user_id)
    if not target:
        # Let the underlying service action raise/produce the 404 --
        # nothing to guard against for an account that doesn't exist.
        return

    if target.get("role") == "admin" and target.get("account_status") == "active":
        if account_admin_service.count_active_admins() <= 1:
            raise HTTPException(status_code=409, detail="Cannot remove the last active admin")


# ---------------------------------------------------------------------------
# GET /api/admin/accounts
# ---------------------------------------------------------------------------


@router.get("/accounts")
@limiter.limit("5/minute")
def list_accounts(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    actor: dict = Depends(require_admin),
):
    return account_admin_service.list_accounts(
        status=status, search=search, cursor=cursor, limit=limit
    )


# ---------------------------------------------------------------------------
# Lifecycle actions
# ---------------------------------------------------------------------------


@router.post("/accounts/{user_id}/approve")
@limiter.limit("5/minute")
def approve_account(request: Request, user_id: str, actor: dict = Depends(require_admin)):
    try:
        return account_admin_service.change_status(actor["sub"], user_id, "active")
    except ValueError as e:
        _raise_from_value_error(e)


@router.post("/accounts/{user_id}/disable")
@limiter.limit("5/minute")
def disable_account(request: Request, user_id: str, actor: dict = Depends(require_admin)):
    _guard_self_and_last_admin(actor, user_id, "disable")
    try:
        return account_admin_service.change_status(actor["sub"], user_id, "disabled")
    except ValueError as e:
        _raise_from_value_error(e)


@router.post("/accounts/{user_id}/restore")
@limiter.limit("5/minute")
def restore_account(request: Request, user_id: str, actor: dict = Depends(require_admin)):
    try:
        return account_admin_service.change_status(actor["sub"], user_id, "active")
    except ValueError as e:
        _raise_from_value_error(e)


@router.post("/accounts/{user_id}/reset-link")
@limiter.limit("5/minute")
def reset_link(request: Request, user_id: str, actor: dict = Depends(require_admin)):
    try:
        reset_url = account_admin_service.create_reset_link(actor["sub"], user_id)
    except ValueError as e:
        _raise_from_value_error(e)
    return {"resetUrl": reset_url}


@router.delete("/accounts/{user_id}")
@limiter.limit("5/minute")
def delete_account(
    request: Request,
    user_id: str,
    body: PermanentDeleteRequest,
    actor: dict = Depends(require_admin),
):
    _guard_self_and_last_admin(actor, user_id, "delete")
    try:
        return account_admin_service.permanently_delete(
            actor["sub"], user_id, body.confirmUserId, body.reason
        )
    except ValueError as e:
        _raise_from_value_error(e)


# ---------------------------------------------------------------------------
# Per-account views
# ---------------------------------------------------------------------------


@router.get("/accounts/{user_id}/activity")
@limiter.limit("5/minute")
def account_activity(
    request: Request,
    user_id: str,
    limit: int = Query(default=50, le=100),
    cursor: Optional[str] = None,
    actor: dict = Depends(require_admin),
):
    return account_admin_service.activity(user_id, limit=limit, cursor=cursor)


@router.get("/accounts/{user_id}/performance")
@limiter.limit("5/minute")
def account_performance(
    request: Request,
    user_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    actor: dict = Depends(require_admin),
):
    return account_admin_service.performance(user_id, start=start, end=end)
