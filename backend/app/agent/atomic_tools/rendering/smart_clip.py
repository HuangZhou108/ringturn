# app/agent/atomic_tools/rendering/smart_clip.py
import librosa
import numpy as np
import soundfile as sf
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def smart_clip_audio(
    audio_path: str,
    target_duration: float,
    mode: str = "auto",
    output_path: str | None = None
) -> tuple[str, float]:
    """
    智能截取音频中最精华的片段（默认选择能量最高的区域）。

    Args:
        audio_path: 输入音频路径
        target_duration: 目标时长（秒）
        mode: "auto" (高潮区域), "from_start", "from_middle"
        output_path: 输出路径（默认覆盖原文件）

    Returns:
        tuple: (输出路径, 实际截取后时长)
    """
    if output_path is None:
        output_path = audio_path
    y, sr = librosa.load(audio_path, sr=None, mono=False)
    if y.ndim == 1:
        y_mono = y
    else:
        y_mono = np.mean(y, axis=0)
    duration = y.shape[1] / sr if y.ndim > 1 else len(y) / sr
    
    if duration <= target_duration + 1:
        return output_path, duration
    
    if mode == "auto":
        rms = librosa.feature.rms(y=y_mono, hop_length=512)[0]
        frame_times = librosa.times_like(rms, sr=sr, hop_length=512)
        # 在 25%~75% 区间找最大 RMS 片段
        mid_idx = int(len(rms) * 0.5)
        search_range = slice(int(len(rms)*0.25), int(len(rms)*0.75))
        peak_idx = np.argmax(rms[search_range]) + int(len(rms)*0.25)
        start_time = max(0, frame_times[peak_idx] - target_duration/2)
    elif mode == "from_start":
        start_time = 0
    else:
        start_time = (duration - target_duration) / 2  # 中间
    end_time = min(start_time + target_duration, duration)
    actual_dur = end_time - start_time
    
    start_sample = int(start_time * sr)
    end_sample = int(end_time * sr)
    y_clip = y[:, start_sample:end_sample] if y.ndim > 1 else y[start_sample:end_sample]
    sf.write(output_path, y_clip.T if y.ndim > 1 else y_clip, sr)
    return output_path, actual_dur

class SmartClipInput(BaseModel):
    audio_path: str = Field(description="输入音频文件路径")
    target_duration: float = Field(description="目标时长（秒）")
    mode: str = Field(default="auto", description="截取模式：auto（高潮区）, from_start, from_middle")
    output_path: str | None = Field(default=None, description="输出路径（默认覆盖原文件）")

smart_clip_audio_tool = StructuredTool.from_function(
    coroutine=smart_clip_audio,
    name="smart_clip_audio",
    description="智能截取音频中最精彩的部分（默认选择能量最高的区域）使其达到目标时长。",
    args_schema=SmartClipInput,
)