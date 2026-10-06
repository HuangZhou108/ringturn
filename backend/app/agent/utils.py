# backend/app/agent/utils.py
import asyncio
import inspect
import json
import re
import time
from typing import Any, Callable, Dict

import numpy as np
from app.core.config import get_settings

from .resilience import policy_for_name, run_with_retry
from .thinking_utils import record_thought
from .trace import (build_execution_error, create_trace_event,
                    persist_trace_event, redact_text, summarize_result,
                    summarize_tool_input)


def convert_numpy_to_native(obj: Any) -> Any:
    """递归地将 numpy 类型转换为 Python 原生类型"""
    if isinstance(obj, dict):
        return {k: convert_numpy_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_to_native(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_numpy_to_native(item) for item in obj)
    elif isinstance(obj, (np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, (np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return convert_numpy_to_native(obj.tolist())
    else:
        return obj
    
def clean_state(func):
    """装饰器：在节点返回前自动清理 state 中的 numpy 类型"""
    async def wrapper(state: Dict[str, Any], *args, **kwargs):
        result = await func(state, *args, **kwargs)
        if result is not None:
            return convert_numpy_to_native(result)
        return result
    return wrapper

def extract_json_from_response(text: str) -> dict:
    """
    从 LLM 返回的文本中提取 JSON 对象。
    支持纯 JSON 字符串或 markdown 代码块 (```json ... ```)。
    """
    # 尝试匹配 ```json ... ``` 或 ``` ... ```
    pattern = r"```(?:json)?\s*\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # 没有代码块，尝试直接解析整段文本
        json_str = text
    # 去除首尾空白
    json_str = json_str.strip()
    # 尝试直接解析
    return json.loads(json_str)

async def log_tool_call(
    task_id: str,
    step_name: str,
    tool_func: Callable,
    *args,
    tool_name: str = None,
    **kwargs
):
    """记录工具调用的开始、结果/异常，并返回工具返回值。"""
    tool_name = tool_name or getattr(tool_func, "__name__", "unknown_tool")
    settings = get_settings()
    retry_policy = policy_for_name(
        tool_name,
        allowlist=settings.AGENT_RETRYABLE_TOOLS,
        max_attempts=settings.AGENT_TOOL_MAX_ATTEMPTS,
        timeout_seconds=settings.AGENT_TOOL_TIMEOUT_SECONDS,
        backoff_seconds=settings.AGENT_TOOL_RETRY_BACKOFF_SECONDS,
        max_backoff_seconds=settings.AGENT_TOOL_RETRY_MAX_BACKOFF_SECONDS,
    )
    trace_started = create_trace_event(
        task_id=task_id,
        kind="tool",
        name=tool_name,
        status="running",
        details={"step": step_name, "input": summarize_tool_input(args, kwargs)},
    )
    persist_trace_event(task_id, trace_started)
    started_at = time.perf_counter()
    input_summary = summarize_tool_input(args, kwargs)
    record_thought(
        task_id,
        step_name,
        f"调用工具: {tool_name} (参数值已省略: {input_summary})",
        type="tool_call",
        status="pending"
    )
    try:
        async def invoke(_attempt: int):
            if inspect.iscoroutinefunction(tool_func):
                return await tool_func(*args, **kwargs)
            return await asyncio.to_thread(tool_func, *args, **kwargs)

        def on_retry(attempt: int, error: BaseException, delay: float) -> None:
            normalized_error = build_execution_error(
                error,
                scope="tool",
                component=tool_name,
            )
            next_attempt = attempt + 1
            record_thought(
                task_id,
                step_name,
                (
                    f"工具发生瞬时故障，将进行第 {next_attempt}/"
                    f"{retry_policy.max_attempts} 次尝试"
                ),
                type="tool_result",
                status="retry",
            )
            persist_trace_event(
                task_id,
                create_trace_event(
                    task_id=task_id,
                    kind="resilience",
                    name=tool_name,
                    status="retrying",
                    details={
                        "attempt": attempt,
                        "next_attempt": next_attempt,
                        "max_attempts": retry_policy.max_attempts,
                        "delay_ms": round(delay * 1000, 3),
                    },
                    error=normalized_error,
                ),
            )

        result, attempts_used = await run_with_retry(
            invoke,
            policy=retry_policy,
            on_retry=on_retry,
        )
        record_thought(
            task_id,
            step_name,
            f"工具返回结构: {summarize_result(result)}",
            type="tool_result",
            status="success"
        )
        persist_trace_event(
            task_id,
            create_trace_event(
                task_id=task_id,
                kind="tool",
                name=tool_name,
                status="succeeded",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                details={
                    "step": step_name,
                    "output": summarize_result(result),
                    "attempts": attempts_used,
                    "retries": attempts_used - 1,
                },
            ),
        )
        return result
    except Exception as e:
        normalized_error = build_execution_error(
            e,
            scope="tool",
            component=tool_name,
        )
        record_thought(
            task_id,
            step_name,
            f"工具执行失败: {redact_text(e)}",
            type="tool_result",
            status="failed"
        )
        persist_trace_event(
            task_id,
            create_trace_event(
                task_id=task_id,
                kind="tool",
                name=tool_name,
                status="failed",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                details={"step": step_name},
                error=normalized_error,
            ),
        )
        raise
