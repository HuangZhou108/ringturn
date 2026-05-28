# backend/app/agent/utils.py
import numpy as np
from typing import Any

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