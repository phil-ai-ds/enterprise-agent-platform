from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now():
    return datetime.now(timezone.utc)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="user")  # user | platform_admin
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    team: Mapped[Team | None] = relationship()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LLMProvider(Base):
    __tablename__ = "llm_providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    kind: Mapped[str] = mapped_column(String(30), default="openai_compatible")
    base_url: Mapped[str] = mapped_column(String(300))
    api_key: Mapped[str] = mapped_column(String(300), default="")
    models: Mapped[list] = mapped_column(JSON, default=list)
    default_model: Mapped[str] = mapped_column(String(120))
    price_in_per_mtok: Mapped[float] = mapped_column(Float, default=0.0)
    price_out_per_mtok: Mapped[float] = mapped_column(Float, default=0.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Skill(Base):
    """M7: 技能逻辑实体（名称/归属/可见范围）；内容与版本在 skill_versions。"""
    __tablename__ = "skills"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(String(600), default="")
    scope: Mapped[str] = mapped_column(String(20), default="private")  # private | team | org
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    api_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    owner: Mapped[User | None] = relationship()


class SkillVersion(Base):
    """M7: 技能版本（不可变发布：published 后内容不可改，可另起 draft 迭代）。"""
    __tablename__ = "skill_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, default="")
    change_note: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published | deprecated
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skill: Mapped[Skill | None] = relationship()


class Workspace(Base):
    """个人 / 团队 / 组织工作区：Agent 文档读写与文件上传下载的统一场所。"""
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="personal")  # personal | team | org
    name: Mapped[str] = mapped_column(String(160))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    owner: Mapped[User | None] = relationship()
    team: Mapped[Team | None] = relationship()


class WorkspaceFile(Base):
    """工作区文件索引（本体在磁盘 data_dir/workspaces/{w{id}}/…；DB 记录便于权限/审计/下载）。"""
    __tablename__ = "workspace_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    rel_path: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(20), default="file")  # file | dir
    mime: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    workspace: Mapped[Workspace | None] = relationship()


class Agent(Base):
    """M7-lite→完整：Agent 注册（可用户自建），skills 通过 AgentSkill 挂版本。"""
    __tablename__ = "agents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(String(600), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    scope: Mapped[str] = mapped_column(String(20), default="user")  # user | team | org
    provider_id: Mapped[int] = mapped_column(ForeignKey("llm_providers.id"))
    model: Mapped[str] = mapped_column(String(120))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True)  # None=按scope自动
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    provider: Mapped[LLMProvider | None] = relationship()
    owner: Mapped[User | None] = relationship()
    workspace: Mapped[Workspace | None] = relationship()


class ReflectionEntry(Base):
    """Agent 反思：用户反馈 → LLM 分析 → 对 skills/memory 的迭代动作（应用后可追溯）。"""
    __tablename__ = "reflections"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer, default=3)  # 1..5
    feedback: Mapped[str] = mapped_column(Text, default="")
    analysis: Mapped[str] = mapped_column(Text, default="")
    actions: Mapped[list] = mapped_column(JSON, default=list)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    agent: Mapped[Agent | None] = relationship()


class AgentSkill(Base):
    __tablename__ = "agent_skills"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"))
    version_id: Mapped[int | None] = mapped_column(ForeignKey("skill_versions.id"), nullable=True)  # None=最新published
    permission: Mapped[str] = mapped_column(String(10), default="r")


class AgentWsPref(Base):
    """工作区偏好记忆（Agent 与工作区解耦后）：某用户在某个 Agent 上最近一次工作的
    工作区 + 文件夹。Agent 默认选中该位置，用户可手动切换（切换即更新记忆）。"""
    __tablename__ = "agent_ws_prefs"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    folder: Mapped[str] = mapped_column(String(500), default="")  # 相对工作区根的文件夹，空=根
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Workflow(Base):
    """W-lite：用户工作流 = 有序串联的多个技能版本；运行时逐步调用 LLM。"""
    __tablename__ = "workflows"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(String(600), default="")
    steps: Mapped[list] = mapped_column(JSON, default=list)  # [{skill_id, version_id|null, note}]
    scope: Mapped[str] = mapped_column(String(20), default="private")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    input_text: Mapped[str] = mapped_column(Text, default="")
    steps_output: Mapped[list] = mapped_column(JSON, default=list)
    final: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), default="fact")
    key: Mapped[str] = mapped_column(String(200), default="")
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    hits: Mapped[int] = mapped_column(Integer, default=0)


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    agent_name: Mapped[str] = mapped_column(String(200), default="")
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("llm_providers.id"), nullable=True)
    provider_name: Mapped[str] = mapped_column(String(60), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    kind: Mapped[str] = mapped_column(String(30), default="chat")  # chat | flow | skill_test | skill_api | workflow
    run_ref: Mapped[str] = mapped_column(String(200), default="")


class FlowRun(Base):
    __tablename__ = "flow_runs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    flow_name: Mapped[str] = mapped_column(String(80), default="draft-review")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    task: Mapped[str] = mapped_column(Text)
    draft: Mapped[str] = mapped_column(Text, default="")
    final: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="waiting_approval")
    feedback: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
