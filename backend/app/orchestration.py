"""M3-lite: 多 Agent + HITL 编排（LangGraph StateGraph）。
流程 draft-review：Agent A(起草) → 人工审批门(interrupt) → Agent B(评审/对抗) 或 驳回；
演示 LangGraph interrupt/resume、checkpoint 与按流程计量的用量。"""
import logging
import uuid
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from . import usage as usage_mod
from .config import settings
from .models import FlowRun, User
from .providers import build_chat_model, get_provider
from .usage import UsageCaptureCallback, UsageContext

log = logging.getLogger(__name__)

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except Exception:  # pragma: no cover
    SqliteSaver = None

try:
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt
except Exception:  # pragma: no cover
    StateGraph = interrupt = START = END = None

DRAFT_PROMPT = ("你是 Agent A（起草者）：根据任务撰写高质量初稿，输出结构清晰、可直接交付的内容。"
                "只输出正文内容本身。")
REVIEW_PROMPT = ("你是 Agent B（评审者/对抗式质检）：对 Agent A 的草稿做严格评审——检查事实、结构、遗漏与风险；"
                 "若有问题请输出改进后的最终版本并附 2-3 条评审要点；若无问题直接输出草稿并说明已通过。")


class FlowState(TypedDict, total=False):
    task: str
    draft: str
    approval: dict
    final: str
    status: str


def _llm_call(db: Session, system: str, task: str, draft: str = "", feedback: str = "", who: str = "A"):
    provider = get_provider(db)
    model = build_chat_model(provider, None)
    cb = UsageCaptureCallback(db)
    msgs = [SystemMessage(content=system)]
    if who == "B":
        msgs.append(HumanMessage(content=f"任务：{task}\n\n草稿：\n{draft}\n\n评审意见（若有）：{feedback}"))
    else:
        msgs.append(HumanMessage(content=task))
    resp = model.invoke(msgs, config={"callbacks": [cb]})
    return resp.content


def build_flow_app(db: Session):
    """每个请求重新编译小图（节点闭包绑定当前 db 用于用量落库），checkpointer 全局共享。"""
    saver = _saver()

    def node_draft(state: FlowState) -> dict:
        return {"draft": _llm_call(db, DRAFT_PROMPT, state["task"], who="A")}

    def node_gate(state: FlowState) -> dict:
        decision = interrupt({"ask": "请审批 Agent A 的草稿", "draft": state.get("draft", "")})
        return {"approval": decision}

    def node_review(state: FlowState) -> dict:
        final = _llm_call(db, REVIEW_PROMPT, state["task"], state.get("draft", ""),
                          (state.get("approval") or {}).get("feedback", ""), who="B")
        return {"final": final, "status": "done"}

    def node_rejected(state: FlowState) -> dict:
        fb = (state.get("approval") or {}).get("feedback", "未通过审批")
        return {"final": f"（审批未通过）已驳回。评审意见：{fb}\n\n草稿存档：\n{state.get('draft', '')[:2000]}", "status": "rejected"}

    def route(state: FlowState) -> str:
        return "review" if (state.get("approval") or {}).get("approved") else "rejected"

    g = StateGraph(FlowState)
    g.add_node("draft", node_draft)
    g.add_node("gate", node_gate)
    g.add_node("review", node_review)
    g.add_node("rejected", node_rejected)
    g.add_edge(START, "draft")
    g.add_edge("draft", "gate")
    g.add_conditional_edges("gate", route, {"review": "review", "rejected": "rejected"})
    g.add_edge("review", END)
    g.add_edge("rejected", END)
    return g.compile(checkpointer=saver), saver


_saver_cache = None


def _saver():
    global _saver_cache
    if _saver_cache is not None:
        return _saver_cache
    if SqliteSaver is not None:
        try:
            import os
            import sqlite3
            os.makedirs(settings.data_dir, exist_ok=True)
            path = f"{settings.data_dir}/flow_checkpoints.sqlite"
            # 新版本 from_conn_string 返回上下文管理器；直接持有连接以跨请求存活
            conn = sqlite3.connect(path, check_same_thread=False)
            _saver_cache = SqliteSaver(conn)
        except Exception as e:  # pragma: no cover
            log.warning("SqliteSaver 不可用，回退 MemorySaver: %s", e)
            from langgraph.checkpoint.memory import InMemorySaver
            _saver_cache = InMemorySaver()
    else:  # pragma: no cover
        from langgraph.checkpoint.memory import InMemorySaver
        _saver_cache = InMemorySaver()
    return _saver_cache


def start_flow(db: Session, user: User, task: str) -> FlowRun:
    app, saver = build_flow_app(db)
    run_id = "flow-" + uuid.uuid4().hex[:12]
    config = {"configurable": {"thread_id": run_id}}
    provider = get_provider(db)
    ctx = UsageContext(user.id, user.team_id, None, "flow:draft-review", provider.id, provider.name,
                       kind="flow", run_ref=run_id)
    with ctx:
        state = app.invoke({"task": task}, config)
    draft = state.get("draft", "")
    run = FlowRun(id=run_id, flow_name="draft-review", user_id=user.id, task=task, draft=draft,
                  status="waiting_approval")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def approve_flow(db: Session, user: User, run_id: str, approved: bool, feedback: str) -> FlowRun:
    run = db.get(FlowRun, run_id)
    if not run or run.user_id != user.id:
        raise LookupError("flow run not found")
    app, saver = build_flow_app(db)
    config = {"configurable": {"thread_id": run_id}}
    provider = get_provider(db)
    ctx = UsageContext(user.id, user.team_id, None, "flow:draft-review", provider.id, provider.name,
                       kind="flow", run_ref=run_id)
    decision = {"approved": approved, "feedback": feedback}
    with ctx:
        try:
            from langgraph.types import Command
            state = app.invoke(Command(resume=decision), config)
        except TypeError:  # 兼容旧版 API
            app.update_state(config, {"approval": decision}, as_node="gate")
            state = app.invoke(None, config)
    run.feedback = feedback
    run.final = state.get("final", "")
    run.status = state.get("status", "done" if approved else "rejected")
    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, user: User, run_id: str) -> FlowRun:
    run = db.get(FlowRun, run_id)
    if not run or run.user_id != user.id:
        raise LookupError("flow run not found")
    return run
