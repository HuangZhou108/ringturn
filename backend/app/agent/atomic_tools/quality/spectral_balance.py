# app/agent/atomic_tools/quality/spectral_balance.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def check_spectral_balance(audio_path: str) -> dict:
    """
    检查频谱平衡（低频是否过重、高频是否刺耳）。

    Returns:
        dict: {"spectral_centroid_mean": float, "low_freq_heavy": bool, "high_freq_harsh": bool}
    """
    y, sr = librosa.load(audio_path, sr=22050)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    mean_centroid = float(np.mean(centroid))
    return {
        "spectral_centroid_mean": mean_centroid,
        "low_freq_heavy": mean_centroid < 200,
        "high_freq_harsh": mean_centroid > 4000,
    }

class CheckSpectralBalanceInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

check_spectral_balance_tool = StructuredTool.from_function(
    coroutine=check_spectral_balance,
    name="check_spectral_balance",
    description="检查音频的频谱平衡，判断低频是否过多或高频是否刺耳。",
    args_schema=CheckSpectralBalanceInput,
)