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
        self._llm_runs: dict[str, float] = {}

    def _start_llm_run(self, run_id: Any, message_count: int) -> None:
        run_key = str(run_id or "")
        if run_key in self._llm_runs:
            return
        if run_key:
            self._llm_runs[run_key] = time.perf_counter()
        persist_trace_event(
            self.task_id,
            create_trace_event(
                task_id=self.task_id,
                kind="llm",
                name="langchain_chat_model",
                status="running",
                details={"step": self.step_name, "message_count": message_count},
            ),
        )

    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        self._start_llm_run(kwargs.get("run_id"), len(prompts))

    async def on_chat_model_start(
        self, serialized: Dict[str, Any], messages: List[List], **kwargs: Any
    ) -> None:
        self._start_llm_run(
            kwargs.get("run_id"), sum(len(batch) for batch in messages)
        )

    async def on_chat_model_end(self, run_obj: Any, **kwargs: Any) -> None:
        """兼容可能提供 chat-model 专用结束回调的实现。"""
        return None

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,  # 必须与基类签名一致
        **kwargs: Any,
    ) -> None:
        """记录模型完成事件，但不保存响应正文或隐藏推理内容。"""
        started_at = self._llm_runs.pop(str(run_id), time.perf_counter())
        generations = getattr(response, "generations", []) or []
        record_thought(
            self.task_id,
            self.step_name,
            "LLM 响应已生成（正文已从诊断日志省略）",
            type="llm",
            status="success",
        )
        persist_trace_event(
            self.task_id,
            create_trace_event(
                task_id=self.task_id,
                kind="llm",
                name="langchain_chat_model",
                status="succeeded",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                details={
                    "step": self.step_name,
                    "generation_count": sum(len(batch) for batch in generations),
                },
            ),
        )

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        """记录脱敏后的 LangChain 模型故障。"""
        from app.services.llm_service import build_llm_error

        started_at = self._llm_runs.pop(str(run_id), time.perf_counter())
        normalized_error = build_llm_error(error)
        normalized_error["component"] = "langchain_chat_model"
        persist_trace_event(
            self.task_id,
            create_trace_event(
                task_id=self.task_id,
                kind="llm",
                name="langchain_chat_model",
                status="failed",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                details={"step": self.step_name},
                error=normalized_error,
            ),
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
