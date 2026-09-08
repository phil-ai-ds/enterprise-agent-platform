"""M10: LLM 用量采集（LangChain callback + contextvar 绑定 user/agent/provider/run）。"""
import contextvars
from datetime import datetime, timezone

from langchain_core.callbacks import BaseCallbackHandler
from sqlalchemy.orm import Session

from .models import LlmUsage, LLMProvider

_ctx_user_id = contextvars.ContextVar("eap_user_id", default=None)
_ctx_team_id = contextvars.ContextVar("eap_team_id", default=None)
_ctx_agent_id = contextvars.ContextVar("eap_agent_id", default=None)
_ctx_agent_name = contextvars.ContextVar("eap_agent_name", default="")
_ctx_provider_id = contextvars.ContextVar("eap_provider_id", default=None)
_ctx_provider_name = contextvars.ContextVar("eap_provider_name", default="")
_ctx_kind = contextvars.ContextVar("eap_kind", default="chat")
_ctx_run_ref = contextvars.ContextVar("eap_run_ref", default="")

EST_MT = {
    # 参考价（USD / 百万 token），仅估算；可在 Provider 管理里配置真实价
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "qwen-plus": (0.40, 1.20),
}


def estimate_cost_usd(provider_name: str, model: str, input_tokens: int, output_tokens: int, custom_prices=None) -> float:
    pi, po = None, None
    if custom_prices:
        pi, po = custom_prices
    if pi is None or po is None:
        pi, po = EST_MT.get(model, (0.5, 1.5))
    return (input_tokens * pi + output_tokens * po) / 1_000_000.0


class UsageCaptureCallback(BaseCallbackHandler):
    """每个 LLM 调用结束时写一行用量（含上下文绑定的归属信息）。"""

    def __init__(self, db: Session):
        self.db = db

    def on_llm_end(self, response, **kwargs) -> None:
        usage = None
        model_name = ""
        try:
            for gen in response.generations:
                msg = gen[0].message
                um = getattr(msg, "usage_metadata", None)
                if um:
                    usage = um
                    break
        except Exception:
            usage = None
        try:
            lo = getattr(response, "llm_output") or {}
            model_name = str(lo.get("model_name") or lo.get("model") or "")
        except Exception:
            model_name = ""
        if usage is None:
            return  # 无用量信息（如 mock 流）时跳过
        provider_id = _ctx_provider_id.get()
        provider = self.db.get(LLMProvider, provider_id) if provider_id else None
        prices = (provider.price_in_per_mtok, provider.price_out_per_mtok) if provider else None
        cost = estimate_cost_usd(_ctx_provider_name.get() or (provider.name if provider else ""), model_name,
                                 int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0), prices)
        self.db.add(LlmUsage(
            ts=datetime.now(timezone.utc),
            user_id=_ctx_user_id.get(),
            team_id=_ctx_team_id.get(),
            agent_id=_ctx_agent_id.get(),
            agent_name=_ctx_agent_name.get(),
            provider_id=_ctx_provider_id.get(),
            provider_name=_ctx_provider_name.get() or (provider.name if provider else ""),
            model=model_name,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            cost_usd=cost,
            kind=_ctx_kind.get(),
            run_ref=_ctx_run_ref.get(),
        ))
        self.db.commit()


class UsageContext:
    """上下文管理器：绑定一条 run 的归属信息。"""

    def __init__(self, user_id, team_id, agent_id, agent_name, provider_id, provider_name, kind="chat", run_ref=""):
        self.tokens = {
            "user": (lambda v: _ctx_user_id.set(v), _ctx_user_id),
            "team": (lambda v: _ctx_team_id.set(v), _ctx_team_id),
            "agent": (lambda v: _ctx_agent_id.set(v), _ctx_agent_id),
            "agent_name": (lambda v: _ctx_agent_name.set(v), _ctx_agent_name),
            "provider": (lambda v: _ctx_provider_id.set(v), _ctx_provider_id),
            "provider_name": (lambda v: _ctx_provider_name.set(v), _ctx_provider_name),
            "kind": (lambda v: _ctx_kind.set(v), _ctx_kind),
            "run": (lambda v: _ctx_run_ref.set(v), _ctx_run_ref),
        }
        self.values = [user_id, team_id, agent_id, agent_name, provider_id, provider_name, kind, run_ref]
        self.reset_tokens = []

    def __enter__(self):
        keys = ["user", "team", "agent", "agent_name", "provider", "provider_name", "kind", "run"]
        for k, v in zip(keys, self.values):
            setter, var = self.tokens[k]
            self.reset_tokens.append((var, var.get()))
            setter(v)
        return self

    def __exit__(self, *a):
        for var, old in reversed(self.reset_tokens):
            var.set(old)
