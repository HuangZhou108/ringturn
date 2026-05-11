# app/agent/atomic_tools/quality/loudness_check.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def check_loudness(audio_path: str) -> dict:
    """
    评估音频响度，返回平均 RMS 及是否过轻/过载的提示。

    Returns:
        dict: {"rms_mean": float, "is_too_quiet": bool, "is_clipped": bool}
    """
    y, sr = librosa.load(audio_path, sr=None)
    rms = librosa.feature.rms(y=y)[0]
    mean_rms = float(np.mean(rms))
    return {
        "rms_mean": mean_rms,
        "is_too_quiet": mean_rms < 0.01,
        "is_clipped": mean_rms > 0.8,
    }

class CheckLoudnessInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

check_loudness_tool = StructuredTool.from_function(
    coroutine=check_loudness,
    name="check_loudness",
    description="检查音频的响度（RMS），判断是否过轻或过载。",
    args_schema=CheckLoudnessInput,
)