# app/agent/atomic_tools/analysis/key.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def get_key(audio_path: str) -> str:
    """
    估计音频的调性（只返回主调，不区分大小调）。

    Args:
        audio_path: 音频文件的绝对路径

    Returns:
        str: 调性名称，例如 "C Major", "G# Minor"

    使用场景：
        - 辅助和弦进行提取
        - 用于后续改编时保持和声一致性
    """
    y, sr = librosa.load(audio_path, sr=22050)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = np.mean(chroma, axis=1)
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    key_idx = int(np.argmax(chroma_mean))
    # 简单模式：默认为 Major，可以通过更复杂的算法判断大小调
    return f"{note_names[key_idx]} Major"

class GetKeyInput(BaseModel):
    audio_path: str = Field(description="音频文件的绝对路径")

get_key_tool = StructuredTool.from_function(
    coroutine=get_key,
    name="get_key",
    description="估计音频的主调（如 C Major），用于保持和声一致性。",
    args_schema=GetKeyInput,
)