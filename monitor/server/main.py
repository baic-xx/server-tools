"""FastAPI 服务端入口"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import connect_db, close_db
from routers import servers, monitor
from config import STATIC_DIR, API_PREFIX, SERVER_PORT


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    await connect_db()
    yield
    await close_db()


app = FastAPI(
    title="服务器监控平台",
    description="集中管理和监控 GPU 服务器运行状态",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — 开发时允许所有来源，生产环境应限制
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(servers.router, prefix=API_PREFIX)
app.include_router(monitor.router, prefix=API_PREFIX)


# ─── 静态文件（Vue 构建产物）───

if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA fallback — 所有未匹配的路由返回 index.html"""
        file_path = os.path.join(STATIC_DIR, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=SERVER_PORT, reload=True)
