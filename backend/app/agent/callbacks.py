from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import ToolMessage
from langchain_core.outputs import LLMResult
from typing import Any, Dict, Optional, List
from uuid import UUID
from .thinking_utils import record_thought


class ThinkingCallbackHandler(AsyncCallbackHandler):
    """将子 Agent 的 LLM 输出和工具调用记录到数据库"""

    def __init__(self, task_id: str, step_name: str):
        self.task_id = task_id
        self.step_name = step_name

    # 新增调试日志
    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        print(f"[CALLBACK DEBUG] on_llm_start triggered for task={self.task_id}, step={self.step_name}")
    
    async def on_chat_model_start(
        self, serialized: Dict[str, Any], messages: List[List], **kwargs: Any
    ) -> None:
        print(f"[CALLBACK DEBUG] on_chat_model_start triggered for task={self.task_id}, step={self.step_name}")

    # 处理 Chat 模型的完结事件
    async def on_chat_model_end(
        self,
        run_obj: Any,
        **kwargs: Any
    ) -> None:
        """ChatOpenAI 实际触发的是此事件，而不是我们之前使用的on_llm_end"""
        # response = run_obj
        # if hasattr(response, 'generations'):
        #     for gen_list in response.generations:
        #         for gen in gen_list:
        #             # ChatGeneration 的内容在 message.content 中
        #             text = getattr(gen, 'message', None)
        #             if text and hasattr(text, 'content'):
        #                 text = text.content
        #             elif hasattr(gen, 'text'):
        #                 text = gen.text
        #             if text:
        #                 record_thought(
        #                     self.task_id,
        #                     self.step_name,
        #                     f"[LLM思考] {text[:500]}"
        #                 )
        print(f"[CALLBACK DEBUG] on_chat_model_end triggered for task={self.task_id}, step={self.step_name}")
        await self.on_llm_end(response, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,  # 必须与基类签名一致
        **kwargs: Any,
    ) -> None:
        """LLM / Chat 模型结束事件。根据官方文档，异步 chat 模型不会触发
        on_chat_model_end，统一由此方法处理。"""
        print(f"[CALLBACK DEBUG] on_llm_end triggered for step={self.step_name}")
        if hasattr(response, 'generations'):
            for gen_list in response.generations:
                for gen in gen_list:
                    # ChatGeneration 的内容在 message.content 中
                    text = getattr(gen, 'message', None)
                    if text and hasattr(text, 'content'):
                        text = text.content
                    elif hasattr(gen, 'text'):
                        text = gen.text
                    if text:
                        record_thought(
                            self.task_id,
                            self.step_name,
                            f"[LLM思考] {text[:500]}"
                        )

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs: Any) -> None:
        record_thought(
            self.task_id,
            self.step_name,
            f"调用工具: {serialized.get('name')} 参数: {input_str[:200]}"
        )

    # async def on_tool_end(self, output: Any, **kwargs: Any) -> None:
    #     # 处理不同类型的输出
    #     if isinstance(output, ToolMessage):
    #         content = output.content
    #     elif isinstance(output, str):
    #         content = output
    #     else:
    #         content = str(output)
    #     record_thought(
    #         self.task_id,
    #         self.step_name,
    #         f"工具返回: {content[:200]}"
    #     )

    async def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        content = output.content if isinstance(output, ToolMessage) else (
            output if isinstance(output, str) else str(output)
        )
        record_thought(
            self.task_id,
            self.step_name,
            f"工具返回: {content[:200]}"
        )