# backend/app/agent/atomic_tools/arrangement/set_portamento.py
import os
import mido
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def set_portamento(
    midi_path: str,
    output_path: str,
    track_index: int = 0,
    portamento_time_ms: int = 30,
) -> str:
    """
    为指定轨道添加 portamento（连奏滑音）控制。
    通过插入控制事件（CC 65 开启 portamento，RPN 设置时间）实现。
    """
    if not os.path.isfile(midi_path):
        raise ValueError(f"输入 MIDI 文件不存在: {midi_path}")

    mid = mido.MidiFile(midi_path)
    if track_index >= len(mid.tracks):
        raise ValueError(f"track_index {track_index} 超出范围，共有 {len(mid.tracks)} 个轨道")

    track = mid.tracks[track_index]
    # 在轨道开头插入 Portamento 控制消息
    # 1. 设置 Portamento 时间（RPN 0,0 然后 data entry MSB/LSB）
    # 为了简单，直接使用 CC 65 开启，但时间需要用 RPN 或使用 CC 5 与 CC 6 组合。
    # 更标准的方法：发送 RPN 序列，但许多播放器支持 CC 65=127 开启，CC 65=0 关闭，而时间需要通过 CC 5 (portamento time) 设置。
    # 这里我们采用发送 CC 5 (Portamento Time) 和 CC 65 (Portamento On) 的方式。
    # 转换 time_ms 到 MIDI 值：0-127 对应 0-127? 实际时间范围取决于设备，我们按线性映射 0-127 对应 0-1270 ms。
    time_value = min(127, portamento_time_ms // 10)
    portamento_on = mido.Message('control_change', channel=0, control=65, value=127, time=0)
    time_cc = mido.Message('control_change', channel=0, control=5, value=time_value, time=0)

    # 在轨道最前面插入（t=0）
    new_track = mido.MidiTrack()
    new_track.append(portamento_on)
    new_track.append(time_cc)
    # 复制原轨道所有消息
    for msg in track:
        new_track.append(msg)
    # 如果需要，可以在结束关闭 portamento（可选）
    # portamento_off = mido.Message('control_change', channel=0, control=65, value=0, time=0)
    # new_track.append(portamento_off)

    mid.tracks[track_index] = new_track
    mid.save(output_path)
    return output_path

class SetPortamentoInput(BaseModel):
    midi_path: str = Field(..., description="输入 MIDI 文件的完整绝对路径")
    output_path: str = Field(..., description="输出 MIDI 文件的完整绝对路径（必须由系统指定）")
    track_index: int = Field(default=0, description="要应用 portamento 的轨道索引")
    portamento_time_ms: int = Field(default=30, description="滑音时间（毫秒），0-1270 映射到 0-127")

set_portamento_tool = StructuredTool.from_function(
    coroutine=set_portamento,
    name="set_portamento",
    description="为指定 MIDI 轨道开启连奏（portamento）并设置滑音时间。",
    args_schema=SetPortamentoInput,
)