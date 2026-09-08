"""构建者 API：用户自助构建闭环 —— 建 Agent / 建-迭代-版本化-发布-API化-分享-复制 技能 / 建并运行工作流。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import executor, skills as skill_svc
from .config import settings
from .db import get_db
from .deps import get_current_user
from .models import (
    Agent, AgentSkill, Skill, SkillVersion, User, Workflow, WorkflowRun, Workspace,
)
from .providers import get_provider

router = APIRouter()


def err(msg: str, code: int = 400):
    raise HTTPException(code, msg)


# ---------------- Skills：完整生命周期 ----------------
class SkillCreate(BaseModel):
    name: str
    description: str = ""
    content: str = ""
    scope: str = "private"  # private | team | org


class SkillPatch(BaseModel):
    description: str | None = None
    scope: str | None = None  # 分享/可见范围


class SkillVersionNew(BaseModel):
    content: str
    change_note: str = ""


class SkillInvoke(BaseModel):
    input: str
    version_id: int | None = None


@router.get("/skills")
def list_skills(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = []
    for s in skill_svc.visible_skills(db, user):
        vers = skill_svc.skill_versions(db, s.id)
        out.append({
            "id": s.id, "name": s.name, "description": s.description, "scope": s.scope,
            "owner_id": s.owner_id, "owner": s.owner.username if s.owner else "?",
            "api_enabled": s.api_enabled, "can_edit": skill_svc.can_edit(user, s),
            "versions": [{"id": v.id, "version": v.version, "status": v.status,
                          "change_note": v.change_note} for v in vers],
        })
    return out


@router.post("/skills")
def create_skill(body: SkillCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models import Team
    name = body.name.strip()
    if not name:
        err("技能名不能为空")
    if db.query(Skill).filter(Skill.name == name).first():
        err(f"技能名 '{name}' 已存在，请换一个或使用复制")
    if body.scope not in ("private", "team", "org"):
        err("scope 仅支持 private/team/org")
    if body.scope == "team" and not user.team_id:
        err("你不在任何团队中，无法创建 team 范围技能（可用 org/private）")
    s = Skill(name=name, description=body.description, scope=body.scope,
              owner_id=user.id, team_id=user.team_id if body.scope == "team" else None)
    db.add(s)
    db.flush()
    db.add(SkillVersion(skill_id=s.id, version=1, content=body.content, status="draft", created_by=user.id))
    db.commit()
    return {"id": s.id, "name": s.name}


@router.get("/skills/{sid}")
def skill_detail(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s or s not in skill_svc.visible_skills(db, user):
        err("技能不存在或无权访问", 404)
    vers = skill_svc.skill_versions(db, sid)
    used_by = db.query(AgentSkill).filter(AgentSkill.skill_id == sid).count()
    return {
        "id": s.id, "name": s.name, "description": s.description, "scope": s.scope,
        "owner_id": s.owner_id, "owner": s.owner.username if s.owner else "?",
        "api_enabled": s.api_enabled, "can_edit": skill_svc.can_edit(user, s),
        "used_by_agents": used_by,
        "api_url": f"/api/skills/{s.id}/invoke" if s.api_enabled else None,
        "versions": [{"id": v.id, "version": v.version, "status": v.status,
                      "content": v.content, "change_note": v.change_note,
                      "created_at": v.created_at.isoformat() if v.created_at else None,
                      "published_at": v.published_at.isoformat() if v.published_at else None}
                     for v in vers],
    }


@router.patch("/skills/{sid}")
def patch_skill(sid: int, body: SkillPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s or s not in skill_svc.visible_skills(db, user) or not skill_svc.can_edit(user, s):
        err("技能不存在或无权编辑", 403)
    if body.scope:
        if body.scope not in ("private", "team", "org"):
            err("scope 非法")
        if body.scope == "team" and not user.team_id:
            err("你不在任何团队中，无法分享到 team")
        s.scope = body.scope
        s.team_id = user.team_id if body.scope == "team" else None
    if body.description is not None:
        s.description = body.description
    db.commit()
    return {"id": s.id, "scope": s.scope}


@router.post("/skills/{sid}/versions")
def new_skill_version(sid: int, body: SkillVersionNew, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s or not skill_svc.can_edit(user, s):
        err("无权操作", 403)
    vers = skill_svc.skill_versions(db, sid)
    nxt = max((v.version for v in vers), default=0) + 1
    db.add(SkillVersion(skill_id=sid, version=nxt, content=body.content,
                        change_note=body.change_note, status="draft", created_by=user.id))
    db.commit()
    return {"id": s.id, "next_version": nxt}


@router.patch("/skills/{sid}/versions/{vid}")
def patch_skill_version(sid: int, vid: int, body: SkillVersionNew,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.get(SkillVersion, vid)
    if not v or v.skill_id != sid:
        err("版本不存在", 404)
    if not skill_svc.can_edit(user, v.skill or db.get(Skill, sid)):
        err("无权编辑", 403)
    if v.status != "draft":
        err("已发布的版本不可修改——请创建新草稿版本迭代")
    v.content = body.content
    v.change_note = body.change_note
    db.commit()
    return {"id": v.id, "version": v.version, "status": v.status}


@router.post("/skills/{sid}/versions/{vid}/publish")
def publish_skill_version(sid: int, vid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    v = db.get(SkillVersion, vid)
    if not s or not v or v.skill_id != sid:
        err("技能或版本不存在", 404)
    if not skill_svc.can_edit(user, s):
        err("无权发布", 403)
    if v.status == "published":
        err(f"v{v.version} 已是 published")
    from datetime import datetime, timezone
    v.status = "published"
    v.published_at = datetime.now(timezone.utc)
    # 发布即分享：private 技能至少升到 team 可见（发布给团队），否则别人无法发现/使用
    if s.scope == "private":
        s.scope = "team" if s.owner.team_id else "org"
        s.team_id = s.owner.team_id if s.scope == "team" else None
    db.commit()
    return {"id": s.id, "name": s.name, "version": v.version, "status": v.status, "scope": s.scope}


@router.post("/skills/{sid}/api")
def toggle_skill_api(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """把技能发布成 API（需至少一个 published 版本）。"""
    s = db.get(Skill, sid)
    if not s or not skill_svc.can_edit(user, s):
        err("无权操作", 403)
    latest = skill_svc.latest_published_version(db, sid)
    if not latest:
        err("请先发布至少一个版本，再开启 API")
    s.api_enabled = not s.api_enabled
    db.commit()
    return {"api_enabled": s.api_enabled, "endpoint": f"/api/skills/{s.id}/invoke",
            "method": "POST", "body": '{"input": "..."}',
            "auth": "Authorization: Bearer <token>"}


@router.post("/skills/{sid}/invoke")
def invoke_skill_api(sid: int, body: SkillInvoke, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """调用技能（发布成 API 后任何可见用户可调用；作者也可随时用未发布版本测试）。"""
    s = db.get(Skill, sid)
    if not s or s not in skill_svc.visible_skills(db, user):
        err("技能不存在或无权访问", 404)
    if body.version_id:
        if not skill_svc.can_edit(user, s):
            err("仅作者/管理员可调用指定草稿版本")
        ver = db.get(SkillVersion, body.version_id)
        if not ver or ver.skill_id != sid:
            err("版本不存在", 404)
        kind = "skill_test"
    else:
        ver = skill_svc.latest_published_version(db, sid)
        if not ver:
            err("该技能还没有已发布版本")
        if not s.api_enabled and not skill_svc.can_edit(user, s):
            err("该技能未开放 API，仅作者可测试")
        kind = "skill_api" if s.api_enabled else "skill_test"
    provider = get_provider(db)
    out = executor.run_skill(db, user, ver, s.name, body.input, kind=kind, provider=provider)
    return {"skill_id": s.id, **out}


@router.post("/skills/{sid}/fork")
def fork_skill(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """复制（分享后复用）：把可见技能+全部已发布版本复制为我的私有技能。"""
    s = db.get(Skill, sid)
    if not s or s not in skill_svc.visible_skills(db, user):
        err("技能不存在或无权访问", 404)
    name = skill_svc.unique_skill_name(db, s.name + "-副本")
    s2 = Skill(name=name, description=f"由 {s.name} 复制：{s.description}", scope="private",
               owner_id=user.id, team_id=None)
    db.add(s2)
    db.flush()
    n = 0
    for v in skill_svc.skill_versions(db, sid):
        if v.status in ("published", "draft"):
            db.add(SkillVersion(skill_id=s2.id, version=v.version, content=v.content,
                                change_note=v.change_note, status=v.status,
                                created_by=user.id,
                                published_at=v.published_at))
            n += 1
    db.commit()
    return {"id": s2.id, "name": s2.name, "copied_versions": n}


@router.delete("/skills/{sid}")
def delete_skill(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s or not skill_svc.can_edit(user, s):
        err("技能不存在或无权删除", 403)
    used = db.query(AgentSkill).filter(AgentSkill.skill_id == sid).count()
    wf_used = sum(1 for w in db.query(Workflow).all() for st in (w.steps or []) if st.get("skill_id") == sid)
    if used or wf_used:
        err(f"技能正被 {used} 个 Agent / {wf_used} 个工作流引用，请先解绑（可改为废弃版本而非删除）")
    for v in skill_svc.skill_versions(db, sid):
        db.delete(v)
    db.delete(s)
    db.commit()
    return {"ok": True}


# ---------------- Agents：用户自建与迭代 ----------------
class AgentBinding(BaseModel):
    skill_id: int
    version_id: int | None = None


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    scope: str = "user"  # user | team | org
    provider_id: int | None = None
    model: str = ""
    workspace_id: int | None = None  # None=按 scope 自动（个人→个人空间/团队→团队空间/org→组织空间）
    skill_bindings: list[AgentBinding] = []


@router.post("/agents")
def create_agent(body: AgentCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        err("Agent 名不能为空")
    if db.query(Agent).filter(Agent.name == name).first():
        err("Agent 名已存在")
    provider = get_provider(db, body.provider_id) if body.provider_id else get_provider(db)
    if body.scope not in ("user", "team", "org"):
        err("scope 非法")
    if body.scope == "team" and not user.team_id:
        err("你不在团队中，无法创建 team Agent")
    ws_id = body.workspace_id
    if ws_id is None:
        # 按 scope 解析默认工作区
        from . import workspaces as wsvc
        ws = wsvc.agent_default_workspace(db, user, type("A", (), {
            "scope": body.scope, "team_id": user.team_id if body.scope == "team" else None,
            "workspace_id": None})())
        ws_id = ws.id if ws else None
    a = Agent(name=name, description=body.description, system_prompt=body.system_prompt,
              scope=body.scope, provider_id=provider.id, model=body.model or provider.default_model,
              owner_id=user.id, team_id=user.team_id if body.scope == "team" else None,
              workspace_id=ws_id)
    db.add(a)
    db.flush()
    bind_skills(db, a, user, body.skill_bindings)
    db.commit()
    return {"id": a.id, "name": a.name}


def bind_skills(db: Session, agent: Agent, user: User, bindings: list[AgentBinding]):
    db.query(AgentSkill).filter(AgentSkill.agent_id == agent.id).delete()
    visible = skill_svc.visible_skills(db, user)
    for b in bindings:
        s = db.get(Skill, b.skill_id)
        if not s or s not in visible:
            continue
        ver = None
        if b.version_id:
            ver = db.get(SkillVersion, b.version_id)
            if not ver or ver.skill_id != s.id:
                ver = None
        if ver is None:
            ver = skill_svc.latest_published_version(db, s.id)
        if ver is None and not skill_svc.can_edit(user, s):
            continue
        db.add(AgentSkill(agent_id=agent.id, skill_id=s.id, version_id=ver.id if ver else None))


@router.get("/agents/{aid}")
def agent_detail(aid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(Agent, aid)
    from .api_routes import visible_agents
    if not a or a not in visible_agents(db, user):
        err("Agent 不存在或无权访问", 404)
    binds = db.query(AgentSkill).filter(AgentSkill.agent_id == aid).all()
    bindings = []
    for b in binds:
        s = db.get(Skill, b.skill_id)
        ver = db.get(SkillVersion, b.version_id) if b.version_id else skill_svc.latest_published_version(db, b.skill_id)
        bindings.append({"skill_id": b.skill_id, "skill_name": s.name if s else "?",
                         "version_id": b.version_id, "version": ver.version if ver else None,
                         "status": ver.status if ver else "?"})
    from . import workspaces as wsvc
    ws = db.get(Workspace, a.workspace_id) if a.workspace_id else None
    if not ws:
        try:
            ws = wsvc.agent_default_workspace(db, user, a)
        except Exception:  # noqa: BLE001
            ws = None
    return {"id": a.id, "name": a.name, "description": a.description, "system_prompt": a.system_prompt,
            "scope": a.scope, "version": a.version, "provider_id": a.provider_id,
            "provider": a.provider.name if a.provider else "", "model": a.model,
            "owner_id": a.owner_id, "owner": a.owner.username if a.owner else "?",
            "can_edit": a.owner_id == user.id or user.role == "platform_admin",
            "workspace": {"id": ws.id, "name": ws.name, "kind": ws.kind,
                          "label": wsvc.workspace_label(ws)} if ws else None,
            "skill_bindings": bindings}


@router.patch("/agents/{aid}")
def patch_agent(aid: int, body: AgentCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(Agent, aid)
    if not a or (a.owner_id != user.id and user.role != "platform_admin"):
        err("无权编辑", 403)
    if body.name.strip() and body.name != a.name:
        if db.query(Agent).filter(Agent.name == body.name, Agent.id != aid).first():
            err("Agent 名已存在")
        a.name = body.name.strip()
    a.description = body.description
    a.system_prompt = body.system_prompt
    if body.scope in ("user", "team", "org"):
        a.scope = body.scope
        a.team_id = user.team_id if body.scope == "team" else None
    if body.provider_id:
        from .providers import get_provider as _gp
        p = _gp(db, body.provider_id)
        a.provider_id = p.id
        a.model = body.model or p.default_model
    if body.workspace_id is not None:
        from . import workspaces as wsvc
        ws = db.get(Workspace, body.workspace_id)
        if not ws or not wsvc.can_read_ws(user, ws):
            err("目标工作区不存在或无权使用")
        a.workspace_id = ws.id
    bind_skills(db, a, user, body.skill_bindings)
    a.version += 1
    db.commit()
    return {"id": a.id, "name": a.name, "version": a.version}


@router.delete("/agents/{aid}")
def delete_agent(aid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(Agent, aid)
    if not a or (a.owner_id != user.id and user.role != "platform_admin"):
        err("无权删除", 403)
    db.query(AgentSkill).filter(AgentSkill.agent_id == aid).delete()
    db.delete(a)
    db.commit()
    return {"ok": True}


# ---------------- Workflows：串联多个技能 ----------------
class WorkflowIn(BaseModel):
    name: str
    description: str = ""
    scope: str = "private"
    steps: list[dict] = []  # [{skill_id, version_id?, note}]


def visible_workflows(db: Session, user: User) -> list[Workflow]:
    from sqlalchemy import or_
    conds = [Workflow.scope == "org", Workflow.owner_id == user.id]
    if user.team_id:
        conds.append(Workflow.team_id == user.team_id)
    return db.query(Workflow).filter(or_(*conds)).order_by(Workflow.id.desc()).all()


def wf_dto(db: Session, wf: Workflow, detail: bool = False) -> dict:
    step_meta = []
    for st in (wf.steps or []):
        s = db.get(Skill, st.get("skill_id"))
        ver = skill_svc.resolve_version(db, st.get("skill_id"), st.get("version_id"))
        step_meta.append({"skill_id": st.get("skill_id"),
                          "skill_name": s.name if s else "?",
                          "version_id": st.get("version_id"),
                          "version": ver.version if ver else None,
                          "status": ver.status if ver else "?",
                          "note": st.get("note", "")})
    return {"id": wf.id, "name": wf.name, "description": wf.description, "scope": wf.scope,
            "owner_id": wf.owner_id, "owner": (db.get(User, wf.owner_id).username if wf.owner_id else "?"),
            "steps": step_meta if detail else len(step_meta)}


@router.get("/workflows")
def list_workflows(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [wf_dto(db, w) for w in visible_workflows(db, user)]


@router.post("/workflows")
def create_workflow(body: WorkflowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        err("工作流名不能为空")
    if db.query(Workflow).filter(Workflow.name == name).first():
        err("工作流名已存在")
    if not body.steps:
        err("至少选择 1 个已发布的技能作为步骤")
    if body.scope not in ("private", "team", "org"):
        err("scope 非法")
    wf = Workflow(name=name, description=body.description, steps=body.steps, scope=body.scope,
                  owner_id=user.id, team_id=user.team_id if body.scope == "team" else None)
    db.add(wf)
    db.commit()
    return {"id": wf.id, "name": wf.name}


@router.get("/workflows/runs/mine")
def my_workflow_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db), limit: int = 20):
    rows = db.query(WorkflowRun).filter(WorkflowRun.user_id == user.id).order_by(
        WorkflowRun.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "workflow_id": r.workflow_id,
             "workflow": (db.get(Workflow, r.workflow_id).name if db.get(Workflow, r.workflow_id) else "?"),
             "input": r.input_text[:120], "steps": len(r.steps_output or []),
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.get("/workflows/{wid}")
def workflow_detail(wid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wf = db.get(Workflow, wid)
    if not wf or wf not in visible_workflows(db, user):
        err("工作流不存在或无权访问", 404)
    return wf_dto(db, wf, detail=True)


@router.patch("/workflows/{wid}")
def patch_workflow(wid: int, body: WorkflowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wf = db.get(Workflow, wid)
    if not wf or wf not in visible_workflows(db, user):
        err("工作流不存在或无权访问", 404)
    if wf.owner_id != user.id and user.role != "platform_admin":
        err("无权编辑", 403)
    if body.name.strip():
        dup = db.query(Workflow).filter(Workflow.name == body.name.strip(), Workflow.id != wid).first()
        if dup:
            err("工作流名已存在")
        wf.name = body.name.strip()
    wf.description = body.description
    if body.scope in ("private", "team", "org"):
        wf.scope = body.scope
        wf.team_id = user.team_id if body.scope == "team" else None
    wf.steps = body.steps
    db.commit()
    return {"id": wf.id, "name": wf.name, "steps": len(wf.steps or [])}


@router.post("/workflows/{wid}/run")
def run_workflow(wid: int, body: SkillInvoke, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wf = db.get(Workflow, wid)
    if not wf or wf not in visible_workflows(db, user):
        err("工作流不存在或无权访问", 404)
    provider = get_provider(db)
    out = executor.run_workflow(db, user, wf, body.input, provider=provider)
    run = WorkflowRun(workflow_id=wid, user_id=user.id, input_text=body.input,
                      steps_output=out["steps"], final=out["final"])
    db.add(run)
    db.commit()
    return {"workflow": wf.name, "run_id": run.id, **out}


@router.delete("/workflows/{wid}")
def delete_workflow(wid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wf = db.get(Workflow, wid)
    if not wf or (wf.owner_id != user.id and user.role != "platform_admin"):
        err("无权删除", 403)
    db.query(WorkflowRun).filter(WorkflowRun.workflow_id == wid).delete()
    db.delete(wf)
    db.commit()
    return {"ok": True}
