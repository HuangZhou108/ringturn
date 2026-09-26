# app/agent/atomic_tools/melody/merge_notes.py
"""
音符合并工具

将旋律提取/量化产生的碎片化音符合并，提升连贯性：
1. 合并音高相同、间隔极小（gap < merge_gap）的相邻音符（含重叠）
2. 去除被其它音符完全覆盖的重叠重复音符
3. 可选合并相差一个八度的相邻音符（octave_merge）
"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import List, Dict, Any


async def merge_notes(
    melody_notes: list[dict],
    merge_gap: float = 0.05,
    octave_merge: bool = False,
) -> list[dict]:
    """
    合并碎片化的相邻同音高音符，去除重叠重复音符。

    Args:
        melody_notes: 音符列表，每个含 pitch, start, end, velocity, confidence
        merge_gap: 相邻同音高音符间隔小于该值（秒）时合并
        octave_merge: 是否合并相差一个八度的相邻音符（默认关闭）

    Returns:
        list[dict]: 合并后的音符列表
    """
    if not melody_notes:
        return []

    notes = sorted(melody_notes, key=lambda n: (n["start"], n["end"]))
    merged = []

    for note in notes:
        pitch = note["pitch"]
        start = note["start"]
        end = note["end"]

        if not merged:
            merged.append(dict(note))
            continue

        prev = merged[-1]
        gap = start - prev["end"]
        same_pitch = pitch == prev["pitch"]
        if octave_merge:
            same_pitch = same_pitch or abs(pitch - prev["pitch"]) == 12

        if same_pitch and gap < merge_gap:
            # 同音高且几乎相连（含重叠）→ 合并成一个更长音符
            prev["end"] = max(prev["end"], end)
        elif start < prev["end"] and end <= prev["end"]:
            # 不同音高但被完全覆盖 → 丢弃（避免同刻叠音）
            continue
        elif start < prev["end"]:
            # 部分重叠 → 截断新音符起点，避免重叠
            merged.append({**note, "start": prev["end"]})
        else:
            merged.append(dict(note))

    return merged


class MergeNotesInput(BaseModel):
    melody_notes: List[Dict[str, Any]] = Field(description="音符列表，每个音符包含 pitch, start, end, velocity, confidence")
    merge_gap: float = Field(default=0.05, description="相邻同音高音符间隔小于该值（秒）时合并")
    octave_merge: bool = Field(default=False, description="是否合并相差一个八度的相邻音符")


merge_notes_tool = StructuredTool.from_function(
    coroutine=merge_notes,
    name="merge_notes",
    description="合并旋律中碎片化的相邻同音高音符，去除重叠重复音符，提升旋律连贯性。",
    args_schema=MergeNotesInput,
)
