# app/agent/atomic_tools/analysis/spectral_centroid.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def get_spectral_centroid(audio_path: str) -> float:
    """返回音频的频谱中心（Hz），用于判断音色亮度。"""
    y, sr = librosa.load(audio_path, sr=22050)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    return float(np.mean(centroid))

class GetSpectralCentroidInput(BaseModel):
    audio_path: str = Field(description="音频文件的绝对路径")

get_spectral_centroid_tool = StructuredTool.from_function(
    coroutine=get_spectral_centroid,
    name="get_spectral_centroid",
    description="获取音频的频谱中心频率（Hz），数值越低声音越暗（低频多），越高声音越亮（高频多）。",
    args_schema=GetSpectralCentroidInput,
)