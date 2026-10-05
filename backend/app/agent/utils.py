# backend/app/agent/utils.py
import numpy as np
from typing import Any, Dict, Callable
import re
import json
from .thinking_utils import record_thought
from .observability import finish_trace_event, new_trace_event, record_trace_event, summarize
import inspect
import asyncio

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
    # 截断参数避免记录过长
    args_str = str(args)[:200]
    kwargs_str = str(kwargs)[:200]
    record_thought(
        task_id,
        step_name,
        f"调用工具: {tool_name} (参数: {args_str}, {kwargs_str})",
        type="tool_call",
        status="pending"
    )
    trace_event = new_trace_event(
        kind="tool",
        name=tool_name,
        parent_name=step_name,
        metadata={
            "args_summary": summarize(args),
            "kwargs_summary": summarize(kwargs),
        },
    )
    record_trace_event(task_id, trace_event)
    try:
        # result = await tool_func(*args, **kwargs)
        if inspect.iscoroutinefunction(tool_func):
            result = await tool_func(*args, **kwargs)
        else:
            result = await asyncio.to_thread(tool_func, *args, **kwargs)
        record_thought(
            task_id,
            step_name,
            f"工具返回: {str(result)[:300]}",
            type="tool_result",
            status="success"
        )
        record_trace_event(
            task_id,
            finish_trace_event(
                trace_event,
                status="success",
                metadata={"output_summary": summarize(result)},
            ),
        )
        return result
    except Exception as e:
        record_thought(
            task_id,
            step_name,
            f"工具执行失败: {str(e)}",
            type="tool_result",
            status="failed"
        )
        record_trace_event(
            task_id,
            finish_trace_event(trace_event, status="failed", error=e),
        )
        raise
