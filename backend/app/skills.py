"""M7: 技能可见性、版本解析与指令加载。"""
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .models import Agent, AgentSkill, Skill, SkillVersion, User


def visible_skills(db: Session, user: User) -> list[Skill]:
    conds = [Skill.scope == "org"]
    if user.team_id:
        conds.append(Skill.team_id == user.team_id)
    conds.append(Skill.owner_id == user.id)
    return db.query(Skill).filter(or_(*conds)).order_by(Skill.id.desc()).all()


def can_edit(user: User, skill: Skill) -> bool:
    return user.role == "platform_admin" or skill.owner_id == user.id


def latest_published_version(db: Session, skill_id: int) -> SkillVersion | None:
    return (db.query(SkillVersion)
            .filter(SkillVersion.skill_id == skill_id, SkillVersion.status == "published")
            .order_by(SkillVersion.version.desc()).first())


def resolve_version(db: Session, skill_id: int, version_id: int | None = None,
                    fallback: str = "published") -> SkillVersion | None:
    if version_id:
        v = db.get(SkillVersion, version_id)
        if v and v.skill_id == skill_id:
            return v
    return latest_published_version(db, skill_id)


def skill_versions(db: Session, skill_id: int) -> list[SkillVersion]:
    return (db.query(SkillVersion).filter(SkillVersion.skill_id == skill_id)
            .order_by(SkillVersion.version.desc()).all())


def load_agent_skill_instructions(db: Session, agent: Agent) -> str:
    """按 AgentSkill 绑定（pin 指定版本，否则最新 published）把技能正文注入提示词。"""
    rows = (db.query(AgentSkill, Skill)
            .join(Skill, AgentSkill.skill_id == Skill.id)
            .filter(AgentSkill.agent_id == agent.id).all())
    parts = []
    for bind, skill in rows:
        ver = resolve_version(db, skill.id, bind.version_id)
        if ver is None or ver.status not in ("published", "draft"):
            continue
        head = (ver.content or "").strip()
        if len(head) > 4000:
            head = head[:4000] + "\n..."
        parts.append(f"### 技能：{skill.name} v{ver.version}（{ver.status}）\n{head}")
    return "\n\n".join(parts) if parts else ""


def unique_skill_name(db: Session, base: str) -> str:
    name, i = base, 2
    while db.query(Skill).filter(Skill.name == name).first():
        name = f"{base}-{i}"
        i += 1
    return name
