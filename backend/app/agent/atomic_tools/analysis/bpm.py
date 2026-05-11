# app/agent/atomic_tools/analysis/bpm.py
import librosa
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def get_bpm(audio_path: str) -> float:
    """
    提取音频的 BPM（每分钟节拍数）。

    Args:
        audio_path: 音频文件的绝对路径

    Returns:
        float: BPM 值，例如 120.0
    """
    y, sr = librosa.load(audio_path, sr=22050)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    return float(tempo)


class GetBpmInput(BaseModel):
    audio_path: str = Field(description="音频文件的绝对路径")

get_bpm_tool = StructuredTool.from_function(
    coroutine=get_bpm,
    name="get_bpm",
    description="提取音频的 BPM（每分钟节拍数）。对于 Lo-Fi 风格建议 60-90，流行 90-120，电子舞曲 120+。",
    args_schema=GetBpmInput,
)