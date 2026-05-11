# app/agent/atomic_tools/melody/filter_short_notes.py
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import List, Dict, Any

async def filter_short_notes(melody_notes: list[dict], min_duration: float = 0.05) -> list[dict]:
    """
    过滤时长小于 min_duration 秒的音符，通常用于去除杂音。

    Args:
        melody_notes: 旋律音符列表
        min_duration: 最小持续时间（秒）

    Returns:
        list[dict]: 过滤后的音符列表
    """
    return [note for note in melody_notes if (note["end"] - note["start"]) >= min_duration]

class FilterShortNotesInput(BaseModel):
    melody_notes: List[Dict[str, Any]] = Field(description="音符列表，每个音符包含 pitch, start, end, velocity, confidence")
    min_duration: float = Field(default=0.05, description="最小持续时间（秒），短于此值的音符将被过滤")

filter_short_notes_tool = StructuredTool.from_function(
    coroutine=filter_short_notes,
    name="filter_short_notes",
    description="过滤掉时长过短（如小于0.05秒）的音符，去除杂音或误检。",
    args_schema=FilterShortNotesInput,
)