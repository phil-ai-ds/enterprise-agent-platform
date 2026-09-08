"""Workspace API：个人/团队/组织空间的浏览、上传、下载、删除；Agent 绑定的工作区也由此管理。"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import workspaces as wsvc
from .config import settings
from .db import get_db
from .deps import get_current_user
from .models import Agent, User, Workspace

router = APIRouter()


def _err(msg: str, code: int = 400):
    raise HTTPException(code, msg)


def _get_ws_or_403(db: Session, user: User, ws_id: int) -> Workspace:
    ws = db.get(Workspace, ws_id)
    if not ws or not wsvc.can_read_ws(user, ws):
        _err("工作区不存在或无权访问", 403)
    return ws


def _write_guard(user: User, ws: Workspace):
    if not wsvc.can_write_ws(user, ws):
        _err("该工作区只读（无写入权限）", 403)


@router.get("/workspaces")
def list_workspaces(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """我可见的工作区（含个人/团队/组织），附文件计数。"""
    out = []
    for ws in wsvc.visible_workspaces(db, user):
        root = wsvc.ws_root(settings.data_dir, ws)
        n_files = sum(1 for x in wsvc.list_tree(db, ws, settings.data_dir) if x["kind"] == "file") if os.path.isdir(root) else 0
        out.append({
            "id": ws.id, "kind": ws.kind, "name": ws.name,
            "label": wsvc.workspace_label(ws),
            "owner_id": ws.owner_id, "team_id": ws.team_id,
            "can_write": wsvc.can_write_ws(user, ws),
            "file_count": n_files,
        })
    return out


@router.get("/workspaces/{ws_id}/files")
def list_ws_files(ws_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = _get_ws_or_403(db, user, ws_id)
    return {"workspace": {"id": ws.id, "name": ws.name, "label": wsvc.workspace_label(ws),
                          "kind": ws.kind, "can_write": wsvc.can_write_ws(user, ws)},
            "files": wsvc.list_tree(db, ws, settings.data_dir)}


@router.post("/workspaces/{ws_id}/files")
async def upload_ws_file(ws_id: int, file: UploadFile, path: str = "",
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """上传文件到工作区。path 可选子目录（相对）。"""
    ws = _get_ws_or_403(db, user, ws_id)
    _write_guard(user, ws)
    root = wsvc.ws_root(settings.data_dir, ws)
    root_real = os.path.realpath(root)
    rel_dir = path.strip().strip("/").replace("\\", "/") if path else ""
    # 文件名防穿越：只取 basename
    fname = os.path.basename((file.filename or "unnamed").replace("\\", "/"))
    if not fname:
        _err("文件名无效")
    # 目标 = 子目录(可选) + 文件名；用 safe_rel 统一校验越界
    rel_target = os.path.join(rel_dir, fname).replace("\\", "/")
    try:
        target = wsvc.safe_rel(root, rel_target)
    except ValueError as e:
        _err(str(e))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if not target.startswith(root_real + os.sep):
        _err("非法路径")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        _err("文件超过 50MB 限制")
    with open(target, "wb") as f:
        f.write(content)
    rel = os.path.relpath(target, root)
    wsvc.upsert_file_record(db, ws.id, rel, len(content), user.id)
    return {"ok": True, "path": rel, "size": len(content)}


@router.get("/workspaces/{ws_id}/download")
def download_ws_file(ws_id: int, path: str,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = _get_ws_or_403(db, user, ws_id)
    root = wsvc.ws_root(settings.data_dir, ws)
    try:
        target = wsvc.safe_rel(root, path)
    except ValueError as e:
        _err(str(e))
    if not os.path.isfile(target):
        _err("文件不存在", 404)
    return FileResponse(target, filename=os.path.basename(target))


@router.delete("/workspaces/{ws_id}/files")
def delete_ws_file(ws_id: int, path: str,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = _get_ws_or_403(db, user, ws_id)
    _write_guard(user, ws)
    root = wsvc.ws_root(settings.data_dir, ws)
    try:
        target = wsvc.safe_rel(root, path)
    except ValueError as e:
        _err(str(e))
    if not os.path.exists(target):
        _err("不存在", 404)
    if os.path.isdir(target):
        for cur, dirs, files in os.walk(target, topdown=False):
            for f in files:
                os.remove(os.path.join(cur, f))
                wsvc.remove_file_record(db, ws.id, os.path.relpath(os.path.join(cur, f), root))
            for d in dirs:
                os.rmdir(os.path.join(cur, d))
        os.rmdir(target)
    else:
        os.remove(target)
        wsvc.remove_file_record(db, ws.id, path)
    return {"ok": True, "path": path}


class TextWriteIn(BaseModel):
    path: str
    content: str


@router.post("/workspaces/{ws_id}/text")
def write_ws_text(ws_id: int, body: TextWriteIn,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """直接在工作区写入/新建文本文件（前端“新建文档”）。"""
    ws = _get_ws_or_403(db, user, ws_id)
    _write_guard(user, ws)
    root = wsvc.ws_root(settings.data_dir, ws)
    try:
        target = wsvc.safe_rel(root, body.path)
    except ValueError as e:
        _err(str(e))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(body.content)
    rel = os.path.relpath(target, root)
    wsvc.upsert_file_record(db, ws.id, rel, len(body.content.encode("utf-8")), user.id)
    return {"ok": True, "path": rel}


@router.get("/workspaces/{ws_id}/text")
def read_ws_text(ws_id: int, path: str,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = _get_ws_or_403(db, user, ws_id)
    root = wsvc.ws_root(settings.data_dir, ws)
    try:
        target = wsvc.safe_rel(root, path)
    except ValueError as e:
        _err(str(e))
    if not os.path.isfile(target):
        _err("文件不存在", 404)
    size = os.path.getsize(target)
    if size > 2 * 1024 * 1024:
        _err("文件过大，请下载查看")
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return {"path": path, "content": content, "size": size}
