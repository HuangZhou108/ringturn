# backend/app/agent/atomic_tools/arrangement/quantize_swing.py
import os
import mido
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def quantize_swing(
    midi_path: str,
    output_path: str,
    grid: float = 0.25,
    swing_ratio: float = 0.6,
) -> str:
    """
    对 MIDI 进行 swing 量化：将落在偶数网格上的音符向后延迟一定比例。
    """
    if not os.path.isfile(midi_path):
        raise ValueError(f"输入 MIDI 文件不存在: {midi_path}")

    mid = mido.MidiFile(midi_path)
    ticks_per_beat = mid.ticks_per_beat
    grid_ticks = int(ticks_per_beat * grid)  # 每个网格的 tick 数

    for track in mid.tracks:
        # 转为绝对时间
        abs_time = 0
        events = []  # (abs_time, msg)
        for msg in track:
            abs_time += msg.time
            events.append((abs_time, msg))

        # 收集所有 note_on 和 note_off 并进行量化
        # 简化：只对 note_on 进行 swing 偏移，note_off 跟随其偏移
        note_offsets = {}  # note -> offset
        new_events = []
        for abs_t, msg in events:
            if msg.type == 'note_on' and msg.velocity > 0:
                # 找到所在的网格索引
                grid_idx = abs_t // grid_ticks
                # 如果是偶数网格 (0,2,4...)，不偏移；奇数网格偏移 swing_ratio * grid_ticks
                if grid_idx % 2 == 1:
                    offset = int(swing_ratio * grid_ticks)
                else:
                    offset = 0
                new_abs_t = abs_t + offset
                note_offsets[msg.note] = offset
                new_msg = msg.copy()
                new_events.append((new_abs_t, new_msg))
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                offset = note_offsets.get(msg.note, 0)
                new_abs_t = abs_t + offset
                new_msg = msg.copy()
                new_events.append((new_abs_t, new_msg))
            else:
                # 非音符消息保持原时间
                new_events.append((abs_t, msg))

        new_events.sort(key=lambda x: x[0])
        new_track = mido.MidiTrack()
        last_abs = 0
        for abs_t, msg in new_events:
            delta = max(0, abs_t - last_abs)
            msg.time = delta
            new_track.append(msg)
            last_abs = abs_t
        # 替换原轨道
        mid.tracks[mid.tracks.index(track)] = new_track

    mid.save(output_path)
    return output_path

class QuantizeSwingInput(BaseModel):
    midi_path: str = Field(..., description="输入 MIDI 文件的完整绝对路径")
    output_path: str = Field(..., description="输出 MIDI 文件的完整绝对路径（必须由系统指定）")
    grid: float = Field(default=0.25, description="量化网格（拍），如 0.25 = 16分音符")
    swing_ratio: float = Field(default=0.6, description="摇摆强度，0~1，0.5 无摇摆，>0.5 产生摇摆感")

quantize_swing_tool = StructuredTool.from_function(
    coroutine=quantize_swing,
    name="quantize_swing",
    description="对 MIDI 音符应用 swing 量化，产生爵士摇摆感。",
    args_schema=QuantizeSwingInput,
)