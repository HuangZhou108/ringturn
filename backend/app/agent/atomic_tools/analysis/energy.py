# app/agent/atomic_tools/analysis/energy.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def get_rms_energy(audio_path: str) -> float:
    """
    返回音频的均方根能量（0~1 之间归一化近似值）。
    """
    y, sr = librosa.load(audio_path, sr=22050)
    rms = librosa.feature.rms(y=y)[0]
    return float(np.mean(rms))

class GetRmsEnergyInput(BaseModel):
    audio_path: str = Field(description="音频文件的绝对路径")

get_rms_energy_tool = StructuredTool.from_function(
    coroutine=get_rms_energy,
    name="get_rms_energy",
    description="获取音频的平均 RMS 能量，值越小表示声音越轻，越大表示越响。可用于判断是否需要增益补偿。",
    args_schema=GetRmsEnergyInput,
)