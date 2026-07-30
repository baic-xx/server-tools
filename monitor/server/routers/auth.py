"""认证 API — 登录、登出、登录态查询"""
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request, Response, status
from itsdangerous import BadSignature, Signer
from config import ADMIN_PASSWORD, SESSION_SECRET_KEY

router = APIRouter(prefix="/auth", tags=["认证"])
auth_signer = Signer(SESSION_SECRET_KEY)
AUTH_COOKIE = "monitor_auth"


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
async def login(data: LoginRequest, response: Response):
    if data.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="密码错误")

    token = auth_signer.sign(b"authenticated").decode("utf-8")
    response.set_cookie(
        AUTH_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=7 * 24 * 60 * 60,
        path="/",
    )
    return {"message": "登录成功"}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(AUTH_COOKIE, path="/")
    return {"message": "已退出登录"}


@router.get("/me")
async def me(request: Request):
    cookie = request.cookies.get(AUTH_COOKIE)
    if not cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    try:
        auth_signer.unsign(cookie)
    except BadSignature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    return {"authenticated": True}