"""Workspace 服务：个人/团队/组织工作区的解析、权限、磁盘目录与文件操作。

磁盘布局: data_dir/workspaces/w{workspace_id}/
Agent 工具与文件 API 共用本模块，保证同一工作区同一视角。
"""
import mimetypes
import os
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .models import Team, User, Workspace, WorkspaceFile

# ---------------- 目录解析 ----------------


def ws_root(data_dir: str, ws: Workspace) -> str:
    d = os.path.join(data_dir, "workspaces", f"w{ws.id}")
    os.makedirs(d, exist_ok=True)
    return d


def workspace_label(ws: Workspace) -> str:
    if ws.kind == "team":
        return f"团队 · {ws.team.name if ws.team else ws.name}"
    if ws.kind == "org":
        return "组织 · 全员共享"
    owner = ws.owner.display_name if ws.owner else ws.owner_id
    return f"个人 · {owner}"


def ensure_personal(db: Session, user: User) -> Workspace:
    """每个用户都有个人工作区（懒创建）。"""
    ws = db.query(Workspace).filter(Workspace.kind == "personal", Workspace.owner_id == user.id).first()
    if not ws:
        ws = Workspace(kind="personal", name=f"{user.display_name} 的个人空间", owner_id=user.id)
        db.add(ws)
        db.commit()
        db.refresh(ws)
    return ws


def ensure_team(db: Session, team: Team) -> Workspace:
    ws = db.query(Workspace).filter(Workspace.kind == "team", Workspace.team_id == team.id).first()
    if not ws:
        ws = Workspace(kind="team", name=f"{team.name} 团队空间", team_id=team.id)
        db.add(ws)
        db.commit()
        db.refresh(ws)
    return ws


def ensure_org(db: Session) -> Workspace:
    ws = db.query(Workspace).filter(Workspace.kind == "org").first()
    if not ws:
        ws = Workspace(kind="org", name="组织空间")
        db.add(ws)
        db.commit()
        db.refresh(ws)
    return ws


# ---------------- 可见性与权限 ----------------


def visible_workspaces(db: Session, user: User) -> list[Workspace]:
    """用户可见工作区：自己的个人空间 + 所在团队空间 + 组织空间。"""
    conds = [Workspace.kind == "org"]
    conds.append(Workspace.owner_id == user.id)
    if user.team_id:
        conds.append(Workspace.team_id == user.team_id)
    return db.query(Workspace).filter(or_(*conds)).order_by(Workspace.id).all()


def can_read_ws(user: User, ws: Workspace) -> bool:
    if ws.kind == "org" or user.role == "platform_admin":
        return True
    if ws.kind == "personal":
        return ws.owner_id == user.id
    if ws.kind == "team":
        return ws.team_id == user.team_id
    return False


def can_write_ws(user: User, ws: Workspace) -> bool:
    # 读写同权：个人空间仅本人；团队空间成员可写；org 全员可写
    return can_read_ws(user, ws)


def agent_default_workspace(db: Session, user: User, agent) -> Workspace | None:
    """Agent 未显式绑定 workspace 时按其 scope 解析默认空间。"""
    if agent.workspace_id:
        return db.get(Workspace, agent.workspace_id)
    if agent.scope == "org":
        return ensure_org(db)
    if agent.scope == "team" and agent.team_id:
        team = db.get(Team, agent.team_id)
        if team:
            return ensure_team(db, team)
    return ensure_personal(db, user)


def resolve_ws(db: Session, user: User, ws_id: int) -> Workspace | None:
    """按 id 取工作区并校验当前用户可读；不可见返回 None。"""
    ws = db.get(Workspace, ws_id)
    if ws and can_read_ws(user, ws):
        return ws
    return None


def clean_folder(folder: str | None) -> str:
    """清洗文件夹参数：反斜杠转正、去首尾 /、防 .. 段。非法返回 '' 或抛 ValueError。"""
    f = (folder or "").strip().replace("\\", "/").strip("/")
    if not f:
        return ""
    segs = [s for s in f.split("/") if s and s not in (".",)]
    if any(s == ".." for s in segs):
        raise ValueError("文件夹不能包含 ..")
    return "/".join(segs)


def get_agent_ws_pref(db: Session, user: User, agent) -> tuple[Workspace | None, str]:
    """该用户在此 Agent 上记忆的工作区 + 文件夹；无记忆或记忆失效 → 按 Agent 默认空间。"""
    from .models import AgentWsPref
    row = db.query(AgentWsPref).filter(AgentWsPref.agent_id == agent.id,
                                       AgentWsPref.user_id == user.id).first()
    if row:
        ws = db.get(Workspace, row.workspace_id)
        if ws and can_read_ws(user, ws):
            return ws, row.folder or ""
        db.delete(row)
        db.commit()
    return agent_default_workspace(db, user, agent), ""


def set_agent_ws_pref(db: Session, user: User, agent, ws: Workspace, folder: str = ""):
    """记住该用户在此 Agent 上工作的工作区 + 文件夹（Agent 与工作区解耦的『默认位置』）。"""
    from .models import AgentWsPref
    folder = clean_folder(folder)
    row = db.query(AgentWsPref).filter(AgentWsPref.agent_id == agent.id,
                                       AgentWsPref.user_id == user.id).first()
    if not row:
        row = AgentWsPref(agent_id=agent.id, user_id=user.id,
                          workspace_id=ws.id, folder=folder)
        db.add(row)
    else:
        row.workspace_id = ws.id
        row.folder = folder
    db.commit()


# ---------------- 安全路径 ----------------


def safe_rel(root: str, rel: str) -> str:
    """把用户/Agent 给的相对路径规范到 root 内，越界抛 ValueError。"""
    rel = rel.replace("\\", "/").lstrip("/")
    target = os.path.realpath(os.path.join(root, rel))
    base = os.path.realpath(root)
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("路径越界：只能访问该工作区内")
    return target


def list_tree(db: Session, ws: Workspace, data_dir: str) -> list[dict]:
    """扫描磁盘目录树，返回 {path, kind, size, mtime}。与 DB 元数据无关（Agent 也直接写盘）。"""
    root = ws_root(data_dir, ws)
    out = []
    for cur, dirs, files in os.walk(root):
        # 隐藏目录（.git 等）不展示
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        rel_dir = os.path.relpath(cur, root)
        for d in dirs:
            rel = os.path.relpath(os.path.join(cur, d), root)
            out.append({"path": rel, "kind": "dir", "size": 0,
                        "mtime": datetime.fromtimestamp(os.path.getmtime(os.path.join(cur, d))).isoformat()})
        for f in files:
            if f.startswith("."):
                continue
            fp = os.path.join(cur, f)
            rel = os.path.relpath(fp, root)
            st = os.stat(fp)
            out.append({"path": rel, "kind": "file", "size": st.st_size,
                        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat()})
    out.sort(key=lambda x: (x["kind"] != "dir", x["path"].lower()))
    return out


def upsert_file_record(db: Session, ws_id: int, rel: str, size: int, created_by: int | None):
    """记录/刷新文件元数据（Agent 写入的文件也会被登记，便于统一浏览）。"""
    row = db.query(WorkspaceFile).filter(WorkspaceFile.workspace_id == ws_id,
                                         WorkspaceFile.rel_path == rel,
                                         WorkspaceFile.kind == "file").first()
    mime, _ = mimetypes.guess_type(rel)
    if row:
        row.size = size
        row.mime = mime or ""
        row.updated_at = datetime.utcnow()
    else:
        row = WorkspaceFile(workspace_id=ws_id, rel_path=rel, kind="file",
                            mime=mime or "", size=size, created_by=created_by)
        db.add(row)
    db.commit()


def remove_file_record(db: Session, ws_id: int, rel: str):
    db.query(WorkspaceFile).filter(WorkspaceFile.workspace_id == ws_id,
                                   WorkspaceFile.rel_path == rel).delete()
    db.commit()
