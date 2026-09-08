"""M4: Agent Runtime —— 用 LangChain(LangGraph create_agent) 构建自由 agent 循环。

结构：Runtime = 系统提示(Agent定义+技能+记忆上下文) + 模型(按 Provider BYOM) + 工具(沙箱工作区/记忆)。
"""
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from .models import Agent, User
from .providers import build_chat_model
from .skills import load_agent_skill_instructions
from .tools import build_tools
from .usage import UsageCaptureCallback, UsageContext
from . import memory as mem

log = logging.getLogger(__name__)

try:
    from langchain.agents import create_agent  # langchain 1.x harness API
except Exception:
    create_agent = None


def build_agent_runnable(db: Session, user: User, agent: Agent, data_dir: str, extra_instructions: str = "",
                         run_ref: str = "", workspace_id: int | None = None, folder: str = ""):
    """返回 (runnable, tool_names, model)。runnable 为 LangChain/LangGraph agent。"""
    model = build_chat_model(agent.provider, agent.model)
    tools = build_tools(db, user, agent, data_dir, run_ref, workspace_id=workspace_id, folder=folder)
    skill_inst = load_agent_skill_instructions(db, agent)
    recalls = mem.recall(db, user.id, agent.id, "", limit=4)  # 最近记忆做暖启动上下文

    lines = []
    if agent.system_prompt:
        lines.append(agent.system_prompt)
    if skill_inst:
        lines.append("你当前已加载以下技能，遇到相关任务时请遵循其中的方法：")
        lines.append(skill_inst)
    if extra_instructions:
        lines.append(extra_instructions)
    if recalls:
        lines.append("与该用户的近期记忆（可能相关）：")
        lines.append("\n".join(f"- {r.key}: {r.value[:200]}" for r in recalls))
    system_prompt = "\n\n".join(lines) or "你是一个有用的 AI 助手。"

    if create_agent is None:
        raise RuntimeError("langchain.agents.create_agent 不可用")

    try:
        runnable = create_agent(model=model, tools=tools, system_prompt=system_prompt)
    except TypeError:
        runnable = create_agent(model=model, tools=tools)

    return runnable, [t.name for t in tools], model


def _invoke(runnable, message: str, cfg: dict) -> str:
    """调用 agent runnable。仅尝试 langgraph 合法的输入形态（dict 状态 / message list），
    绝不 fallback 到裸字符串 —— 字符串输入会触发 INVALID_GRAPH_NODE_RETURN_VALUE 并掩盖真实错误。
    dict 形态失败会自动重试一次（容忍 LLM Provider 瞬时网络抖动）。"""
    import time

    attempts = [
        ("dict+messages", lambda: runnable.invoke({"messages": [HumanMessage(content=message)]}, config=cfg)),
        ("dict+messages(retry)", lambda: (time.sleep(1.5), runnable.invoke({"messages": [HumanMessage(content=message)]}, config=cfg))[1]),
        ("list[messages]", lambda: runnable.invoke([HumanMessage(content=message)], config=cfg)),
    ]
    errors = []
    for name, fn in attempts:
        try:
            res = fn()
            if isinstance(res, dict):
                msgs = res.get("messages") or []
                # 取最后一条 AI 消息；若无则用 output 字段
                ai_msgs = [m for m in msgs if getattr(m, "type", "") == "ai"]
                reply = ai_msgs[-1].content if ai_msgs else (msgs[-1].content if msgs else str(res.get("output", res)))
            elif hasattr(res, "content"):
                reply = res.content
            else:
                reply = str(res)
            return str(reply)
        except Exception as e:  # noqa: BLE001
            errors.append(f"[{name}] {type(e).__name__}: {e}")
            continue
    raise RuntimeError("agent invoke 全部失败: " + " | ".join(errors))


def run_agent_chat(db: Session, user: User, agent: Agent, message: str, data_dir: str,
                   extra_instructions: str = "", refs: list[str] | None = None,
                   workspace_id: int | None = None, folder: str = "") -> dict:
    """执行一次带自由 loop 的对话（含工具调用）；记忆 user 消息并事后沉淀对话记忆。
    extra_instructions: 额外注入的上下文（如工作区参考文件内容）；refs: 本次参考的工作区路径；
    workspace_id/folder: 本次会话的工作区与工作目录（与 Agent 静态绑定解耦）。"""
    mem.save_memory(db, user.id, agent.id, "chat", message[:80], message[:1500])
    run_ref = f"run-{agent.id}-{user.id}"
    runnable, tool_names, model = build_agent_runnable(db, user, agent, data_dir,
                                                       extra_instructions=extra_instructions,
                                                       run_ref=run_ref,
                                                       workspace_id=workspace_id, folder=folder)
    cb = UsageCaptureCallback(db)
    ctx = UsageContext(
        user.id, user.team_id, agent.id, agent.name, agent.provider_id,
        agent.provider.name if agent.provider else "", kind="chat", run_ref=run_ref,
    )
    with ctx:
        cfg = {"callbacks": [cb], "tags": [f"user:{user.username}", f"agent:{agent.name}"],
               "recursion_limit": 25}  # 工具循环上限：防止搜索类任务无限多轮
        result = _invoke(runnable, message, cfg)
    reply = result
    mem.save_memory(db, user.id, agent.id, "chat", ("回复:" + message[:60]), str(reply)[:1500])
    return {"reply": reply, "tools_used": tool_names, "agent": agent.name, "run_ref": run_ref}
