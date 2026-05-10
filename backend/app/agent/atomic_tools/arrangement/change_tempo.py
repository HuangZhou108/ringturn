# app/agent/atomic_tools/arrangement/change_tempo.py
from ..midi.set_tempo import set_midi_tempo
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def change_tempo(midi_path: str, new_bpm: float, output_path: str | None = None) -> str:
    """改编时调整速度（直接复用 set_midi_tempo）"""
    return await set_midi_tempo(midi_path, new_bpm, output_path)

class ChangeTempoInput(BaseModel):
    midi_path: str = Field(description="输入 MIDI 文件路径")
    new_bpm: float = Field(description="新的 BPM")
    output_path: str | None = Field(default=None, description="输出路径（可选）")

change_tempo_tool = StructuredTool.from_function(
    coroutine=change_tempo,
    name="change_tempo",
    description="调整 MIDI 文件的速度（BPM）。",
    args_schema=ChangeTempoInput,
)