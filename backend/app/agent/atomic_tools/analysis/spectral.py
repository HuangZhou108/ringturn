# app/agent/atomic_tools/analysis/spectral.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def analyze_spectral(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, sr=22050)
    # 频谱质心
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    centroid_mean = float(np.mean(centroid))
    # 低频/高频能量比
    spec = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)
    low_mask = freqs < 250
    high_mask = freqs > 4000
    low_energy = np.sum(spec[low_mask]) if np.any(low_mask) else 0
    high_energy = np.sum(spec[high_mask]) if np.any(high_mask) else 0
    total = low_energy + high_energy + 1e-6
    low_ratio = low_energy / total
    high_ratio = high_energy / total
    # 噪声底噪（静音段估算）
    rms = librosa.feature.rms(y=y)[0]
    silent_frames = rms < 0.01
    if np.any(silent_frames):
        spec_silent = spec[:, silent_frames]
        noise_floor = np.mean(np.abs(spec_silent)) if spec_silent.size else -60
    else:
        noise_floor = -60
    noise_floor_db = 20 * np.log10(noise_floor + 1e-6)
    return {
        "spectral_centroid_mean": centroid_mean,
        "low_freq_energy_ratio": float(low_ratio),
        "high_freq_energy_ratio": float(high_ratio),
        "noise_floor": float(noise_floor_db)
    }

class SpectralInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

analyze_spectral_tool = StructuredTool.from_function(
    coroutine=analyze_spectral,
    name="analyze_spectral",
    description="频谱分析：质心、低频/高频能量比、噪声底噪",
    args_schema=SpectralInput
)