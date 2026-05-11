# app/agent/atomic_tools/arrangement/change_instrument.py
import os
import mido
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

# GM 乐器映射表（与原来保持一致）
INSTRUMENTS = {
    "piano": 0,
    "electric_piano": 4,
    "guitar": 24,
    "electric_guitar": 27,
    "bass": 32,
    "violin": 40,
    "cello": 42,
    "strings": 48,
    "flute": 73,
    "saxophone": 66,
    "organ": 19,
    "harp": 46,
    "bell": 14,
    "chime": 91,
}

def _get_instrument_number(name: str) -> int:
    name_lower = name.lower()
    for key, val in INSTRUMENTS.items():
        if key in name_lower or name_lower in key:
            return val
    return 0  # default piano

async def change_instrument(midi_path: str, target_instrument: str, output_path: str | None = None) -> str:
    """
    将 MIDI 文件中的所有音轨乐器更换为目标 GM 乐器。

    Args:
        midi_path: 输入 MIDI 路径
        target_instrument: 乐器名称（如 "piano", "violin"）
        output_path: 输出路径

    Returns:
        str: 输出路径
    """
    if not os.path.isfile(midi_path):
        raise ValueError(f"输入 MIDI 文件不存在: {midi_path}")
    if output_path is None:
        output_path = midi_path.replace(".mid", "_instr.mid")
    mid = mido.MidiFile(midi_path)
    program = _get_instrument_number(target_instrument)
    
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'program_change':
                msg.program = program
    # 如果没有 program_change，在第一个非元消息前插入
    has_program = any(msg.type == 'program_change' for track in mid.tracks for msg in track)
    if not has_program and mid.tracks:
        track = mid.tracks[0]
        new_track = []
        inserted = False
        for msg in track:
            if not inserted and msg.type not in ('track_name', 'time_signature', 'set_tempo'):
                new_track.append(mido.Message('program_change', program=program, time=0))
                inserted = True
            new_track.append(msg)
        if not inserted:
            new_track.insert(0, mido.Message('program_change', program=program, time=0))
        mid.tracks[0] = new_track
    mid.save(output_path)
    if not os.path.isfile(output_path):
        raise RuntimeError(f"改编后的 MIDI 未成功保存至 {output_path}")
    return output_path

class ChangeInstrumentInput(BaseModel):
    midi_path: str = Field(..., description="输入 MIDI 文件的完整绝对路径，必须是可读文件")
    target_instrument: str = Field(description="目标乐器名称，如 piano, violin, guitar 等")
    output_path: str = Field(..., description="输出 MIDI 文件的完整路径，必须由系统指定，不得编造")

change_instrument_tool = StructuredTool.from_function(
    coroutine=change_instrument,
    name="change_instrument",
    description=(
        "将 MIDI 文件中所有音轨的乐器更换为目标 GM 乐器。"
        "必须提供 output_path，且必须使用系统给定的输出路径。"
    ),
    args_schema=ChangeInstrumentInput,
)