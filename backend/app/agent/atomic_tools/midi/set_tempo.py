# app/agent/atomic_tools/midi/set_tempo.py
import mido
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def set_midi_tempo(midi_path: str, new_bpm: float, output_path: str | None = None) -> str:
    """
    修改 MIDI 文件的速度。

    本函数直接修改 set_tempo 元消息，保留所有音符的相对时值。

    Args:
        midi_path: 输入 MIDI 路径
        new_bpm: 新速度
        output_path: 输出路径（默认在原文件名后加 _tempo）

    Returns:
        str: 输出路径
    """
    if output_path is None:
        output_path = midi_path.replace(".mid", f"_tempo.mid")
    mid = mido.MidiFile(midi_path)
    new_tempo = mido.bpm2tempo(new_bpm)
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                msg.tempo = new_tempo
    # 如果没有 set_tempo，则在第一轨添加
    has_tempo = any(msg.type == 'set_tempo' for track in mid.tracks for msg in track)
    if not has_tempo and mid.tracks:
        mid.tracks[0].insert(0, mido.MetaMessage('set_tempo', tempo=new_tempo, time=0))
    mid.save(output_path)
    return output_path

class SetMidiTempoInput(BaseModel):
    midi_path: str = Field(description="输入 MIDI 文件路径")
    new_bpm: float = Field(description="目标 BPM")
    output_path: str | None = Field(default=None, description="输出路径（可选）")

set_midi_tempo_tool = StructuredTool.from_function(
    coroutine=set_midi_tempo,
    name="set_midi_tempo",
    description="修改 MIDI 文件的速度（BPM），保持音符的相对时值不变。",
    args_schema=SetMidiTempoInput,
)