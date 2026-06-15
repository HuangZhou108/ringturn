# backend/app/agent/atomic_tools/analysis/omnizart_transcribe.py

"""
Omnizart 综合音乐转录原子工具

功能：
- 综合转录工具包，覆盖乐器、人声旋律、和弦、节拍、鼓等多个维度
- 一站式分析，输出完整的 MIDI 转录结果
"""

from pathlib import Path
from typing import Dict, Any, Optional, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


async def omnizart_transcribe(
    audio_path: str,
    output_dir: Optional[str] = None,
    task: Literal["music", "vocal", "chord", "beat", "drum"] = "music"
) -> Dict[str, Any]:
    """
    使用 Omnizart 对音频进行综合分析。

    Omnizart 是首个覆盖广泛乐器类别的通用转录工具箱[reference:2]，
    支持独奏、器乐合奏、打击乐器、人声旋律、和弦及节拍识别。

    Args:
        audio_path: 输入音频文件的绝对路径
        output_dir: 输出目录
        task: 转录任务类型

    Returns:
        dict: 包含以下字段
            - midi_path: 生成的 MIDI 文件路径
            - instrument_tracks: 乐器轨道信息
            - chord_progression: 和弦进行（如 task 包含 chord）
            - bpm: 节拍速度
            - drum_pattern: 鼓点模式（如有）
    """
    try:
        from omnizart.music import app as music_app
        from omnizart.vocal import app as vocal_app
        from omnizart.chord import app as chord_app
        from omnizart.beat import app as beat_app
        from omnizart.drum import app as drum_app
    except ImportError:
        raise RuntimeError(
            "Omnizart 未安装。安装方式: pip install omnizart"
        )

    if output_dir is None:
        output_dir = str(Path(audio_path).parent / "omnizart_output")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    result = {}

    if task == "music":
        # 音乐转录（多乐器）
        midi_path = music_app.transcribe(audio_path, output_dir=output_dir)
        result["midi_path"] = midi_path
        # TODO: 解析 MIDI 文件，提取乐器轨道信息
        result["instrument_tracks"] = []

    elif task == "vocal":
        # 人声旋律转录
        midi_path = vocal_app.transcribe(audio_path, output_dir=output_dir)
        result["midi_path"] = midi_path

    elif task == "chord":
        # 和弦识别
        chord_result = chord_app.transcribe(audio_path, output_dir=output_dir)
        result["chord_progression"] = chord_result

    elif task == "beat":
        # 节拍检测
        beat_result = beat_app.transcribe(audio_path, output_dir=output_dir)
        result["bpm"] = beat_result.get("bpm")
        result["beat_times"] = beat_result.get("beats")

    elif task == "drum":
        # 鼓转录
        drum_result = drum_app.transcribe(audio_path, output_dir=output_dir)
        result["drum_pattern"] = drum_result

    return result


class OmnizartInput(BaseModel):
    audio_path: str = Field(..., description="音频文件的绝对路径")
    output_dir: str | None = Field(default=None, description="输出目录")
    task: Literal["music", "vocal", "chord", "beat", "drum"] = Field(
        default="music",
        description="转录任务类型"
    )


omnizart_transcribe_tool = StructuredTool.from_function(
    coroutine=omnizart_transcribe,
    name="omnizart_transcribe",
    description=(
        "使用 Omnizart 进行综合音乐转录。支持多乐器转录、人声旋律、和弦识别、节拍检测、"
        "鼓点转录等多种任务，是一个全能的 MIR 工具包。"
    ),
    args_schema=OmnizartInput,
)