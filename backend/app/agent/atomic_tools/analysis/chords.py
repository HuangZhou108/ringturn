# app/agent/atomic_tools/analysis/chords.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def extract_chord_progression(audio_path: str, num_chords: int = 8) -> list[dict]:
    """
    提取和弦进行（简化版，基于 chroma 相似度）。

    Args:
        audio_path: 音频路径
        num_chords: 和弦数量

    Returns:
        list[dict]: 每个元素 {"start": float, "end": float, "chord": str}
    """
    y, sr = librosa.load(audio_path, sr=22050)
    duration = librosa.get_duration(y=y, sr=sr)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    hop_length = chroma.shape[1] // num_chords
    chord_labels = []
    for i in range(num_chords):
        segment = chroma[:, i*hop_length:(i+1)*hop_length] if i < num_chords-1 else chroma[:, i*hop_length:]
        avg = np.mean(segment, axis=1)
        idx = np.argmax(avg)
        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        chord_labels.append(note_names[idx])
    
    chord_duration = duration / num_chords
    chords = []
    for i, chord in enumerate(chord_labels):
        start = i * chord_duration
        end = min((i+1) * chord_duration, duration)
        chords.append({"start": float(start), "end": float(end), "chord": chord})
    return chords

class ExtractChordProgressionInput(BaseModel):
    audio_path: str = Field(description="音频文件的绝对路径")
    num_chords: int = Field(default=8, description="提取的和弦数量，默认8个")

extract_chord_progression_tool = StructuredTool.from_function(
    coroutine=extract_chord_progression,
    name="extract_chord_progression",
    description="提取音频的和弦进行，返回每个和弦的开始时间、结束时间和和弦名称。适用于了解和声结构。",
    args_schema=ExtractChordProgressionInput,
)