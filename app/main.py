from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.settings import get_settings
from app.core.container import get_auth_service, get_scheduler_service, get_snapshot_repository


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    snapshot_repository = get_snapshot_repository()
    if snapshot_repository and snapshot_repository.enabled:
        try:
            snapshot_repository.ensure_schema()
            get_auth_service().bootstrap()
        except Exception:
            logger.exception("Failed to ensure database schema on startup.")
    scheduler = get_scheduler_service()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(
    title="Shandong Refined Oil Agent Lab",
    version="0.1.0",
    description="FastAPI agent lab for Shandong 92# gasoline deterministic prediction and backtest.",
    lifespan=lifespan,
)


def _usage_action(method: str, path: str) -> str:
    if path == "/api/v1/auth/login":
        return "login_request"
    if path == "/api/v1/auth/logout":
        return "logout"
    if path.startswith("/api/v1/predictions/"):
        return "prediction"
    if path.startswith("/api/v1/chat/"):
        return "chat"
    if path.startswith("/api/v1/briefings/"):
        return "briefing"
    if path.startswith("/api/v1/users"):
        return "user_admin"
    if path.startswith("/api/v1/permissions") or path.startswith("/api/v1/roles"):
        return "permission_admin"
    if path.startswith("/api/v1/agents/"):
        return "agent_manage"
    if path.startswith("/api/v1/policy-events"):
        return "policy_event"
    if path.startswith("/api/v1/regional-freight-settings"):
        return "freight_setting" if method in {"POST", "PATCH", "PUT", "DELETE"} else "freight_view"
    if path.startswith("/api/v1/market/") or path.startswith("/api/v1/dashboard"):
        return "market_view"
    return "api_request"


def _should_log_usage(path: str) -> bool:
    if not path.startswith("/api/v1/"):
        return False
    skipped_paths = {
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/market/brent-live",
    }
    return path not in skipped_paths


def _request_user(request: Request) -> dict[str, Any]:
    token = request.cookies.get(get_settings().auth.cookie_name)
    if not token:
        return {"user_id": None, "username": None}
    repository = get_snapshot_repository()
    if not repository or not repository.enabled:
        return {"user_id": None, "username": None}
    session = repository.get_active_session(token)
    if not session:
        return {"user_id": None, "username": None}
    try:
        profile = repository.get_user_profile(int(session["user_id"]))
    except Exception:
        return {"user_id": int(session["user_id"]), "username": None}
    return {"user_id": int(profile["user_id"]), "username": str(profile.get("username") or "")}


@app.middleware("http")
async def usage_log_middleware(request: Request, call_next):
    path = request.url.path
    should_log = _should_log_usage(path)
    user_payload = _request_user(request) if should_log else {"user_id": None, "username": None}
    started_at = time.perf_counter()
    response = await call_next(request)
    if should_log:
        try:
            repository = get_snapshot_repository()
            if repository and repository.enabled:
                repository.save_usage_log(
                    user_id=user_payload.get("user_id"),
                    username=user_payload.get("username"),
                    action=_usage_action(request.method, path),
                    method=request.method,
                    path=path,
                    status_code=response.status_code,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    duration_ms=int((time.perf_counter() - started_at) * 1000),
                    detail={"query": dict(request.query_params)},
                )
        except Exception:
            logger.exception("Failed to save usage log.")
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(router)
