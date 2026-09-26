# app/agent/atomic_tools/melody/snap_to_key.py
"""
旋律调性校正工具

对旋律做两件事，减少"错误音/不和谐"：
1. 八度校正：用滑动中位数修复 Basic Pitch 常见的八度误判（仅当偏离邻居 ≥ 1 个八度时）
2. 调性校正：把音符 snap 到检测调性的大/小调音阶内（仅校正离调 1 半音以内的音，保留经过音）
"""
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import List, Dict, Any

MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]


async def snap_to_key(
    melody_notes: list[dict],
    key_midi: int | None = None,
    mode: str = "major",
    snap_threshold: float = 0.0,
    octave_correct: bool = True,
) -> list[dict]:
    """
    校正旋律音高。

    Args:
        melody_notes: 音符列表（pitch, start, end, velocity, confidence）
        key_midi: 调性根音 MIDI（用于构建音阶），None 则跳过调性校正
        mode: 'major' 或 'minor'
        snap_threshold: 离调超过该半音数则不强校正；默认 0 表示不做调性 snap
            （只做八度校正，最大程度保留原曲经过音，提高与原文相似度）
        octave_correct: 是否做八度误判校正

    Returns:
        list[dict]: 校正后的音符列表
    """
    if not melody_notes:
        return []

    notes = sorted(melody_notes, key=lambda n: (n["start"], n["end"]))

    # 1. 八度校正：滑动中位数（窗口 3），仅校正 ≥ 1 个八度的突变
    if octave_correct:
        pitches = [n["pitch"] for n in notes]
        out = []
        for i, n in enumerate(notes):
            lo = max(0, i - 1)
            hi = min(len(notes), i + 2)
            med = float(np.median(pitches[lo:hi]))
            p = n["pitch"]
            while p - med >= 12:
                p -= 12
            while med - p >= 12:
                p += 12
            out.append({**n, "pitch": int(p)})
        notes = out

    # 2. 调性校正：snap 到调内音阶
    if key_midi is not None:
        intervals = MINOR if mode == "minor" else MAJOR
        scale_pcs = set((key_midi + iv) % 12 for iv in intervals)
        for n in notes:
            pc = n["pitch"] % 12
            if pc in scale_pcs:
                continue
            best_delta = 12
            for spc in scale_pcs:
                d = pc - spc
                if d > 6:
                    d -= 12
                elif d < -6:
                    d += 12
                if abs(d) < abs(best_delta):
                    best_delta = d
            if abs(best_delta) <= snap_threshold:
                n["pitch"] = int(n["pitch"] - best_delta)
    return notes


class SnapToKeyInput(BaseModel):
    melody_notes: List[Dict[str, Any]] = Field(description="音符列表，每个音符包含 pitch, start, end, velocity, confidence")
    key_midi: int | None = Field(default=None, description="调性根音 MIDI，None 则跳过调性校正")
    mode: str = Field(default="major", description="调式：major 或 minor")
    snap_threshold: float = Field(default=0.0, description="离调超过该半音数则不校正；0 表示不做调性 snap")
    octave_correct: bool = Field(default=True, description="是否做八度误判校正")


snap_to_key_tool = StructuredTool.from_function(
    coroutine=snap_to_key,
    name="snap_to_key",
    description="校正旋律音高：修复八度误判，并把音符 snap 到调内音阶，减少错误音。",
    args_schema=SnapToKeyInput,
)
