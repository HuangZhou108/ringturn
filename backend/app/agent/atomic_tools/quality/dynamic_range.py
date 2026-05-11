# app/agent/atomic_tools/quality/dynamic_range.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def check_dynamic_range(audio_path: str) -> dict:
    """
    计算动态范围（RMS 的最大值减最小值）。

    Returns:
        dict: {"dynamic_range_db": float, "is_narrow": bool}
    """
    y, sr = librosa.load(audio_path, sr=None)
    rms = librosa.feature.rms(y=y)[0]
    rms_db = 20 * np.log10(rms + 1e-6)
    dr = float(np.max(rms_db) - np.min(rms_db))
    return {
        "dynamic_range_db": dr,
        "is_narrow": dr < 10.0,   # 小于 10dB 视为动态不足
    }

class CheckDynamicRangeInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

check_dynamic_range_tool = StructuredTool.from_function(
    coroutine=check_dynamic_range,
    name="check_dynamic_range",
    description="计算音频的动态范围（dB），并判断是否过于狭窄（<10dB）。",
    args_schema=CheckDynamicRangeInput,
)