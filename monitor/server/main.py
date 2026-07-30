"""FastAPI 服务端入口"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, Signer

from database import connect_db, close_db
from routers import servers, monitor, auth
from config import STATIC_DIR, API_PREFIX, SERVER_PORT, SESSION_SECRET_KEY

auth_signer = Signer(SESSION_SECRET_KEY)
AUTH_COOKIE = "monitor_auth"


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
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(servers.router, prefix=API_PREFIX)
app.include_router(monitor.router, prefix=API_PREFIX)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path

    # 放行认证接口、静态资源、客户端上报接口
    if path.startswith(f"{API_PREFIX}/auth"):
        return await call_next(request)
    if path.startswith("/assets") or path == "/favicon.ico":
        return await call_next(request)
    if path.startswith(f"{API_PREFIX}/servers/register") or path.startswith(f"{API_PREFIX}/servers/") and path.endswith("/metrics"):
        return await call_next(request)

    # 其余 API 需要登录；页面由前端自行显示登录页
    if path.startswith(API_PREFIX):
        cookie = request.cookies.get(AUTH_COOKIE)
        if not cookie:
            return JSONResponse(status_code=401, content={"detail": "未登录"})

        try:
            auth_signer.unsign(cookie)
        except BadSignature:
            return JSONResponse(status_code=401, content={"detail": "未登录"})

    return await call_next(request)


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
