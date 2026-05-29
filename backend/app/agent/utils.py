# backend/app/agent/utils.py
import numpy as np
from typing import Any, Dict
import re
import json

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