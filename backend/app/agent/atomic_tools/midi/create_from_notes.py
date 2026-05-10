# app/agent/atomic_tools/midi/create_from_notes.py
import mido
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import List, Dict, Any

async def create_midi_from_notes(
    notes: list[dict],
    bpm: float,
    output_path: str,
    ticks_per_beat: int = 480
) -> str:
    """
    根据音符列表生成 MIDI 文件。

    Args:
        notes: 每个音符包含 pitch, start, end, velocity
        bpm: 节拍速度
        output_path: 输出 MIDI 路径
        ticks_per_beat: MIDI 时钟精度

    Returns:
        str: 输出路径
    """
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    
    tempo = mido.bpm2tempo(bpm)
    track.append(mido.MetaMessage('set_tempo', tempo=tempo, time=0))
    
    last_ticks = 0
    for note in notes:
        start_ticks = int(note["start"] * ticks_per_beat * (bpm / 60))
        dur_ticks = int((note["end"] - note["start"]) * ticks_per_beat * (bpm / 60))
        wait = max(0, start_ticks - last_ticks)
        track.append(mido.Message('note_on', channel=0, note=note["pitch"], velocity=note["velocity"], time=wait))
        track.append(mido.Message('note_off', channel=0, note=note["pitch"], velocity=0, time=dur_ticks))
        last_ticks = start_ticks + dur_ticks
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    mid.save(output_path)
    return output_path

class CreateMidiFromNotesInput(BaseModel):
    notes: List[Dict[str, Any]] = Field(description="音符列表，每个音符需包含 pitch, start, end, velocity")
    bpm: float = Field(description="速度（BPM）")
    output_path: str = Field(description="输出 MIDI 文件路径")
    ticks_per_beat: int = Field(default=480, description="MIDI 时钟精度")

create_midi_from_notes_tool = StructuredTool.from_function(
    coroutine=create_midi_from_notes,
    name="create_midi_from_notes",
    description="根据音符列表和 BPM 生成 MIDI 文件。",
    args_schema=CreateMidiFromNotesInput,
)