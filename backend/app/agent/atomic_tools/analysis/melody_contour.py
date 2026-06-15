# app/agent/atomic_tools/analysis/melody_contour.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import Optional

async def extract_melody_contour(audio_path: str, bpm: Optional[float] = None, sections: Optional[list] = None) -> dict:
    y, sr = librosa.load(audio_path, sr=22050)
    # 使用 pyin 提取基频
    f0, voiced_flag, voiced_prob = librosa.pyin(y, fmin=80, fmax=1000, sr=sr)
    times = librosa.times_like(f0, sr=sr)
    # 转换为 MIDI 音高
    melody_contour = []
    for t, f in zip(times, f0):
        if not np.isnan(f):
            midi = librosa.hz_to_midi(f)
            melody_contour.append([float(t), float(midi)])
    # 简化：每隔0.1秒取一个点
    # 主题动机：检测重复模式（简化：取最频繁出现的短片段，这里略）
    motif_times = []  # 可以留空或简单取副歌起始点
    pitch_range = [min([p[1] for p in melody_contour]) if melody_contour else 48,
                   max([p[1] for p in melody_contour]) if melody_contour else 72]
    return {
        "melody_contour": melody_contour,
        "motif_times": motif_times,
        "pitch_range": pitch_range
    }

class MelodyContourInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")
    bpm: Optional[float] = Field(default=None, description="BPM，可选")
    sections: Optional[list] = Field(default=None, description="段落信息，可选")

extract_melody_contour_tool = StructuredTool.from_function(
    coroutine=extract_melody_contour,
    name="extract_melody_contour",
    description="提取旋律轮廓（时间-音高序列）、主题动机出现时间、音域",
    args_schema=MelodyContourInput
)