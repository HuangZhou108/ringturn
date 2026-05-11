# app/agent/atomic_tools/quality/zero_crossing_rate.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def get_zero_crossing_rate(audio_path: str) -> float:
    """
    返回过零率均值，用于检测噪声或削波。

    Returns:
        float: 过零率 (0~1)
    """
    y, sr = librosa.load(audio_path, sr=None)
    zcr = librosa.feature.zero_crossing_rate(y)[0]
    return float(np.mean(zcr))

class GetZeroCrossingRateInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

get_zero_crossing_rate_tool = StructuredTool.from_function(
    coroutine=get_zero_crossing_rate,
    name="get_zero_crossing_rate",
    description="获取音频的过零率，过高的过零率可能表示噪声或削波。",
    args_schema=GetZeroCrossingRateInput,
)