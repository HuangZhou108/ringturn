from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import ToolMessage
from langchain_core.outputs import LLMResult
from typing import Any, Dict, Optional, List
from uuid import UUID
from .thinking_utils import record_thought
from .observability import finish_trace_event, new_trace_event, record_trace_event, summarize


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
        pass

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
                            f"[LLM思考] {text[:500]}",
                            type="llm",
                            status="success"
                        )

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs: Any) -> None:
        record_thought(
            self.task_id,
            self.step_name,
            f"调用工具: {serialized.get('name')} 参数: {input_str[:200]}",
            type="tool_call",
            status="pending"
        )

    async def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        content = output.content if isinstance(output, ToolMessage) else (
            output if isinstance(output, str) else str(output)
        )
        record_thought(
            self.task_id,
            self.step_name,
            f"工具返回: {content[:200]}",
            type="tool_result",
            status="success"
        )

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        """工具执行错误回调"""
        record_thought(
            self.task_id,
            self.step_name,
            f"工具执行失败: {str(error)[:200]}",
            type="tool_result",
            status="failed"
        )


class ToolTraceCallbackHandler(AsyncCallbackHandler):
    """Record function-calling tool lifecycle without storing LLM messages."""

    def __init__(self, task_id: str, step_name: str):
        self.task_id = task_id
        self.step_name = step_name
        self._tool_runs: dict[str, dict[str, Any]] = {}

    async def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        inputs: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name") or "unknown_tool"
        event = new_trace_event(
            kind="tool",
            name=name,
            parent_name=self.step_name,
            metadata={
                "input_summary": summarize(inputs if inputs is not None else input_str),
                "langchain_run_id": str(run_id),
            },
        )
        self._tool_runs[str(run_id)] = event
        record_trace_event(self.task_id, event)

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        event = self._tool_runs.pop(str(run_id), None)
        if not event:
            return
        completed = finish_trace_event(
            event,
            status="success",
            metadata={"output_summary": summarize(output)},
        )
        record_trace_event(self.task_id, completed)

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        event = self._tool_runs.pop(str(run_id), None)
        if not event:
            return
        record_trace_event(
            self.task_id,
            finish_trace_event(event, status="failed", error=error),
        )
