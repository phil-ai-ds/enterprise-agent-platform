from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import memory as mem
from .db import get_db
from .deps import get_current_user, require_admin
from .models import Agent, AgentSkill, FlowRun, LLMProvider, LlmUsage, Skill, Team, User
from .providers import mask_key

router = APIRouter()


# ---------- 认证 / 当前用户 ----------
class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    user: dict


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    from .security import create_token, verify_password
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return LoginOut(token=create_token(user.id, user.username, user.role), user=user_dto(user))


def user_dto(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name,
            "role": u.role, "team": u.team.name if u.team else None}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_dto(user)


# ---------- Agent 目录（O1: 可见性 = org + 同团队 + 自己的草稿） ----------
def visible_agents(db: Session, user: User) -> list[Agent]:
    q = db.query(Agent).filter(Agent.enabled == True)  # noqa: E712
    from sqlalchemy import or_
    conds = [Agent.scope == "org", Agent.owner_id == user.id]
    if user.team_id:
        conds.append(Agent.team_id == user.team_id)
    return q.filter(or_(*conds)).all()


@router.get("/agents")
def list_agents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from . import workspaces as wsvc
    out = []
    for a in visible_agents(db, user):
        from . import skills as skill_svc_mod
        binds = db.query(AgentSkill).filter(AgentSkill.agent_id == a.id).all()
        names = []
        for b in binds:
            s = db.get(Skill, b.skill_id)
            if s:
                names.append(s.name)
        ws = None
        pref_folder = ""
        try:
            ws0, pref_folder = wsvc.get_agent_ws_pref(db, user, a)
            if ws0:
                ws = {"id": ws0.id, "name": ws0.name, "kind": ws0.kind,
                      "label": wsvc.workspace_label(ws0)}
        except Exception:  # noqa: BLE001
            ws = None
        out.append({
            "id": a.id, "name": a.name, "description": a.description, "scope": a.scope,
            "version": a.version, "model": a.model,
            "provider": a.provider.name if a.provider else "",
            "skills": names,
            "workspace": ws,
            "pref": {"workspace_id": ws["id"] if ws else None, "folder": pref_folder or ""},
        })
    return out


# ---------- 技能/记忆/用量（构建类 API 见 api_builder.py：创建/版本/发布/API/分享/复制/工作流） ----------
# ---------- 记忆（M8） ----------
@router.get("/memory")
def list_my_memory(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": m.id, "kind": m.kind, "key": m.key, "value": m.value[:500],
             "updated_at": m.updated_at.isoformat() if m.updated_at else None}
            for m in mem.list_memory(db, user.id)]


@router.delete("/memory/{entry_id}")
def del_memory(entry_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not mem.delete_memory(db, user.id, entry_id):
        raise HTTPException(404, "not found")
    return {"ok": True}


# ---------- 用量（用户视角） ----------
def usage_summary(db: Session, user: User | None, group_by: str, days: int = 30):
    since = datetime.combine(date.today(), datetime.min.time()).replace(day=max(1, date.today().day - days + 1))
    g = {
        "agent": (func.coalesce(LlmUsage.agent_name, "—"),),
        "provider": (func.coalesce(LlmUsage.provider_name, "—"),),
        "model": (LlmUsage.model,),
        "team": (func.coalesce(LlmUsage.team_id, 0),),
        "day": (func.date(LlmUsage.ts),),
        "user": (func.coalesce(LlmUsage.user_id, 0),),
    }
    if group_by not in g:
        raise HTTPException(400, f"group_by 支持: {list(g)}")
    q = db.query(
        g[group_by][0].label("label"),
        func.sum(LlmUsage.input_tokens).label("input_tokens"),
        func.sum(LlmUsage.output_tokens).label("output_tokens"),
        func.sum(LlmUsage.cost_usd).label("cost_usd"),
        func.count(LlmUsage.id).label("calls"),
    ).filter(LlmUsage.ts >= since)
    if user:
        q = q.filter(LlmUsage.user_id == user.id)
    rows = q.group_by(g[group_by][0]).order_by(func.sum(LlmUsage.cost_usd).desc()).limit(30).all()
    team_names = {t.id: t.name for t in db.query(Team).all()}
    out = []
    for label, it, ot, cost, calls in rows:
        if group_by == "team" and user is None:
            label = team_names.get(int(label), f"team#{label}")
        if group_by == "user" and user is None:
            u = db.get(User, int(label)) if label else None
            label = u.username if u else f"user#{label}"
        out.append({"label": str(label), "input_tokens": int(it or 0), "output_tokens": int(ot or 0),
                    "cost_usd": round(float(cost or 0), 6), "calls": int(calls or 0)})
    return {"group_by": group_by, "rows": out}


@router.get("/usage/me")
def my_usage(group_by: str = "agent", days: int = 30,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return usage_summary(db, user, group_by, days)


@router.get("/usage/me/recent")
def my_recent(user: User = Depends(get_current_user), db: Session = Depends(get_db), limit: int = 20):
    rows = db.query(LlmUsage).filter(LlmUsage.user_id == user.id).order_by(LlmUsage.ts.desc()).limit(limit).all()
    return [{"ts": r.ts.isoformat() if r.ts else None, "agent": r.agent_name, "provider": r.provider_name,
             "model": r.model, "tokens": r.total_tokens, "cost_usd": round(r.cost_usd, 6), "kind": r.kind}
            for r in rows]


# ---------- 平台管理（admin） ----------
@router.get("/admin/users")
def admin_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [user_dto(u) for u in db.query(User).order_by(User.id).all()]


@router.get("/admin/providers")
def admin_providers(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [{"id": p.id, "name": p.name, "kind": p.kind, "base_url": p.base_url,
             "api_key_masked": mask_key(p.api_key), "models": p.models,
             "default_model": p.default_model, "enabled": p.enabled,
             "price_in_per_mtok": p.price_in_per_mtok, "price_out_per_mtok": p.price_out_per_mtok}
            for p in db.query(LLMProvider).order_by(LLMProvider.id).all()]


class ProviderIn(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    models: list[str]
    default_model: str
    kind: str = "openai_compatible"
    price_in_per_mtok: float = 0.0
    price_out_per_mtok: float = 0.0
    enabled: bool = True


@router.post("/admin/providers")
def admin_add_provider(body: ProviderIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(LLMProvider).filter(LLMProvider.name == body.name).first():
        raise HTTPException(400, "Provider 已存在")
    p = LLMProvider(**body.model_dump())
    db.add(p)
    db.commit()
    return {"id": p.id, "name": p.name}


@router.patch("/admin/providers/{pid}/toggle")
def admin_toggle_provider(pid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.get(LLMProvider, pid)
    if not p:
        raise HTTPException(404, "not found")
    p.enabled = not p.enabled
    db.commit()
    return {"id": p.id, "enabled": p.enabled}


@router.get("/admin/agents")
def admin_agents(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [{"id": a.id, "name": a.name, "scope": a.scope, "version": a.version, "enabled": a.enabled,
             "provider": a.provider.name if a.provider else "", "model": a.model} for a in db.query(Agent).all()]


class AgentIn(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    scope: str = "org"
    provider_id: int
    model: str = ""
    team_id: int | None = None
    skill_ids: list[int] = []


@router.post("/admin/agents")
def admin_add_agent(body: AgentIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(Agent).filter(Agent.name == body.name).first():
        raise HTTPException(400, "Agent 已存在")
    prov = db.get(LLMProvider, body.provider_id)
    if not prov:
        raise HTTPException(400, "provider not found")
    a = Agent(name=body.name, description=body.description, system_prompt=body.system_prompt,
              scope=body.scope, provider_id=body.provider_id,
              model=body.model or prov.default_model, team_id=body.team_id)
    db.add(a)
    db.flush()
    for sid in body.skill_ids:
        db.add(AgentSkill(agent_id=a.id, skill_id=sid))
    db.commit()
    return {"id": a.id, "name": a.name}


@router.get("/admin/skills")
def admin_skills(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    from . import skills as skill_svc_mod
    rows = db.query(Skill).order_by(Skill.id).all()
    owners = {u.id: u.username for u in db.query(User).all()}
    out = []
    for s in rows:
        vers = skill_svc_mod.skill_versions(db, s.id)
        out.append({
            "id": s.id, "name": s.name, "description": s.description, "scope": s.scope,
            "owner": owners.get(s.owner_id, "?"), "api_enabled": s.api_enabled,
            "versions": [{"version": v.version, "status": v.status, "change_note": v.change_note} for v in vers],
            "published": sum(1 for v in vers if v.status == "published"),
        })
    return out


@router.post("/admin/skills/{sid}/deprecate")
def admin_deprecate_skill(sid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    from . import skills as skill_svc_mod
    s = db.get(Skill, sid)
    if not s:
        raise HTTPException(404, "not found")
    ver = skill_svc_mod.latest_published_version(db, sid)
    if ver:
        ver.status = "deprecated"
    s.api_enabled = False
    db.commit()
    return {"id": s.id, "deprecated": True}


@router.get("/admin/usage")
def admin_usage(group_by: str = "user", days: int = 30,
                _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return usage_summary(db, None, group_by, days)


@router.get("/admin/stats")
def admin_stats(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(func.count(User.id)).scalar()
    agents = db.query(func.count(Agent.id)).scalar()
    skills = db.query(func.count(Skill.id)).scalar()
    providers = db.query(func.count(LLMProvider.id)).scalar()
    calls = db.query(func.count(LlmUsage.id)).scalar()
    cost = db.query(func.coalesce(func.sum(LlmUsage.cost_usd), 0.0)).scalar()
    tokens = db.query(func.coalesce(func.sum(LlmUsage.total_tokens), 0)).scalar()
    flows = db.query(func.count(FlowRun.id)).scalar()
    return {"users": users, "agents": agents, "skills": skills, "providers": providers,
            "llm_calls": calls or 0, "total_tokens": tokens or 0, "cost_usd": round(float(cost or 0), 4),
            "flow_runs": flows or 0}
