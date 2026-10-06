import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from .thinking_utils import record_thought
from .trace import (build_execution_error, create_trace_event,
                    persist_trace_event, redact_text, summarize_result)


class ThinkingCallbackHandler(AsyncCallbackHandler):
    """将子 Agent 的 LLM 输出和工具调用记录到数据库"""

    def __init__(self, task_id: str, step_name: str):
        self.task_id = task_id
        self.step_name = step_name
        self._tool_runs: dict[str, tuple[str, float]] = {}

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
        tool_name = serialized.get("name") or "unknown_tool"
        run_id = str(kwargs.get("run_id", ""))
        if run_id:
            self._tool_runs[run_id] = (tool_name, time.perf_counter())
        record_thought(
            self.task_id,
            self.step_name,
            f"调用工具: {tool_name}（参数内容已从日志省略）",
            type="tool_call",
            status="pending"
        )
        persist_trace_event(
            self.task_id,
            create_trace_event(
                task_id=self.task_id,
                kind="tool",
                name=tool_name,
                status="running",
                details={"step": self.step_name, "input_chars": len(input_str)},
            ),
        )

    async def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        record_thought(
            self.task_id,
            self.step_name,
            f"工具返回结构: {summarize_result(output)}",
            type="tool_result",
            status="success"
        )
        run_id = str(kwargs.get("run_id", ""))
        tool_name, started_at = self._tool_runs.pop(
            run_id,
            ("unknown_tool", time.perf_counter()),
        )
        persist_trace_event(
            self.task_id,
            create_trace_event(
                task_id=self.task_id,
                kind="tool",
                name=tool_name,
                status="succeeded",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                details={"step": self.step_name, "output": summarize_result(output)},
            ),
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
            f"工具执行失败: {redact_text(error, limit=200)}",
            type="tool_result",
            status="failed"
        )
        run_key = str(run_id)
        tool_name, started_at = self._tool_runs.pop(
            run_key,
            ("unknown_tool", time.perf_counter()),
        )
        normalized_error = build_execution_error(
            error,
            scope="tool",
            component=tool_name,
        )
        persist_trace_event(
            self.task_id,
            create_trace_event(
                task_id=self.task_id,
                kind="tool",
                name=tool_name,
                status="failed",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                details={"step": self.step_name},
                error=normalized_error,
            ),
        )
