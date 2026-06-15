# backend/app/agent/atomic_tools/arrangement/copy_track.py
import os
import mido
from typing import Optional
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def copy_track(
    midi_path: str,
    output_path: str,
    source_track_index: int,
    target_track_index: Optional[int] = None,
) -> str:
    """
    复制指定轨道到新轨道。如果不指定 target_track_index，则追加到末尾。
    """
    if not os.path.isfile(midi_path):
        raise ValueError(f"输入 MIDI 文件不存在: {midi_path}")

    mid = mido.MidiFile(midi_path)
    if source_track_index >= len(mid.tracks):
        raise ValueError(f"source_track_index {source_track_index} 超出范围，共有 {len(mid.tracks)} 个轨道")

    source_track = mid.tracks[source_track_index]
    # 深拷贝轨道（直接复制消息列表）
    new_track = mido.MidiTrack()
    for msg in source_track:
        new_track.append(msg.copy())

    if target_track_index is None:
        mid.tracks.append(new_track)
    else:
        if target_track_index > len(mid.tracks):
            raise ValueError(f"target_track_index {target_track_index} 超出范围，最大可插入索引为 {len(mid.tracks)}")
        mid.tracks.insert(target_track_index, new_track)

    mid.save(output_path)
    return output_path

class CopyTrackInput(BaseModel):
    midi_path: str = Field(..., description="输入 MIDI 文件的完整绝对路径")
    output_path: str = Field(..., description="输出 MIDI 文件的完整绝对路径（必须由系统指定）")
    source_track_index: int = Field(..., description="要复制的源轨道索引")
    target_track_index: Optional[int] = Field(default=None, description="目标轨道索引，不指定则追加到末尾")

copy_track_tool = StructuredTool.from_function(
    coroutine=copy_track,
    name="copy_track",
    description="复制 MIDI 文件中的一个轨道到新轨道。",
    args_schema=CopyTrackInput,
)