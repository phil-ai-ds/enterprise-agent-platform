import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api_ai import router as ai_router
from .api_builder import router as builder_router
from .api_flows import router as flows_router
from .api_routes import router as api_router
from .api_workspaces import router as workspaces_router
from .config import settings
from .seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.data_dir, exist_ok=True)
    seed()
    yield


app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(builder_router, prefix="/api")
app.include_router(flows_router, prefix="/api")
app.include_router(workspaces_router, prefix="/api")
app.include_router(ai_router, prefix="/api")

_frontend = Path(settings.frontend_dir)
if not _frontend.is_absolute():
    _frontend = Path(__file__).resolve().parent.parent.parent / settings.frontend_dir
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
