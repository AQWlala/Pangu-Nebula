import os
import secrets
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
from .db.engine import init_db, async_session
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
from .api.cu import router as cu_router
from .api.kb import router as kb_router
from .api.graph import router as graph_router
from .api.events import router as events_router
from .core.event_bus import EventBus, set_global_event_bus
from .services.heartbeat_service import create_default_heartbeat
from .services.linkage_coordinator import LinkageCoordinator
from .tools import builtin_tools  # noqa: F401
from .tools import command_tool, code_tool  # noqa: F401  v2.2.0 Phase 2-3
from .tools import browser_tools, computer_tools  # noqa: F401  v2.2.0 Phase 5

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

    # P1: Initialize KB storage singletons in app.state so API handlers can
    # reuse one ChromaVectorStore / KuzuGraphStore instead of creating a new
    # connection per request. Wrapped in try/except so a KB init failure does
    # not break the rest of the app (endpoints fall back to per-request
    # construction when app.state.vector_store is absent).
    try:
        from .config_kb_cu import KBConfig
        from .kb.retrieval.vectorstore import ChromaVectorStore
        from .kb.graph.kuzu_store import KuzuGraphStore

        kb_config = getattr(app.state, "kb_config", None) or KBConfig()
        kb_config.ensure_dirs()
        app.state.kb_config = kb_config
        app.state.vector_store = ChromaVectorStore(persist_dir=kb_config.chroma_dir)
        graph_store = KuzuGraphStore(db_dir=kb_config.kuzu_dir)
        graph_store.init_schema()
        app.state.graph_store = graph_store
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "KB store singleton initialization failed; endpoints will fall "
            "back to per-request construction",
            exc_info=True,
        )

    app.state.services_loaded = True

    # v2.3.0 Phase 0: 初始化事件总线 + 心跳节拍器
    # EventBus 是跨模块联动的脊柱,所有 publish/subscribe 经此扇出
    event_bus = EventBus()
    app.state.event_bus = event_bus
    set_global_event_bus(event_bus)

    # HeartbeatService: 5 种节拍 (微/小/中/大/自检) 错峰执行
    heartbeat = create_default_heartbeat(app.state)
    app.state.heartbeat_service = heartbeat
    await heartbeat.start()

    # v2.3.0 Phase 2: 跨模块联动协调器 (后端消费端)
    # 在 HeartbeatService 之后启动, 注册 5 条联动消费者 (健康/工具/MCP/委派/DAG)
    # graph_executor 传 None: main.py 无全局实例, 链路 6 降级为 log-only
    linkage = LinkageCoordinator(
        event_bus=event_bus,
        session_factory=async_session,
        graph_executor=None,
    )
    app.state.linkage_coordinator = linkage
    await linkage.start()

    yield

    # v2.3.0 Phase 2: 先停止联动协调器 (避免 shutdown 期间消费新事件),
    # 再停止心跳节拍器
    try:
        await linkage.stop()
    except Exception:
        pass

    # v2.3.0: 停止心跳节拍器 (先停,避免 shutdown 期间触发新任务)
    try:
        await heartbeat.stop()
    except Exception:
        pass

    # Shutdown: release store connections. Each close() is wrapped in its own
    # try/except so one failing release does not skip the others.
    for _attr in ("vector_store", "graph_store"):
        _store = getattr(app.state, _attr, None)
        if _store is None:
            continue
        try:
            _store.close()
        except Exception:
            pass


app = FastAPI(lifespan=lifespan, debug=settings.debug)

cors_origins = _parse_cors_origins(settings.cors_origins, settings.debug)
allow_credentials = "*" not in cors_origins and not settings.debug

# v2.2.1 P2: CORS 收敛 — 方法/头收敛到实际使用的集合
# origins 保持 * (Tauri/pywebview 模式下 origin 不固定,debug 模式回退到 *)
# 允许的方法覆盖 RESTful CRUD + OPTIONS 预检
_CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
# 允许的头覆盖前端实际使用的请求头 (Auth/Content/Ajax/Sidecar 自定义)
_CORS_ALLOW_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "X-Requested-With",
    "X-Sidecar-Token",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=_CORS_ALLOW_METHODS,
    allow_headers=_CORS_ALLOW_HEADERS,
)


# v2.1.0 Phase 0 — Bearer token auth middleware for Tauri sidecar mode.
# In pywebview mode (sidecar_token empty), this middleware is a no-op.
# In tauri mode, all requests must carry "Authorization: Bearer <token>"
# except for /health and /health/ready (used by Tauri readiness probes).
# Note: /shutdown is intentionally NOT whitelisted — an unauthenticated
# process-kill endpoint is a security risk, so it requires a valid token.
@app.middleware("http")
async def sidecar_token_auth(request: Request, call_next):
    token = settings.sidecar_token
    # No-op in pywebview mode (no token configured)
    if not token:
        return await call_next(request)
    # Allow readiness probes without token (Tauri polls /health/ready before
    # the frontend has a chance to inject the token).
    unauthenticated_paths = {"/health/ready", "/health"}
    if request.url.path in unauthenticated_paths:
        return await call_next(request)
    # Allow CORS preflight (OPTIONS requests don't carry Authorization header).
    # Auth middleware is in the outer layer (added after CORSMiddleware),
    # so without this, OPTIONS preflight would be rejected with 401 before
    # CORS middleware can handle it, causing "Failed to fetch" in the WebView.
    if request.method == "OPTIONS":
        return await call_next(request)
    # Verify Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:]
        if secrets.compare_digest(provided, token):
            return await call_next(request)
    # v2.3.0: SSE 端点 (EventSource/fetch GET) 无法设置 Authorization header,
    # 额外接受查询参数 ?token=<sidecar_token> (仅 /events/stream 路径)
    if request.url.path == "/events/stream":
        q_token = request.query_params.get("token", "")
        if q_token and secrets.compare_digest(q_token, token):
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
app.include_router(cu_router)
app.include_router(kb_router)
app.include_router(graph_router)
app.include_router(events_router)


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
# on window close / app quit). Requires a valid Bearer token — Tauri must
# send the sidecar token in the Authorization header when calling /shutdown.
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
