"""执行辅助：单技能运行（测试/API）与多技能工作流运行（均计入用量可观测）。"""
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from . import skills as skill_svc
from .models import SkillVersion, User, Workflow
from .providers import build_chat_model, get_provider
from .usage import UsageCaptureCallback, UsageContext


def _llm_one(db: Session, user: User, system: str, task: str,
             kind: str, agent_name: str, provider=None):
    provider = provider or get_provider(db)
    model = build_chat_model(provider, None)
    cb = UsageCaptureCallback(db)
    run_ref = f"{kind}-{uuid.uuid4().hex[:10]}"
    ctx = UsageContext(user.id, user.team_id, None, agent_name, provider.id, provider.name,
                       kind=kind, run_ref=run_ref)
    with ctx:
        resp = model.invoke([SystemMessage(content=system), HumanMessage(content=task)],
                            config={"callbacks": [cb]})
    return str(resp.content), run_ref


def run_skill(db: Session, user: User, version: SkillVersion, skill_name: str, input_text: str,
              kind: str = "skill_test", provider=None) -> dict:
    system = (f"你是技能执行器，严格按下列技能方法处理任务。技能：{skill_name} v{version.version}\n\n"
              f"{version.content}")
    out, run_ref = _llm_one(db, user, system, input_text, kind=kind, agent_name=f"skill:{skill_name}", provider=provider)
    return {"skill": skill_name, "version": version.version, "result": out, "run_ref": run_ref}


def run_workflow(db: Session, user: User, wf: Workflow, input_text: str, provider=None) -> dict:
    """按 steps 顺序串联多个技能：上一步输出作为下一步输入的一部分。"""
    steps_out = []
    current = input_text
    for i, step in enumerate(wf.steps or []):
        skill_id = step.get("skill_id")
        ver = skill_svc.resolve_version(db, skill_id, step.get("version_id"))
        if ver is None or ver.status != "published":
            raise LookupError(f"工作流第 {i + 1} 步技能不可用（需已发布版本）")
        from .models import Skill
        skill = db.get(Skill, skill_id)
        note = step.get("note") or ""
        system = (f"你是工作流 '{wf.name}' 的第 {i + 1} 步执行器。技能：{skill.name} v{ver.version}\n"
                  f"{ver.content}\n"
                  f"步骤说明：{note}\n"
                  f"只输出本步骤结果。")
        task = f"任务输入：\n{current}"
        if i > 0:
            task += f"\n\n（这是上一步骤的输出，可在此基础上加工，但只处理与本步骤相关的部分）"
        out, run_ref = _llm_one(db, user, system, task, kind="workflow",
                                agent_name=f"wf:{wf.name}", provider=provider)
        steps_out.append({"step": i + 1, "skill": skill.name, "version": ver.version,
                          "output": out, "run_ref": run_ref})
        current = out
    return {"steps": steps_out, "final": current}
