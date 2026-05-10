# app/agent/atomic_tools/rendering/fluidsynth_render.py
import subprocess
import shutil
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def render_midi_with_fluidsynth(
    midi_path: str,
    soundfont_path: str,
    output_wav_path: str,
    sample_rate: int = 44100,
    duration_limit: float | None = None
) -> str:
    """
    使用 FluidSynth 将 MIDI 渲染为 WAV 音频。

    Args:
        midi_path: MIDI 文件路径
        soundfont_path: SF2 音色库路径
        output_wav_path: 输出 WAV 路径
        sample_rate: 采样率
        duration_limit: 限制渲染时长（秒），None 表示不限制

    Returns:
        str: 输出 WAV 路径
    """
    fluidsynth_path = shutil.which("fluidsynth")
    if not fluidsynth_path:
        raise RuntimeError("fluidsynth not found in PATH")
    if not Path(soundfont_path).exists():
        raise FileNotFoundError(f"Soundfont not found: {soundfont_path}")
    
    cmd = [fluidsynth_path, "-ni", "-F", output_wav_path, "-r", str(sample_rate)]
    if duration_limit:
        cmd.extend(["-d", str(int(duration_limit))])
    cmd.extend([soundfont_path, midi_path])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FluidSynth error: {result.stderr}")
    return output_wav_path

class RenderMidiInput(BaseModel):
    midi_path: str = Field(description="MIDI 文件路径")
    soundfont_path: str = Field(description="SF2 音色库路径")
    output_wav_path: str = Field(description="输出 WAV 文件路径")
    sample_rate: int = Field(default=44100, description="采样率")
    duration_limit: float | None = Field(default=None, description="限制渲染时长（秒）")

render_midi_with_fluidsynth_tool = StructuredTool.from_function(
    coroutine=render_midi_with_fluidsynth,
    name="render_midi_with_fluidsynth",
    description="使用 FluidSynth 将 MIDI 文件渲染为 WAV 音频文件。",
    args_schema=RenderMidiInput,
)