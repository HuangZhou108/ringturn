# app/agent/atomic_tools/rendering/convert_to_mp3.py
import subprocess
import shutil
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def convert_wav_to_mp3(wav_path: str, mp3_path: str, bitrate: str = "192k") -> str:
    """
    使用 ffmpeg 将 WAV 转换为 MP3。

    Args:
        wav_path: 输入 WAV 路径
        mp3_path: 输出 MP3 路径
        bitrate: 比特率

    Returns:
        str: 输出 MP3 路径
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        # 降级：尝试使用 pydub (需要安装)
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_wav(wav_path)
            audio.export(mp3_path, format="mp3", bitrate=bitrate)
            return mp3_path
        except ImportError:
            raise RuntimeError("ffmpeg not found and pydub not installed")
    subprocess.run(
        [ffmpeg, "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-b:a", bitrate, mp3_path],
        check=True,
        capture_output=True
    )
    return mp3_path

class ConvertWavToMp3Input(BaseModel):
    wav_path: str = Field(description="输入的 WAV 文件路径")
    mp3_path: str = Field(description="输出的 MP3 文件路径")
    bitrate: str = Field(default="192k", description="MP3 比特率，如 128k, 192k, 320k")

convert_wav_to_mp3_tool = StructuredTool.from_function(
    coroutine=convert_wav_to_mp3,
    name="convert_wav_to_mp3",
    description="将 WAV 音频文件转换为 MP3 格式。",
    args_schema=ConvertWavToMp3Input,
)