# app/agent/atomic_tools/melody/quantize_notes.py
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import List, Dict, Any

async def quantize_notes(melody_notes: list[dict], grid: float, bpm: float) -> list[dict]:
    """
    将音符的开始/结束时间量化到最近的网格（网格单位：拍）。

    Args:
        melody_notes: 音符列表
        grid: 网格大小（拍），如 0.25 = 16分音符
        bpm: 当前 BPM

    Returns:
        list[dict]: 量化后的音符列表
    """
    seconds_per_beat = 60.0 / bpm
    grid_seconds = grid * seconds_per_beat
    quantized = []
    for note in melody_notes:
        start = round(note["start"] / grid_seconds) * grid_seconds
        end = round(note["end"] / grid_seconds) * grid_seconds
        if end <= start:
            end = start + grid_seconds  # 避免零长度
        quantized.append({
            **note,
            "start": start,
            "end": end,
        })
    return quantized

class QuantizeNotesInput(BaseModel):
    melody_notes: List[Dict[str, Any]] = Field(description="音符列表")
    grid: float = Field(description="量化网格（拍），例如 0.25 = 16分音符")
    bpm: float = Field(description="当前 BPM")

quantize_notes_tool = StructuredTool.from_function(
    coroutine=quantize_notes,
    name="quantize_notes",
    description="将音符的开始和结束时间对齐到网格（如16分音符），使节奏更规整。",
    args_schema=QuantizeNotesInput,
)