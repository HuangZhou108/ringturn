# app/agent/atomic_tools/analysis/tempo_variation.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def detect_tempo_variation(audio_path: str, bpm: float) -> dict:
    y, sr = librosa.load(audio_path, sr=22050)
    # 滑动窗口计算局部 BPM
    hop_length = 512
    window_size = 8 * hop_length  # 约 8 秒窗口
    tempo_curve = []
    for start in range(0, len(y), window_size):
        end = start + window_size
        segment = y[start:end]
        if len(segment) < window_size:
            break
        tempo, _ = librosa.beat.beat_track(y=segment, sr=sr)
        tempo_curve.append([float(start/sr), float(tempo)])
    # 简单判断渐慢/渐快
    if len(tempo_curve) >= 2:
        first = tempo_curve[0][1]
        last = tempo_curve[-1][1]
        has_rallentando = last < first - 5
        has_accel = last > first + 5
    else:
        has_rallentando = False
        has_accel = False
    return {
        "tempo_curve": tempo_curve,
        "has_rallentando": has_rallentando,
        "has_accel": has_accel
    }

class TempoVariationInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")
    bpm: float = Field(description="平均 BPM")

detect_tempo_variation_tool = StructuredTool.from_function(
    coroutine=detect_tempo_variation,
    name="detect_tempo_variation",
    description="检测速度变化曲线、是否渐慢/渐快",
    args_schema=TempoVariationInput
)