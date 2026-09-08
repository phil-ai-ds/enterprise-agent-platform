"""AI 构建助手：
1) 对话式建 Agent：一段话 → LLM 生成蓝图（name/system_prompt/要创建或复用的 skills/agent.md）→ 预览 → 一键落地。
2) Agent 反思：用户反馈(rating+意见) → LLM 分析 → 自动迭代：写 memory / 为技能建草稿版本 / 建议更新 system_prompt。
"""
import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import skills as skill_svc
from . import workspaces as wsvc
from .db import get_db
from .deps import get_current_user
from .models import (
    Agent, AgentSkill, ReflectionEntry, Skill, SkillVersion, User, Workspace,
)
from .providers import build_chat_model, get_provider
from .usage import UsageCaptureCallback, UsageContext

router = APIRouter()


def err(msg: str, code: int = 400):
    raise HTTPException(code, msg)


# ---------------- LLM JSON 辅助 ----------------

def _llm_json(db: Session, user: User, system: str, task: str, agent_name: str = "ai-builder",
              kind: str = "build", provider=None):
    """调用默认 provider 并要求纯 JSON 输出；返回 (dict, run_ref)。"""
    provider = provider or get_provider(db)
    model = build_chat_model(provider, None, temperature=0.1)
    cb = UsageCaptureCallback(db)
    run_ref = f"{kind}-{uuid.uuid4().hex[:10]}"
    ctx = UsageContext(user.id, user.team_id, None, agent_name, provider.id, provider.name,
                       kind=kind, run_ref=run_ref)
    with ctx:
        resp = model.invoke([SystemMessage(content=system), HumanMessage(content=task)],
                            config={"callbacks": [cb]})
    text = str(resp.content)
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise RuntimeError("LLM 未返回 JSON：" + text[:300])
    try:
        return json.loads(m.group(0)), run_ref
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM JSON 解析失败：{e}；原文：{text[:300]}")


def _visible_skill_catalog(db: Session, user: User) -> str:
    rows = []
    for s in skill_svc.visible_skills(db, user):
        pub = skill_svc.latest_published_version(db, s.id)
        rows.append(f"- id={s.id} | {s.name} | {s.description} | 最新已发布 v{pub.version if pub else '-'}")
    return "\n".join(rows) or "（平台暂无技能）"


# ---------------- 1) 对话式建 Agent ----------------

class GeneratePlanIn(BaseModel):
    prompt: str
    scope: str = "user"
    workspace_id: int | None = None


@router.post("/agents/generate-plan")
def generate_agent_plan(body: GeneratePlanIn, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """把一段需求描述变成 Agent 蓝图（LLM 生成，不落库，供预览确认）。"""
    if not body.prompt.strip():
        err("请描述你想要的 Agent")
    if body.scope not in ("user", "team", "org"):
        err("scope 非法")
    catalog = _visible_skill_catalog(db, user)
    ws = None
    if body.workspace_id:
        ws = db.get(Workspace, body.workspace_id)
        if not ws or not wsvc.can_read_ws(user, ws):
            err("工作区不存在或无权使用")
    system = ("你是企业 Agent 平台的首席 Agent 架构师。用户用自然语言描述想要的 Agent，"
              "你负责把它设计成可落地的蓝图。必须只输出 JSON，不要输出任何其他文字。\n"
              "JSON Schema：\n"
              "{\n"
              '  "name": "Agent 名（10字内，不要含空格）",\n'
              '  "description": "一句话说明职责",\n'
              '  "system_prompt": "完整的系统提示词（含角色、职责、工作方式、输出风格、该用哪些工具：读写工作区/联网搜索/执行代码/记忆）",\n'
              '  "agent_md": "一份简洁的 agent.md（使命/边界/工作流/技能清单），用 Markdown 纯文本（\\n 换行）",\n'
              '  "skills": [{"action":"existing"|"new", "skill_id":0, "name":"技能名", '
              '"content":"技能正文(SKILL.md 风格：触发条件+步骤+要点)", "reason":"为何需要"}],\n'
              '  "notes": "给用户的一句话说明（中文）"\n'
              "}\n"
              "决策规则：\n"
              "- 已有技能能覆盖需求时 action=existing 并填匹配的 skill_id；否则 action=new 并写清楚 content。\n"
              "- 不要重复创建与已有技能同功能的技能。\n"
              "- 技能 content 用中文写，包含：触发条件、执行步骤、输出要求、注意事项。")
    task = (f"用户需求：{body.prompt}\n"
            f"Agent 范围：{body.scope}\n"
            f"工作区：{wsvc.workspace_label(ws) if ws else '（按范围自动）'}\n\n"
            f"平台现有技能目录：\n{catalog}\n\n请生成蓝图 JSON。")
    try:
        plan, run_ref = _llm_json(db, user, system, task, agent_name="plan-agent", kind="plan")
    except RuntimeError as e:
        err(f"生成失败：{e}", 502)
    # 补全 existing skills 的名称与当前可见性
    for sk in plan.get("skills", []):
        if sk.get("action") == "existing":
            s = db.get(Skill, sk.get("skill_id"))
            if s:
                sk["name"] = s.name
    return {"plan": plan, "run_ref": run_ref}


class ApplyPlanIn(BaseModel):
    prompt: str
    plan: dict
    scope: str = "user"
    workspace_id: int | None = None


@router.post("/agents/generate-plan/apply")
def apply_agent_plan(body: ApplyPlanIn, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """把蓝图落地：创建缺失技能(draft)、绑定已存在技能、创建 Agent。"""
    plan = body.plan or {}
    name = (plan.get("name") or "").strip()
    if not name:
        err("蓝图缺少 Agent 名称")
    if body.scope not in ("user", "team", "org"):
        err("scope 非法")
    if body.scope == "team" and not user.team_id:
        err("你不在团队中，无法创建 team Agent")
    if db.query(Agent).filter(Agent.name == name).first():
        err(f"Agent 名 '{name}' 已存在，请修改蓝图中的 name 后重试")
    provider = get_provider(db)

    # 1) 确定工作区
    ws = None
    if body.workspace_id:
        ws = db.get(Workspace, body.workspace_id)
        if not ws or not wsvc.can_read_ws(user, ws):
            err("工作区不存在或无权使用")
    if ws is None:
        ws = wsvc.agent_default_workspace(db, user, type("A", (), {
            "scope": body.scope, "team_id": user.team_id if body.scope == "team" else None,
            "workspace_id": None})())

    # 2) 技能：existing → 绑定；new → 创建(scope=user 的私有草稿)并绑定
    created_skills, bound_skills = [], []
    bindings = []
    for sk in plan.get("skills", []):
        action = sk.get("action")
        sid = sk.get("skill_id")
        if action == "existing" and sid:
            s = db.get(Skill, sid)
            if s and s in skill_svc.visible_skills(db, user):
                ver = skill_svc.latest_published_version(db, s.id)
                bindings.append({"skill_id": s.id,
                                 "version_id": ver.id if ver else None})
                bound_skills.append(s.name)
                continue
        # 否则创建新技能
        sk_name = (sk.get("name") or "").strip()
        if not sk_name:
            continue
        sk_name = skill_svc.unique_skill_name(db, sk_name)
        s = Skill(name=sk_name,
                  description=(sk.get("reason") or sk.get("content") or "")[:200],
                  scope="user" if not user.team_id else "team",
                  owner_id=user.id, team_id=user.team_id if body.scope in ("team",) else user.team_id)
        db.add(s)
        db.flush()
        content = sk.get("content") or f"# {sk_name}\n（蓝图生成）"
        sv = SkillVersion(skill_id=s.id, version=1, content=content,
                          change_note="由 Agent 蓝图生成", status="draft", created_by=user.id)
        db.add(sv)
        db.flush()
        bindings.append({"skill_id": s.id, "version_id": sv.id})
        created_skills.append(sk_name)

    # 3) 创建 Agent
    agent_md = (plan.get("agent_md") or "").strip()
    sp = (plan.get("system_prompt") or "").strip()
    if agent_md:
        sp = sp + "\n\n# agent.md\n" + agent_md if sp else "# agent.md\n" + agent_md
    a = Agent(name=name, description=(plan.get("description") or "")[:600],
              system_prompt=sp or "你是企业 Agent 平台上的专业助手。",
              scope=body.scope, provider_id=provider.id,
              model=provider.default_model,
              owner_id=user.id,
              team_id=user.team_id if body.scope == "team" else None,
              workspace_id=ws.id if ws else None)
    db.add(a)
    db.flush()
    from .api_builder import AgentBinding as _B, bind_skills as _bind
    _bind(db, a, user, [_B(**b) for b in bindings])
    db.commit()
    return {"agent_id": a.id, "name": a.name,
            "created_skills": created_skills, "bound_skills": bound_skills,
            "workspace": {"id": ws.id, "name": ws.name} if ws else None}


# ---------------- 2) Agent 反思 ----------------

class ReflectIn(BaseModel):
    rating: int = 3
    feedback: str = ""


@router.post("/agents/{aid}/reflect")
def reflect_agent(aid: int, body: ReflectIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """用户对 Agent 一次表现给出反馈；LLM 反思并自动迭代：写记忆、为绑定技能建草稿版本、提示词建议。"""
    from .api_routes import visible_agents
    a = db.get(Agent, aid)
    if not a or a not in visible_agents(db, user):
        err("Agent 不存在或无权访问", 404)
    if not (body.feedback or "").strip():
        err("请填写反馈意见（哪里不对/希望怎么改）")
    rating = max(1, min(5, body.rating))

    # 收集上下文：system_prompt + 绑定技能摘要 + 该用户相关记忆
    skill_summary = []
    binds = db.query(AgentSkill).filter(AgentSkill.agent_id == a.id).all()
    for b in binds:
        s = db.get(Skill, b.skill_id)
        if not s:
            continue
        ver = skill_svc.resolve_version(db, s.id, b.version_id)
        if ver:
            skill_summary.append(f"技能[{s.id}] {s.name} v{ver.version}：{(ver.content or '')[:500]}")
    from . import memory as mem
    mems = mem.list_memory(db, user.id, a.id)[:10]

    system = ("你是 Agent 反思引擎。用户对 Agent 的一次表现给出评分与意见，你需要冷静复盘："
              "问题出在 system_prompt、绑定技能、还是缺失信息？然后给出可执行的改进。"
              "只输出 JSON，不要其他文字。JSON Schema：\n"
              "{\n"
              '  "analysis": "反思结论（中文，200字内：根因+改进方向）",\n'
              '  "memory_updates": [{"key":"偏好/事实名","value":"内容"}],\n'
              '  "skill_drafts": [{"skill_id":0, "name":"若新建技能则填新名；若更新已绑定技能则填其名", '
              '"content":"完整的新技能正文或该技能 v_next 的完整新内容（含全部步骤）", '
              '"change_note":"变更说明"}],\n'
              '  "system_prompt_suggestion": "新的/补充的 system_prompt 文本，若无则空字符串"\n'
              "}\n"
              "决策规则：\n"
              "- memory_updates：把用户流露出的稳定偏好/事实沉淀为记忆条目（key 简短，value 一句话）。\n"
              "- skill_drafts：若 Agent 缺少某类可复用方法论→新建技能草稿；若现有技能内容有缺陷→提供该技能的完整 v_next 内容（skill_id 填原技能 id）。\n"
              "- 最多 2 个 skill_drafts，避免过度工程。")
    task = (f"Agent：{a.name}\nSystem Prompt 摘要：{(a.system_prompt or '')[:1200]}\n\n"
            f"绑定技能：\n" + ("\n".join(f"- {x}" for x in skill_summary) or "（无）") +
            f"\n\n用户近期记忆：\n" + ("\n".join(f"- {m.key}: {m.value[:150]}" for m in mems) or "（无）") +
            f"\n\n用户评分：{rating}/5\n用户反馈：{body.feedback}")
    try:
        result, run_ref = _llm_json(db, user, system, task, agent_name=f"reflect:{a.name}", kind="reflect")
    except RuntimeError as e:
        err(f"反思失败：{e}", 502)

    # ---- 应用：memory + skill drafts ----
    applied_memory, applied_skills = [], []
    for m in (result.get("memory_updates") or [])[:4]:
        if m.get("key") and m.get("value"):
            mem.save_memory(db, user.id, a.id, "fact", m["key"].strip(), m["value"].strip())
            applied_memory.append(m["key"].strip())

    for sd in (result.get("skill_drafts") or [])[:2]:
        content = (sd.get("content") or "").strip()
        if not content:
            continue
        name = (sd.get("name") or "").strip()
        target = db.get(Skill, sd.get("skill_id")) if sd.get("skill_id") else None
        if target and skill_svc.can_edit(user, target):
            vers = skill_svc.skill_versions(db, target.id)
            nxt = max((v.version for v in vers), default=0) + 1
            db.add(SkillVersion(skill_id=target.id, version=nxt, content=content,
                                change_note=(sd.get("change_note") or "反思迭代")[:200],
                                status="draft", created_by=user.id))
            applied_skills.append({"skill_id": target.id, "name": target.name, "version": nxt})
        else:
            sk_name = skill_svc.unique_skill_name(db, name or f"{a.name}-反思技能")
            s = Skill(name=sk_name, description="由 Agent 反思自动生成", scope="private",
                      owner_id=user.id)
            db.add(s)
            db.flush()
            sv = SkillVersion(skill_id=s.id, version=1, content=content,
                              change_note="反思自动创建草稿", status="draft", created_by=user.id)
            db.add(sv)
            db.flush()
            # 新技能草稿自动绑定到该 Agent（显式 pin 草稿版本，否则 resolve 只认 published）
            db.add(AgentSkill(agent_id=a.id, skill_id=s.id, version_id=sv.id))
            applied_skills.append({"skill_id": s.id, "name": s.name, "version": 1})

    suggestion = (result.get("system_prompt_suggestion") or "").strip()
    entry = ReflectionEntry(agent_id=a.id, user_id=user.id, rating=rating,
                            feedback=body.feedback, analysis=result.get("analysis", ""),
                            actions=[{"type": "memory", "keys": applied_memory},
                                     {"type": "skill_draft", "items": applied_skills},
                                     {"type": "prompt_suggestion",
                                      "applied": False,
                                      "text": suggestion}],
                            applied=True)
    db.add(entry)
    db.commit()
    return {"reflection_id": entry.id, "analysis": entry.analysis,
            "applied_memory": applied_memory, "applied_skill_drafts": applied_skills,
            "system_prompt_suggestion": suggestion, "run_ref": run_ref}


@router.get("/agents/{aid}/reflections")
def agent_reflections(aid: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """查看 Agent 的反思迭代历史。"""
    from .api_routes import visible_agents
    a = db.get(Agent, aid)
    if not a or a not in visible_agents(db, user):
        err("Agent 不存在或无权访问", 404)
    rows = db.query(ReflectionEntry).filter(ReflectionEntry.agent_id == aid) \
        .order_by(ReflectionEntry.id.desc()).limit(50).all()
    return [{"id": r.id, "rating": r.rating, "feedback": r.feedback,
             "analysis": r.analysis, "actions": r.actions,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.post("/agents/{aid}/reflect/{rid}/apply-prompt")
def apply_prompt_suggestion(aid: int, rid: int, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """采纳某次反思的 system_prompt 建议（仅 Agent 作者/管理员）。"""
    a = db.get(Agent, aid)
    if not a or (a.owner_id != user.id and user.role != "platform_admin"):
        err("无权修改该 Agent", 403)
    r = db.get(ReflectionEntry, rid)
    if not r or r.agent_id != aid:
        err("反思记录不存在", 404)
    suggestion = ""
    for act in (r.actions or []):
        if act.get("type") == "prompt_suggestion":
            suggestion = act.get("text", "")
    if not suggestion.strip():
        err("该反思没有提示词建议")
    a.system_prompt = suggestion.strip()
    a.version += 1
    for act in (r.actions or []):
        if act.get("type") == "prompt_suggestion":
            act["applied"] = True
    db.commit()
    return {"id": a.id, "name": a.name, "version": a.version}
