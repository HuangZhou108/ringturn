# app/agent/atomic_tools/analysis/loudness.py
import librosa
import numpy as np
import pyloudnorm as pyln
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def analyze_loudness(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, sr=None)
    # RMS
    rms = librosa.feature.rms(y=y)[0]
    rms_mean = float(np.mean(rms))
    # 峰值电平 (dBFS)
    peak = np.max(np.abs(y))
    peak_db = 20 * np.log10(peak + 1e-6)
    # 动态范围
    dynamic_range = float(np.max(rms) - np.min(rms))
    # LUFS
    meter = pyln.Meter(sr)
    loudness = meter.integrated_loudness(y)
    return {
        "loudness_lufs": float(loudness),
        "rms_mean": rms_mean,
        "peak_level_db": float(peak_db),
        "dynamic_range_db": dynamic_range
    }

class LoudnessInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

analyze_loudness_tool = StructuredTool.from_function(
    coroutine=analyze_loudness,
    name="analyze_loudness",
    description="计算响度(LUFS)、RMS均值、峰值电平(dBFS)、动态范围(dB)",
    args_schema=LoudnessInput
)