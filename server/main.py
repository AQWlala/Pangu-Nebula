import os
import signal
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from .config import load_settings, APP_DIR
from .db.engine import init_db
from .api.chat import router as chat_router
from .api.persona import router as persona_router
from .api.swarm import router as swarm_router
from .api.memory import router as memory_router
from .api.skills import router as skills_router
from .api.wiki import router as wiki_router
from .api.evolution import router as evolution_router
from .api.loop import router as loop_router
from .api.sync import router as sync_router
from .api.sync_device import router as sync_device_router
from .api.oauth import router as oauth_router
from .api.did import router as did_router
from .api.channel import router as channel_router
from .api.mcp import router as mcp_router
from .api.scheduler import router as scheduler_router
from .api.security import router as security_router
from .api.multimodal import router as multimodal_router
from .api.os_sense import router as os_sense_router
from .api.providers import router as providers_router
from .api.tools import router as tools_router
from .api.distiller import router as distiller_router
from .api.audit import router as audit_router
from .api.browser import router as browser_router
from .api.autowork import router as autowork_router
from .api.dag import router as dag_router
from .api.wiki_review import router as wiki_review_router
from .api.acp import router as acp_router
from .api.terminal import router as terminal_router
from .api.idmm import router as idmm_router
from .api.rag import router as rag_router
from .api.acp_adapters import router as acp_adapters_router
from .api.skill_market import router as skill_market_router
from .api.update import router as update_router
from .api.health import router as health_check_router
from .tools import builtin_tools  # noqa: F401

load_dotenv()
settings = load_settings()


def _parse_cors_origins(raw: str, debug: bool) -> list[str]:
    if debug:
        return ["*"]
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if not origins:
        return ["http://127.0.0.1:7860"]
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Track startup time for /health/ready readiness probe
    app.state.start_time = time.time()
    app.state.db_initialized = False
    await init_db()
    app.state.db_initialized = True
    app.state.services_loaded = True
    yield


app = FastAPI(lifespan=lifespan, debug=settings.debug)

cors_origins = _parse_cors_origins(settings.cors_origins, settings.debug)
allow_credentials = "*" not in cors_origins and not settings.debug

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# v2.1.0 Phase 0 — Bearer token auth middleware for Tauri sidecar mode.
# In pywebview mode (sidecar_token empty), this middleware is a no-op.
# In tauri mode, all requests must carry "Authorization: Bearer <token>"
# except for /health/ready (used by Tauri readiness probe) and /shutdown.
@app.middleware("http")
async def sidecar_token_auth(request: Request, call_next):
    token = settings.sidecar_token
    # No-op in pywebview mode (no token configured)
    if not token:
        return await call_next(request)
    # Allow readiness + shutdown probes without token (Tauri polls /health/ready
    # before frontend has a chance to inject the token).
    unauthenticated_paths = {"/health/ready", "/health", "/shutdown"}
    if request.url.path in unauthenticated_paths:
        return await call_next(request)
    # Verify Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:]
        if provided == token:
            return await call_next(request)
    # Reject all other requests without valid token
    return JSONResponse(
        status_code=401,
        content={"ok": False, "data": None, "error": "Unauthorized: invalid or missing Bearer token"},
    )

# Static frontend assets
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    _dist = Path(sys._MEIPASS) / "frontend" / "dist"
else:
    _dist = APP_DIR / "frontend" / "dist"
if _dist.exists():
    app.mount("/static", StaticFiles(directory=str(_dist)), name="static")

app.include_router(chat_router)
app.include_router(persona_router)
app.include_router(swarm_router)
app.include_router(memory_router)
app.include_router(skills_router)
app.include_router(wiki_router)
app.include_router(evolution_router)
app.include_router(loop_router)
app.include_router(sync_router)
app.include_router(sync_device_router)
app.include_router(oauth_router)
app.include_router(did_router)
app.include_router(channel_router)
app.include_router(mcp_router)
app.include_router(scheduler_router)
app.include_router(security_router)
app.include_router(multimodal_router)
app.include_router(os_sense_router)
app.include_router(providers_router)
app.include_router(tools_router)
app.include_router(distiller_router)
app.include_router(audit_router)
app.include_router(browser_router)
app.include_router(autowork_router)
app.include_router(dag_router)
app.include_router(wiki_review_router)
app.include_router(acp_router)
app.include_router(terminal_router)
app.include_router(idmm_router)
app.include_router(rag_router)
app.include_router(acp_adapters_router)
app.include_router(skill_market_router)
app.include_router(update_router)
app.include_router(health_check_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# v2.1.0 Phase 0 — Sidecar readiness probe (polled by Tauri main process).
# Returns DB initialization + services status + uptime. No Bearer token
# required (whitelisted in sidecar_token_auth middleware) so Tauri can poll
# before the frontend has injected the token.
@app.get("/health/ready")
async def health_ready(request: Request):
    app_state = request.app.state
    db_initialized = getattr(app_state, "db_initialized", False)
    services_loaded = getattr(app_state, "services_loaded", False)
    start_time = getattr(app_state, "start_time", None)
    uptime_seconds = (time.time() - start_time) if start_time else 0.0
    ready = db_initialized and services_loaded
    return {
        "status": "ready" if ready else "starting",
        "db_initialized": db_initialized,
        "services_loaded": services_loaded,
        "uptime_seconds": round(uptime_seconds, 3),
    }


# v2.1.0 Phase 0 — Graceful shutdown endpoint (called by Tauri Supervisor
# on window close / app quit). No Bearer token required (whitelisted in
# sidecar_token_auth middleware) so Tauri can always reach it.
#
# Flow: respond 200 immediately → schedule SIGTERM delivery after a short
# delay so uvicorn finishes streaming the response → uvicorn lifespan
# shutdown runs (DB close, etc.) → process exits.
@app.post("/shutdown")
async def shutdown_sidecar(request: Request):
    def _terminate():
        # Give uvicorn ~100ms to flush the HTTP response, then signal self.
        time.sleep(0.1)
        os.kill(os.getpid(), signal.SIGTERM)

    # Run the terminator in a background thread (not asyncio task) so the
    # signal is delivered even if the event loop is busy draining requests.
    threading.Thread(target=_terminate, daemon=True).start()
    return {"ok": True, "data": {"shutting_down": True}, "error": None}
