# app/agent/atomic_tools/analysis/tempo_beats.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def detect_tempo_and_beats(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, sr=22050)
    # BPM
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='time')
    beat_times = beat_frames.tolist() if isinstance(beat_frames, np.ndarray) else []
    # 强拍检测（简化：以第一个 beat 为 downbeat，每 4 拍一个强拍）
    # 更精确可使用 madmom 或动态规划
    downbeat_times = [beat_times[i] for i in range(0, len(beat_times), 4)] if beat_times else []
    # 节拍号默认 4/4，可改进
    time_signature = "4/4"
    return {
        "bpm": float(tempo),
        "beat_times": beat_times,
        "downbeat_times": downbeat_times,
        "time_signature": time_signature
    }

class TempoBeatsInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

detect_tempo_beats_tool = StructuredTool.from_function(
    coroutine=detect_tempo_and_beats,
    name="detect_tempo_and_beats",
    description="检测 BPM、节拍时间点、强拍时间点、节拍号",
    args_schema=TempoBeatsInput
)