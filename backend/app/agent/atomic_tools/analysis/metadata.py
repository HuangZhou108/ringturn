# app/agent/atomic_tools/analysis/metadata.py
import librosa
import soundfile as sf
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from pathlib import Path

async def get_audio_metadata(audio_path: str) -> dict:
    """
    获取音频时长、采样率、声道数、格式。
    """
    info = sf.info(audio_path)
    duration = info.duration
    sample_rate = info.samplerate
    channels = info.channels
    # 格式从扩展名获取
    ext = Path(audio_path).suffix.lower().lstrip('.')
    return {
        "duration": float(duration),
        "sample_rate": int(sample_rate),
        "channels": int(channels),
        "format": ext
    }

class MetadataInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

get_metadata_tool = StructuredTool.from_function(
    coroutine=get_audio_metadata,
    name="get_audio_metadata",
    description="获取音频的时长(s)、采样率(Hz)、声道数、格式",
    args_schema=MetadataInput
)