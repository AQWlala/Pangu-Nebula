import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
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
from .api.health import router as health_check_router
from .tools import builtin_tools  # noqa: F401 - register builtin tools

load_dotenv()
settings = load_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 前端静态资源目录:打包后在 _MEIPASS/frontend/dist,开发时在项目根/frontend/dist
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
app.include_router(health_check_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("server.main:app", host="0.0.0.0", port=settings.server_port, reload=settings.debug)

