import os
from datetime import datetime, timezone

from .config import settings
from .db import Base, SessionLocal, engine
from .models import (
    Agent, AgentSkill, LLMProvider, Skill, SkillVersion, Team, User, Workspace,
)
from .security import hash_password


def seed():
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(os.path.join(settings.data_dir, "workspaces"), exist_ok=True)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        mk = Team(name="Marketing")
        fn = Team(name="Finance")
        db.add_all([mk, fn])
        db.flush()

        admin = User(username="admin", password_hash=hash_password("demo123"),
                     display_name="平台管理员", role="platform_admin")
        alice = User(username="alice", password_hash=hash_password("demo123"),
                     display_name="Alice(市场)", role="user", team_id=mk.id)
        bob = User(username="bob", password_hash=hash_password("demo123"),
                   display_name="Bob(财务)", role="user", team_id=fn.id)
        db.add_all([admin, alice, bob])
        db.flush()

        # ---- 工作区：每人个人空间、每团队团队空间、一个组织空间 ----
        def mk_ws(kind, name, owner=None, team=None):
            w = Workspace(kind=kind, name=name, owner_id=owner.id if owner else None,
                          team_id=team.id if team else None)
            db.add(w)
            db.flush()
            return w

        ws_admin = mk_ws("personal", "平台管理员 的个人空间", owner=admin)
        ws_alice = mk_ws("personal", "Alice(市场) 的个人空间", owner=alice)
        ws_bob = mk_ws("personal", "Bob(财务) 的个人空间", owner=bob)
        ws_mkt = mk_ws("team", "Marketing 团队空间", team=mk)
        ws_fn = mk_ws("team", "Finance 团队空间", team=fn)
        ws_org = mk_ws("org", "组织空间 · 全员共享")
        db.flush()

        # 工作区欢迎文档
        from . import workspaces as wsvc
        for w, lines in [
            (ws_alice, ["# Alice 的个人空间\n", "在此存放个人资料、笔记与产出文档。\n",
                        "提示：Agent 对话时可用 read_file / write_file / list_workspace 读写本空间。"]),
            (ws_mkt, ["# Marketing 团队空间\n", "市场团队的共享资料区：Campaign、竞品、洞察报告等。\n",
                      "团队 Agent（scope=team）自动在此空间工作。"]),
            (ws_fn, ["# Finance 团队空间\n", "财务团队的共享资料区：预算、口径、报表模板。"]),
            (ws_org, ["# 组织空间\n", "全公司共享的知识库与公共资产。"]),
        ]:
            root = wsvc.ws_root(settings.data_dir, w)
            with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as f:
                f.write("".join(lines))

        ds = LLMProvider(
            name="DeepSeek", kind="openai_compatible",
            base_url=settings.default_deepseek_base,
            api_key=settings.default_deepseek_key,
            models=["deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner"],
            default_model=settings.default_deepseek_model,
            price_in_per_mtok=0.14, price_out_per_mtok=0.28,
        )
        mock = LLMProvider(
            name="Mock-Offline", kind="mock", base_url="", api_key="",
            models=["mock-model"], default_model="mock-model",
            price_in_per_mtok=0.0, price_out_per_mtok=0.0,
        )
        db.add_all([ds, mock])
        db.flush()

        def add_skill(name, desc, scope, owner, team_id, versions, api=False):
            s = Skill(name=name, description=desc, scope=scope, owner_id=owner.id,
                      team_id=team_id, api_enabled=api)
            db.add(s)
            db.flush()
            for ver, content, note, status in versions:
                db.add(SkillVersion(skill_id=s.id, version=ver, content=content,
                                    change_note=note, status=status, created_by=owner.id,
                                    published_at=datetime.now(timezone.utc) if status == "published" else None))
            return s

        s1 = add_skill("结构化输出规范", "所有产出按 结论→证据→建议 组织；v2 增加引用与数字要求。",
                       "org", admin, None, [
                           (1, "# 结构化输出规范 v1\n1. 先结论（1-3 句）\n2. 再证据（要点）\n3. 后建议\n4. 中文为主，术语保留英文", "初版", "published"),
                           (2, "# 结构化输出规范 v2\n1. 先结论（1-3 句）\n2. 再证据（要点，尽量带数字）\n3. 后建议（可执行）\n4. 涉及数字：给出来源或标注估算\n5. 中文为主，术语保留英文", "v2：数字需注明出处或估算", "published"),
                       ])
        s2 = add_skill("数据口径检查", "写任何分析前先核对口径。", "org", admin, None, [
            (1, "# 数据口径检查 v1\n- 写百分比/金额前说明口径（同比/环比、含税/不含税）\n- 无法确认口径时明确标注假设", "初版", "published"),
        ])
        s3 = add_skill("会议纪要模板", "把讨论整理成结构化的会议纪要。", "org", alice, None, [
            (1, "# 会议纪要模板 v1\n输出结构：\n- 会议目标\n- 关键结论\n- 待办（负责人+时间）\n- 风险与升级项", "初版", "published"),
        ])
        s4 = add_skill("草稿技能示例（迭代中）", "演示草稿→测试→发布的迭代闭环。", "private", alice, None, [
            (1, "# 草稿技能示例 v1\n（编辑此内容来迭代——发布后才可被他人使用）", "草稿", "draft"),
        ])
        db.flush()

        def bind(agent, skill, version_id=None):
            db.add(AgentSkill(agent_id=agent.id, skill_id=skill.id, version_id=version_id))

        a_org = Agent(name="通用业务助理",
                      description="日常办公与业务问题解答：读写工作区、长期记忆、联网搜索、按需执行代码、调用技能。",
                      system_prompt="你是企业 Agent 平台中的通用业务助理。回答专业、简洁、可执行；需要落文档时写入当前工作区；把值得记住的事实写入记忆。",
                      scope="org", provider_id=ds.id, model=settings.default_deepseek_model,
                      owner_id=admin.id, workspace_id=ws_org.id)
        a_mkt = Agent(name="市场洞察专员", description="面向市场团队的洞察与简报助手，工作于 Marketing 团队空间。",
                      system_prompt="你是市场洞察专员。输出结构：结论先行→证据→建议。用中文回答。需要资料时联网搜索并注明来源。",
                      scope="team", provider_id=ds.id, model=settings.default_deepseek_model,
                      owner_id=alice.id, team_id=mk.id, workspace_id=ws_mkt.id)
        a_mock = Agent(name="离线演示助手(Mock)", description="本地 Mock 模型，离线演示平台流程与用量。",
                       system_prompt="你是离线演示助手。",
                       scope="org", provider_id=mock.id, model="mock-model", owner_id=admin.id,
                       workspace_id=ws_org.id)
        a_personal = Agent(name="Alice 私人助理", description="Alice 个人助理，在她的个人工作区工作。",
                           system_prompt="你是 Alice 的私人助理。优先读写 Alice 的个人工作区，用中文回答。",
                           scope="user", provider_id=ds.id, model=settings.default_deepseek_model,
                           owner_id=alice.id, workspace_id=ws_alice.id)
        db.add_all([a_org, a_mkt, a_mock, a_personal])
        db.flush()
        bind(a_org, s1)   # 自动最新 published = v2
        bind(a_org, s2)
        bind(a_mkt, s1)
        bind(a_mkt, s3)
        bind(a_personal, s3)
        db.commit()
        print("seed ok: admin/alice/bob (demo123); 工作区(个人/团队/组织)+Agent已绑定；版本化技能与示例就绪")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
