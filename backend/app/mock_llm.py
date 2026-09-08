"""Mock LLM（provider.kind == 'mock'）：无网络即可演示多 Provider、技能注入与用量统计。"""
from typing import Any, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class MockChatModel(BaseChatModel):
    """根据技能/系统提示返回占位回复，并携带 usage_metadata 以驱动用量观测。"""
    model: str = "mock-model"
    temperature: float = 0.0

    @property
    def _llm_type(self) -> str:
        return "mock"

    def bind_tools(self, tools, **kwargs):
        """Mock 不产生真实 tool_call：绑定后仍只返回文本，供离线演示 agent 循环。"""
        return self

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                  run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs: Any) -> ChatResult:
        system = next((m.content for m in messages if m.type == "system"), "")
        last = messages[-1].content if messages else ""
        skills = [ln.strip("- ").strip() for ln in (system or "").splitlines() if "[技能]" in ln]
        skill_note = f"（已加载技能: {'、'.join(skills)}）" if skills else ""
        text = (f"[mock:{self.model}] 已收到：{str(last)[:80]}{skill_note}\n"
                f"这是占位回复——在管理端配置真实 LLM Provider 后即可获得真实生成。")
        out_tokens = len(text) // 3 + 8
        usage = {"input_tokens": 96, "output_tokens": out_tokens, "total_tokens": 96 + out_tokens}
        msg = AIMessage(content=text, usage_metadata=usage)
        return ChatResult(generations=[ChatGeneration(message=msg)])
