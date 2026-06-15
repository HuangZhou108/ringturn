# backend/app/agent/atomic_tools/arrangement/transpose_pitch.py
import os
import mido
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def transpose_pitch(
    midi_path: str,
    output_path: str,
    semitones: int,
) -> str:
    """
    将 MIDI 中所有音符（note_on/note_off）的音高整体移调。
    """
    if not os.path.isfile(midi_path):
        raise ValueError(f"输入 MIDI 文件不存在: {midi_path}")

    mid = mido.MidiFile(midi_path)
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'note_on' or msg.type == 'note_off':
                new_note = msg.note + semitones
                if new_note < 0 or new_note > 127:
                    raise ValueError(f"移调后音高 {new_note} 超出 MIDI 范围 (0-127)")
                msg.note = new_note
    mid.save(output_path)
    return output_path

class TransposePitchInput(BaseModel):
    midi_path: str = Field(..., description="输入 MIDI 文件的完整绝对路径")
    output_path: str = Field(..., description="输出 MIDI 文件的完整绝对路径（必须由系统指定）")
    semitones: int = Field(..., description="移调半音数，正数升高，负数降低，如 +2 表示升高全音")

transpose_pitch_tool = StructuredTool.from_function(
    coroutine=transpose_pitch,
    name="transpose_pitch",
    description="整体移调 MIDI 中所有音符的音高。",
    args_schema=TransposePitchInput,
)