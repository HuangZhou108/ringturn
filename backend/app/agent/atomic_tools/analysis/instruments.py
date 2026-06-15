# app/agent/atomic_tools/analysis/instruments.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def detect_instruments(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, sr=22050)
    # 使用频谱质心、过零率等启发式
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    mean_centroid = np.mean(spectral_centroid)
    zcr = librosa.feature.zero_crossing_rate(y=y)
    mean_zcr = np.mean(zcr)
    
    instruments = []
    lead = "piano"  # 默认
    accompaniment = "block chords"
    
    if mean_centroid < 500:
        instruments.append("bass")
        instruments.append("drums")
        lead = "bass"
    if 500 <= mean_centroid < 2000:
        instruments.append("guitar")
        instruments.append("piano")
        lead = "piano"
    if mean_centroid >= 2000:
        instruments.append("vocals")
        instruments.append("violin")
        lead = "vocals"
    if mean_zcr > 0.2:
        instruments.append("drums")
    
    instruments = list(set(instruments))
    # 简单判断伴奏类型
    if len(instruments) > 2:
        accompaniment = "arpeggiated chords"
    return {
        "instruments": instruments,
        "lead_instrument": lead,
        "accompaniment_style": accompaniment
    }

class InstrumentsInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

detect_instruments_tool = StructuredTool.from_function(
    coroutine=detect_instruments,
    name="detect_instruments",
    description="检测音频中的乐器列表、主奏乐器、伴奏类型",
    args_schema=InstrumentsInput
)