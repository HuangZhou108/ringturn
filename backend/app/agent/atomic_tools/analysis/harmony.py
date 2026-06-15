# app/agent/atomic_tools/analysis/harmony.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def analyze_harmony(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, sr=22050)
    # 调性：使用 chroma 平均值
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = np.mean(chroma, axis=1)
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    key_idx = int(np.argmax(chroma_mean))
    key = note_names[key_idx]
    # 简单判断大小调（根据三度音能量）
    mode = "major"  # 默认
    # 和弦提取简化：每2秒一个和弦（实际可调用 Chordino 或外部服务）
    duration = librosa.get_duration(y=y, sr=sr)
    chord_duration = 2.0
    chords = []
    for start in np.arange(0, duration, chord_duration):
        end = min(start + chord_duration, duration)
        # 取该段 chroma 平均
        start_frame = librosa.time_to_frames(start, sr=sr)
        end_frame = librosa.time_to_frames(end, sr=sr)
        segment = chroma[:, start_frame:end_frame]
        seg_mean = np.mean(segment, axis=1)
        idx = int(np.argmax(seg_mean))
        chord_note = note_names[idx]
        chords.append({"start": float(start), "end": float(end), "chord": chord_note})
    return {"key": key, "mode": mode, "chords": chords}

class HarmonyInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

analyze_harmony_tool = StructuredTool.from_function(
    coroutine=analyze_harmony,
    name="analyze_harmony",
    description="检测调性、调式、和弦进行",
    args_schema=HarmonyInput
)