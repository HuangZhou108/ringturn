# app/agent/atomic_tools/analysis/harmony.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


async def analyze_harmony(audio_path: str, num_chords: int = 8) -> dict:
    """
    检测调性（含大小调）与和弦根音进行。

    用于后续的「旋律调性校正」和「多轨和声编曲（低音 + 和弦垫）」。
    采用 chroma 简版：根音 = 平均 chroma 最大的 pitch class，大小调由三度音能量判断。

    Returns:
        {"key": "C Major", "key_midi": 60, "mode": "major",
         "chords": [{"start": float, "end": float, "root_midi": int, "root_name": str}]}
    """
    import asyncio
    y, sr = await asyncio.to_thread(librosa.load, audio_path, sr=22050)
    chroma = await asyncio.to_thread(librosa.feature.chroma_cqt, y=y, sr=sr)
    chroma_mean = np.mean(chroma, axis=1)

    root_pc = int(np.argmax(chroma_mean))
    # 大小调：比较根音上方大三度(4) vs 小三度(3) 的能量
    mode = "major" if chroma_mean[(root_pc + 4) % 12] >= chroma_mean[(root_pc + 3) % 12] else "minor"
    key_midi = 60 + (root_pc % 12)  # 以 C4=60 为基准

    # 和弦根音进行：均分 num_chords 段，每段取 chroma argmax 作为根音
    duration = librosa.get_duration(y=y, sr=sr)
    seg_dur = duration / num_chords
    frames_per_seg = max(1, chroma.shape[1] // num_chords)
    chords = []
    for i in range(num_chords):
        if i < num_chords - 1:
            seg = chroma[:, i * frames_per_seg:(i + 1) * frames_per_seg]
        else:
            seg = chroma[:, i * frames_per_seg:]
        if seg.size == 0:
            continue
        seg_root_pc = int(np.argmax(np.mean(seg, axis=1)))
        chords.append({
            "start": float(i * seg_dur),
            "end": float(min((i + 1) * seg_dur, duration)),
            "root_midi": 60 + seg_root_pc,
            "root_name": NOTE_NAMES[seg_root_pc],
        })

    return {
        "key": f"{NOTE_NAMES[root_pc]} {mode.title()}",
        "key_midi": key_midi,
        "mode": mode,
        "chords": chords,
    }


class HarmonyInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")
    num_chords: int = Field(default=8, description="和弦根音分段数")


analyze_harmony_tool = StructuredTool.from_function(
    coroutine=analyze_harmony,
    name="analyze_harmony",
    description="检测调性（含大小调）与和弦根音进行，供旋律调性校正与多轨和声编曲使用。",
    args_schema=HarmonyInput,
)
