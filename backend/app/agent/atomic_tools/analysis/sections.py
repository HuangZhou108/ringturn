# app/agent/atomic_tools/analysis/sections.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def detect_sections(audio_path: str, max_sections: int = 4) -> list[dict]:
    """
    按能量变化粗略划分段落。

    Args:
        audio_path: 音频文件路径
        max_sections: 最大段落数

    Returns:
        list[dict]: 每个段落包含 start, end, type (intro/verse/chorus/outro)

    使用场景：
        - 确定铃声截取的最佳起点
        - 生成结构分析报告
    """
    y, sr = librosa.load(audio_path, sr=22050)
    duration = librosa.get_duration(y=y, sr=sr)
    
    # 按能量变化分界
    rms = librosa.feature.rms(y=y)[0]
    frame_times = librosa.times_like(rms, sr=sr)
    changes = np.diff(rms)
    peak_frames = np.argsort(np.abs(changes))[-max_sections:]
    cut_times = sorted([frame_times[f] for f in peak_frames if 0 < frame_times[f] < duration])
    cut_times = [0.0] + cut_times + [duration]
    
    section_types = ["intro", "verse", "chorus", "outro"]
    sections = []
    for i in range(min(len(cut_times)-1, len(section_types))):
        sections.append({
            "start": float(cut_times[i]),
            "end": float(cut_times[i+1]),
            "type": section_types[i % len(section_types)]
        })
    return sections

class DetectSectionsInput(BaseModel):
    audio_path: str = Field(description="音频文件的绝对路径")
    max_sections: int = Field(default=4, description="最多划分的段落数")

detect_sections_tool = StructuredTool.from_function(
    coroutine=detect_sections,
    name="detect_sections",
    description="将音频划分为多个段落（intro, verse, chorus, outro），返回每个段落的起止时间。",
    args_schema=DetectSectionsInput,
)