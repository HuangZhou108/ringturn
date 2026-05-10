# app/agent/atomic_tools/analysis/instrument_detection.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def detect_instruments(audio_path: str) -> list[str]:
    """
    基于频谱中心粗略推测可能存在的乐器类别。
    """
    y, sr = librosa.load(audio_path, sr=22050)
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    mean_centroid = float(np.mean(spectral_centroid))
    
    instruments = []
    if mean_centroid < 500:
        instruments.extend(["bass", "drums"])
    if mean_centroid > 1000:
        instruments.append("guitar")
    if mean_centroid > 2000:
        instruments.append("vocals")
    if not instruments:
        instruments = ["piano", "drums"]
    return list(set(instruments))

class DetectInstrumentsInput(BaseModel):
    audio_path: str = Field(description="音频文件的绝对路径")

detect_instruments_tool = StructuredTool.from_function(
    coroutine=detect_instruments,
    name="detect_instruments",
    description="检测音频中可能存在的乐器类型（如钢琴、鼓、吉他、人声等），返回乐器名称列表。",
    args_schema=DetectInstrumentsInput,
)