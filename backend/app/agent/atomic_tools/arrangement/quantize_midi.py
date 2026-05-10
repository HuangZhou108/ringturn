# app/agent/atomic_tools/arrangement/quantize_midi.py
import mido
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def quantize_midi(midi_path: str, grid: float = 0.25, output_path: str | None = None) -> str:
    """
    对 MIDI 文件中的音符进行量化（对齐到网格）。

    Args:
        midi_path: 输入 MIDI
        grid: 网格（拍），如 0.25 = 16分音符
        output_path: 输出路径

    Returns:
        str: 输出路径
    """
    if output_path is None:
        output_path = midi_path.replace(".mid", "_quantized.mid")
    mid = mido.MidiFile(midi_path)
    ticks_per_beat = mid.ticks_per_beat
    grid_ticks = int(ticks_per_beat * grid)
    
    for track in mid.tracks:
        new_track = []
        current_ticks = 0
        note_start_ticks = {}
        for msg in track:
            current_ticks += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                quantized_start = (current_ticks // grid_ticks) * grid_ticks
                note_start_ticks[msg.note] = quantized_start
                time_adj = quantized_start - current_ticks
                new_msg = msg.copy(time=msg.time + time_adj)
                new_track.append(new_msg)
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                if msg.note in note_start_ticks:
                    quantized_start = note_start_ticks.pop(msg.note)
                    time_adj = quantized_start - current_ticks
                    new_msg = msg.copy(time=msg.time + time_adj)
                    new_track.append(new_msg)
                else:
                    new_track.append(msg)
            else:
                new_track.append(msg)
        track[:] = new_track
    mid.save(output_path)
    return output_path

class QuantizeMidiInput(BaseModel):
    midi_path: str = Field(description="输入 MIDI 文件路径")
    grid: float = Field(default=0.25, description="量化网格（拍），如 0.25 = 16分音符")
    output_path: str | None = Field(default=None, description="输出路径（可选）")

quantize_midi_tool = StructuredTool.from_function(
    coroutine=quantize_midi,
    name="quantize_midi",
    description="量化 MIDI 文件中的音符，使其对齐到指定的节拍网格。",
    args_schema=QuantizeMidiInput,
)