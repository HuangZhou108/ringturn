# backend/app/agent/atomic_tools/arrangement/merge_tracks.py
import os
import mido
from typing import List
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def merge_tracks(
    midi_path: str,
    output_path: str,
    track_indices: List[int],
) -> str:
    """
    将 track_indices 中指定的所有轨道合并到第一个轨道（按索引最小者），
    事件按绝对时间排序，删除其余轨道。
    """
    if not os.path.isfile(midi_path):
        raise ValueError(f"输入 MIDI 文件不存在: {midi_path}")

    mid = mido.MidiFile(midi_path)
    indices = sorted(set(track_indices))
    for idx in indices:
        if idx >= len(mid.tracks):
            raise ValueError(f"轨道索引 {idx} 超出范围，共有 {len(mid.tracks)} 个轨道")
    if len(indices) < 2:
        raise ValueError("至少需要两个轨道才能合并")

    target_idx = indices[0]
    target_track = mid.tracks[target_idx]

    # 收集所有要合并轨道的绝对时间事件
    events = []  # (abs_time, msg)
    for idx in indices:
        track = mid.tracks[idx]
        abs_time = 0
        for msg in track:
            abs_time += msg.time
            events.append((abs_time, msg))

    events.sort(key=lambda x: x[0])
    # 重建目标轨道
    new_track = mido.MidiTrack()
    last_abs = 0
    for abs_t, msg in events:
        delta = max(0, abs_t - last_abs)
        msg.time = delta
        new_track.append(msg)
        last_abs = abs_t

    # 替换目标轨道，并删除其他轨道（从后往前删）
    mid.tracks[target_idx] = new_track
    for idx in sorted(indices[1:], reverse=True):
        del mid.tracks[idx]

    mid.save(output_path)
    return output_path

class MergeTracksInput(BaseModel):
    midi_path: str = Field(..., description="输入 MIDI 文件的完整绝对路径")
    output_path: str = Field(..., description="输出 MIDI 文件的完整绝对路径（必须由系统指定）")
    track_indices: List[int] = Field(..., description="要合并的轨道索引列表，第一个索引作为目标轨道")

merge_tracks_tool = StructuredTool.from_function(
    coroutine=merge_tracks,
    name="merge_tracks",
    description="将多个 MIDI 轨道合并到一个轨道，事件按时间顺序排列。",
    args_schema=MergeTracksInput,
)