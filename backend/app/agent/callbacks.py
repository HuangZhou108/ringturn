from langchain_core.callbacks import BaseCallbackHandler
from typing import Any, Dict, List, Optional
from .agent_executor import record_thought

class ThinkingCallbackHandler(BaseCallbackHandler):
    """将子 Agent 的 LLM 输出和工具调用记录到数据库"""
    def __init__(self, task_id: str, step_name: str):
        self.task_id = task_id
        self.step_name = step_name

    async def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        # 记录 LLM 最终输出（可选，通常内容较大，可只记录工具调用）
        pass

    async def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        record_thought(
            self.task_id,
            self.step_name,
            f"调用工具: {serialized.get('name')} 参数: {input_str[:200]}"
        )

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        record_thought(
            self.task_id,
            self.step_name,
            f"工具返回: {output[:200]}"
        )