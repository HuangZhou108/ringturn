# backend/app/agent/atomic_tools/arrangement/add_delay_echo.py
import os
import mido
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def add_delay_echo(
    midi_path: str,
    output_path: str,
    delay_seconds: float,
    decay_factor: float = 0.5,
    repeats: int = 2,
) -> str:
    """
    为 MIDI 音符添加回声/延迟效果：复制音符并延迟，每次力度按衰减系数降低。
    """
    if not os.path.isfile(midi_path):
        raise ValueError(f"输入 MIDI 文件不存在: {midi_path}")

    mid = mido.MidiFile(midi_path)
    # 获取 ticks_per_beat 并计算 delay 对应的 ticks
    ticks_per_beat = mid.ticks_per_beat
    # 默认 tempo = 120 BPM -> 微秒每拍 500000，但为了通用，需要从文件中读取实际 tempo
    tempo_us_per_beat = 500000  # 默认 120 BPM
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                tempo_us_per_beat = msg.tempo
                break
    seconds_per_tick = (tempo_us_per_beat / 1_000_000) / ticks_per_beat
    delay_ticks = int(delay_seconds / seconds_per_tick)

    # 收集所有音符事件（绝对时间）
    for track in mid.tracks:
        abs_time = 0
        events = []  # (abs_time, msg)
        for msg in track:
            abs_time += msg.time
            events.append((abs_time, msg))

        # 创建回声事件
        new_events = events[:]
        for rep in range(1, repeats + 1):
            factor = decay_factor ** rep
            for abs_t, msg in events:
                if msg.type == 'note_on' and msg.velocity > 0:
                    new_msg = msg.copy()
                    new_vel = int(msg.velocity * factor)
                    if new_vel > 0:
                        new_msg.velocity = new_vel
                        new_abs_t = abs_t + delay_ticks * rep
                        new_events.append((new_abs_t, new_msg))
                    # note_off 也需要配对？先简单处理，后续通过 note_off 的延迟来避免无限延音
        # 重新排序并重建 track
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

class AddDelayEchoInput(BaseModel):
    midi_path: str = Field(..., description="输入 MIDI 文件的完整绝对路径")
    output_path: str = Field(..., description="输出 MIDI 文件的完整绝对路径（必须由系统指定）")
    delay_seconds: float = Field(..., description="延迟时间（秒）")
    decay_factor: float = Field(default=0.5, description="每次回声的力度衰减系数，0~1")
    repeats: int = Field(default=2, description="回声重复次数")

add_delay_echo_tool = StructuredTool.from_function(
    coroutine=add_delay_echo,
    name="add_delay_echo",
    description="为 MIDI 音符添加回声/延迟效果。",
    args_schema=AddDelayEchoInput,
)