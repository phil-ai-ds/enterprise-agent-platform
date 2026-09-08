"""API：Agent 对话（M4 runtime）+ 多 Agent 流程（M3 orchestration）。

对话与工作区解耦：请求显式携带 workspace_id（本次在哪工作）与 folder（工作目录），
可选 refs 参考路径；服务端读文本注入上下文，并把该位置记忆为该用户在此 Agent 上的
默认工作位置（下次自动选中，用户仍可手动切换）。
"""
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import orchestration
from . import workspaces as wsvc
from .api_routes import visible_agents
from .config import settings
from .db import get_db
from .deps import get_current_user
from .models import User

router = APIRouter()


class ChatIn(BaseModel):
    message: str
    refs: list[str] = []  # 工作区内相对路径（文件或文件夹），作为本次任务的参考上下文
    workspace_id: int | None = None  # 本次会话工作区；None → 按该 Agent 默认空间
    folder: str = ""  # 工作目录（相对 workspace 根；空=根）


class WsPrefIn(BaseModel):
    workspace_id: int
    folder: str = ""


def build_ref_instructions(db: Session, ws, refs: list[str]) -> str:
    """读取指定工作区中的参考路径，生成注入 agent 的参考上下文指令（路径相对 ws 根）。"""
    if not refs:
        return ""
    root = wsvc.ws_root(settings.data_dir, ws)
    root_real = os.path.realpath(root)
    parts = ["用户指定了以下参考材料，请优先基于这些材料工作；回答里涉及引用时标注对应文件名。"]
    n = 0
    for ref in refs[:12]:
        ref = (ref or "").strip().replace("\\", "/").lstrip("/")
        if not ref:
            continue
        try:
            target = wsvc.safe_rel(root, ref)
        except ValueError:
            continue
        if not os.path.exists(target):
            parts.append(f"- ⚠️ {ref}（不存在，可能已删除）")
            continue
        rel = os.path.relpath(target, root_real)
        if os.path.isdir(target):
            try:
                entries = sorted(os.listdir(target))
            except OSError:
                entries = []
            head = entries[:15]
            more = f"…等共 {len(entries)} 项" if len(entries) > 15 else ""
            parts.append(f"- 📁 目录 {rel}/：{'、'.join(head)}{more}")
        else:
            size = os.path.getsize(target)
            if size > 200 * 1024:
                parts.append(f"- 📄 {rel}（{size} 字节，文件较大未全文载入，如需请用 read_file 工具查看）")
                continue
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                parts.append(f"- 📄 {rel}（读取失败）")
                continue
            content = content[:6000]
            parts.append(f"- 📄 文件 {rel} 内容如下：\n```\n{content}\n```")
        n += 1
        if n >= 8:
            parts.append("（更多参考路径略，如需处理请在对话中说明）")
            break
    return "\n\n".join(parts)


def _resolve_chat_workspace(db: Session, user: User, agent, ws_id: int | None):
    """解析本次对话工作区：显式指定（须可见）→ 否则 Agent 默认空间。"""
    if ws_id:
        ws = wsvc.resolve_ws(db, user, ws_id)
        if ws is None:
            raise HTTPException(403, "工作区不存在或无权访问")
        return ws
    ws = wsvc.agent_default_workspace(db, user, agent)
    if ws is None:
        raise HTTPException(400, "Agent 没有可用工作区")
    return ws


@router.post("/agents/{agent_id}/chat")
def chat(agent_id: int, body: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agent = next((a for a in visible_agents(db, user) if a.id == agent_id), None)
    if not agent:
        raise HTTPException(403, "无权访问该 Agent 或 Agent 不存在")
    if not body.message.strip():
        raise HTTPException(400, "消息不能为空")
    ws = _resolve_chat_workspace(db, user, agent, body.workspace_id)
    try:
        folder = wsvc.clean_folder(body.folder)
    except ValueError:
        raise HTTPException(400, "工作目录非法（不能包含 ..）")
    from .runtime import run_agent_chat
    # 组装参考上下文：工作区/工作目录说明 + 参考文件内容
    ctx_parts = [f"本次工作区：{wsvc.workspace_label(ws)}（{ws.name}）。"
                 f"当前工作目录：/{folder or ''}。write_file / read_file / list_workspace 的路径都相对当前工作目录"
                 f"{'（可用 ../ 访问工作区其它位置）' if folder else ''}。"
                 f"没有特别说明时，请把产出文件写到当前工作目录。"]
    ref_ctx = build_ref_instructions(db, ws, body.refs or [])
    if ref_ctx:
        ctx_parts.append(ref_ctx)
    # 记忆：该用户在此 Agent 上的默认工作位置（下次自动选中）
    try:
        wsvc.set_agent_ws_pref(db, user, agent, ws, folder)
    except ValueError:
        pass
    try:
        return run_agent_chat(db, user, agent, body.message, settings.data_dir,
                              extra_instructions="\n\n".join(ctx_parts), refs=body.refs or [],
                              workspace_id=ws.id, folder=folder)
    except RuntimeError as e:
        # Agent 循环/模型调用失败：给可读错误（含各形态的失败原因），前端 toast 可见
        raise HTTPException(502, f"Agent 调用失败：{e}"[:500])


@router.put("/agents/{agent_id}/ws-pref")
def save_ws_pref(agent_id: int, body: WsPrefIn,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """手动切换工作区/文件夹时立即记忆（Agent 下次默认选中这里）。"""
    agent = next((a for a in visible_agents(db, user) if a.id == agent_id), None)
    if not agent:
        raise HTTPException(403, "无权访问该 Agent 或 Agent 不存在")
    ws = wsvc.resolve_ws(db, user, body.workspace_id)
    if ws is None:
        raise HTTPException(403, "工作区不存在或无权访问")
    try:
        wsvc.set_agent_ws_pref(db, user, agent, ws, body.folder)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "workspace_id": ws.id, "folder": body.folder}


class FlowStart(BaseModel):
    task: str


class FlowApprove(BaseModel):
    approved: bool
    feedback: str = ""


@router.post("/flows/draft-review")
def flow_start(body: FlowStart, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.task.strip():
        raise HTTPException(400, "任务不能为空")
    run = orchestration.start_flow(db, user, body.task)
    return {"run_id": run.id, "status": run.status, "draft": run.draft,
            "tip": "草稿已生成，等待人工审批。请在下方审批（通过 → Agent B 评审；驳回 → 结束并附意见）。"}


@router.post("/flows/{run_id}/approve")
def flow_approve(run_id: str, body: FlowApprove, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        run = orchestration.approve_flow(db, user, run_id, body.approved, body.feedback)
    except LookupError:
        raise HTTPException(404, "flow run not found")
    return {"run_id": run.id, "status": run.status, "draft": run.draft,
            "final": run.final, "feedback": run.feedback}


@router.get("/flows/{run_id}")
def flow_get(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        run = orchestration.get_run(db, user, run_id)
    except LookupError:
        raise HTTPException(404, "flow run not found")
    return {"run_id": run.id, "status": run.status, "task": run.task, "draft": run.draft,
            "final": run.final, "feedback": run.feedback}


@router.get("/flows")
def flow_list(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models import FlowRun
    rows = db.query(FlowRun).filter(FlowRun.user_id == user.id).order_by(FlowRun.created_at.desc()).limit(20).all()
    return [{"run_id": r.id, "status": r.status, "task": r.task[:120], "created_at":
             r.created_at.isoformat() if r.created_at else None} for r in rows]
