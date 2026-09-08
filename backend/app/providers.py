"""M6-lite: 多 LLM Provider 接入（OpenAI 兼容协议）。预置 DeepSeek；管理员可增配任意
OpenAI-compatible 端点（OpenAI / Anthropic 网关 / Qwen / Ollama / vLLM…），实现 BYOM。"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import LLMProvider


def build_chat_model(provider: LLMProvider, model: str | None = None, temperature: float = 0.2):
    from langchain_openai import ChatOpenAI

    if provider.kind == "mock":
        from .mock_llm import MockChatModel
        return MockChatModel(model=model or provider.default_model)

    chosen = model or provider.default_model
    if not provider.api_key:
        raise HTTPException(400, f"Provider '{provider.name}' 未配置 API Key")
    return ChatOpenAI(
        model=chosen,
        api_key=provider.api_key,
        base_url=provider.base_url.rstrip("/"),
        temperature=temperature,
        max_retries=2,
        timeout=120,
    )


def get_provider(db: Session, provider_id: int | None = None, provider_name: str | None = None) -> LLMProvider:
    if provider_id:
        p = db.get(LLMProvider, provider_id)
    elif provider_name:
        p = db.query(LLMProvider).filter(LLMProvider.name == provider_name).first()
    else:
        p = db.query(LLMProvider).filter(LLMProvider.enabled == True).first()  # noqa: E712
    if not p or not p.enabled:
        raise HTTPException(404, "No enabled LLM provider")
    return p


def mask_key(key: str) -> str:
    if not key:
        return ""
    return key[:6] + "****" + key[-4:] if len(key) > 12 else "****"
