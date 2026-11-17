# -*- coding: utf-8 -*-
"""用户服务：注册/登录/用户列表（6.5 user + admin/users）。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, User
from ..security import create_token, get_current_user, hash_password, require_admin, verify_password

router = APIRouter()


class RegisterIn(BaseModel):
    username: str
    password: str
    real_name: str = ""
    role: str = "student"
    tenant_id: str = "default"


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/api/v1/users", tags=["用户服务"])
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(400, "用户名已存在")
    u = User(username=body.username, password_hash=hash_password(body.password),
             real_name=body.real_name, role=body.role, tenant_id=body.tenant_id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"id": u.id, "username": u.username, "role": u.role, "tenant_id": u.tenant_id}


@router.post("/api/v1/users/login", tags=["用户服务"])
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.username == body.username))
    if not u or not verify_password(body.password, u.password_hash):
        db.add(AuditLog(action="login_failed", target=body.username))
        db.commit()
        raise HTTPException(401, "用户名或密码错误")
    db.add(AuditLog(action="login", target=body.username, operator=body.username))
    db.commit()
    return {"token": create_token(u.id, u.username, u.role), "user": {
        "id": u.id, "username": u.username, "real_name": u.real_name,
        "role": u.role, "tenant_id": u.tenant_id, "credit_score": u.credit_score,
    }}


@router.get("/api/v1/users/me", tags=["用户服务"])
def me(payload: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    u = db.get(User, int(payload["sub"]))
    if not u:
        raise HTTPException(404, "用户不存在")
    return {"id": u.id, "username": u.username, "real_name": u.real_name,
            "role": u.role, "tenant_id": u.tenant_id, "credit_score": u.credit_score}


@router.get("/api/v1/admin/users", tags=["运营管理服务"])
def list_users(page: int = 1, size: int = 20, tenant_id: str | None = None,
               db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    q = select(User)
    if tenant_id:
        q = q.where(User.tenant_id == tenant_id)
    total = len(db.scalars(q).all())
    rows = db.scalars(q.order_by(User.id).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "items": [
        {"id": u.id, "username": u.username, "real_name": u.real_name, "role": u.role,
         "tenant_id": u.tenant_id, "credit_score": u.credit_score, "is_active": u.is_active}
        for u in rows]}
