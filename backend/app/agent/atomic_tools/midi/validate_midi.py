# app/agent/atomic_tools/midi/validate_midi.py
import mido
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def validate_midi_file(midi_path: str) -> bool:
    """
    检查 MIDI 文件是否有效且非空。

    Args:
        midi_path: MIDI 文件路径

    Returns:
        bool: 是否有效
    """
    if not Path(midi_path).exists():
        return False
    if Path(midi_path).stat().st_size == 0:
        return False
    try:
        mido.MidiFile(midi_path)
        return True
    except Exception:
        return False
    
class ValidateMidiFileInput(BaseModel):
    midi_path: str = Field(description="MIDI 文件路径")

validate_midi_file_tool = StructuredTool.from_function(
    coroutine=validate_midi_file,
    name="validate_midi_file",
    description="检查 MIDI 文件是否存在、非空且可被 mido 正确解析。",
    args_schema=ValidateMidiFileInput,
)