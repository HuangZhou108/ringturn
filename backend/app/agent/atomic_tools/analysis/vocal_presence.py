# app/agent/atomic_tools/analysis/vocal_presence.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def detect_vocal_presence(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, sr=22050)
    # 利用频谱质心和高频能量粗略判断
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    mean_centroid = np.mean(spectral_centroid)
    # 人声通常频谱中心在 2000-4000 Hz
    has_vocal = 2000 < mean_centroid < 4000
    vocal_type = "lead" if has_vocal else "none"
    # 可分离性评分：基于信号复杂度
    # 这里简单返回0.8如果有 vocal
    separability_score = 0.8 if has_vocal else 0.0
    return {
        "has_vocal": has_vocal,
        "vocal_type": vocal_type,
        "separability_score": separability_score
    }

class VocalInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

detect_vocal_tool = StructuredTool.from_function(
    coroutine=detect_vocal_presence,
    name="detect_vocal_presence",
    description="检测音频是否包含人声、人声类型、可分离性评分",
    args_schema=VocalInput
)