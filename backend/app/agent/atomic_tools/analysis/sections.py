# app/agent/atomic_tools/analysis/sections.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def detect_sections(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, sr=22050)
    duration = librosa.get_duration(y=y, sr=sr)
    # 使用梅尔频谱的突变检测简单划分段落
    mel_spec = librosa.feature.melspectrogram(y=y, sr=sr)
    # 计算每一帧的能量
    energy = np.sum(mel_spec, axis=0)
    # 找出能量变化的拐点作为段落边界
    diff = np.diff(energy)
    threshold = np.std(diff) * 1.5
    boundaries = np.where(np.abs(diff) > threshold)[0]
    # 转换为时间
    frames_to_time = librosa.frames_to_time(boundaries, sr=sr)
    times = sorted(frames_to_time)
    # 添加0和duration
    cut_times = [0.0] + [t for t in times if 0 < t < duration] + [duration]
    # 给段落类型（简单模式：intro, verse, chorus, outro 循环）
    types = ["intro", "verse", "chorus", "outro"]
    sections = []
    for i in range(len(cut_times)-1):
        typ = types[i % len(types)] if i < len(types) else "verse"
        # 粗略能量等级（0~1）
        energy_level = float(np.mean(energy[int(cut_times[i]*sr/512):int(cut_times[i+1]*sr/512)])) if len(energy) > 0 else 0.5
        sections.append({
            "start": cut_times[i],
            "end": cut_times[i+1],
            "type": typ,
            "energy_level": energy_level
        })
    # 能量曲线简化为每0.5秒一个点
    hop_length = int(0.5 * sr / 512)  # 每0.5秒
    energy_curve = [{"time": float(t), "energy": float(e)} for t, e in zip(librosa.times_like(energy, sr=sr), energy) if t < duration]
    return {"sections": sections, "energy_curve": energy_curve}

class SectionsInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

detect_sections_tool = StructuredTool.from_function(
    coroutine=detect_sections,
    name="detect_sections",
    description="检测段落边界、段落类型、能量曲线",
    args_schema=SectionsInput
)