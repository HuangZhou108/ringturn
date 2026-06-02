# app/agent/atomic_tools/analysis/special_effects.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def detect_special_effects(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, sr=22050)
    # 检测混响（简化：计算 RT60，需要复杂模型，这里用占位）
    has_reverb = False
    # 检测延迟（通过自相关峰值）
    autocorr = np.correlate(y, y, mode='full')
    autocorr = autocorr[len(autocorr)//2:]
    peaks = np.where(autocorr > 0.5 * np.max(autocorr))[0]
    # 如果存在明显的周期峰值，可能有延迟
    has_delay = len(peaks) > 2 and np.diff(peaks).std() < 1000
    # 失真检测（高次谐波比例）
    spec = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)
    harm = librosa.feature.spectral_flatness(y=y)
    has_distortion = np.mean(harm) < 0.1
    # 削波检测
    is_clipped = np.any(np.abs(y) > 0.99)
    return {
        "has_reverb": has_reverb,
        "has_delay": has_delay,
        "has_distortion": has_distortion,
        "is_clipped": is_clipped
    }

class SpecialEffectsInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

detect_special_effects_tool = StructuredTool.from_function(
    coroutine=detect_special_effects,
    name="detect_special_effects",
    description="检测混响、延迟、失真、削波",
    args_schema=SpecialEffectsInput
)