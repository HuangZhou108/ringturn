# backend/app/agent/atomic_tools/analysis/spleeter_separate.py

"""
Spleeter 音源分离原子工具

功能：
- 使用 Deezer 的 Spleeter 快速分离音频
- 支持 2 轨、4 轨、5 轨分离
- 速度极快（100 倍实时），适合快速预处理或轻量场景
"""

import os
from pathlib import Path
from typing import Dict, Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


async def separate_sources_spleeter(
    audio_path: str,
    output_dir: str | None = None,
    stems: Literal["2", "4", "5"] = "4"
) -> Dict[str, str]:
    """
    使用 Spleeter 快速分离音频中的多个声部。

    Spleeter 可以在 GPU 上实现高达 100 倍实时速度的分离[reference:0]，
    适合需要快速处理或对分离质量要求不是最高的场景。

    Args:
        audio_path: 输入音频文件的绝对路径
        output_dir: 输出目录（默认为音频文件所在目录下的 spleeter_output）
        stems: 分离轨道数（2: vocals/accompaniment, 4: vocals/drums/bass/other, 5: 同4但更细）

    Returns:
        dict: 包含各轨道路径
    """
    try:
        from spleeter.separator import Separator
    except ImportError:
        raise RuntimeError("Spleeter not found. Please install with: pip install spleeter")

    if output_dir is None:
        output_dir = str(Path(audio_path).parent / "spleeter_output")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 选择分离配置
    config_map = {
        "2": "spleeter:2stems",
        "4": "spleeter:4stems",
        "5": "spleeter:5stems",
    }
    separator = Separator(config_map[stems])

    # 执行分离
    separation = separator.separate_to_file(audio_path, output_dir)

    # 解析输出
    result_dict = {}
    audio_name = Path(audio_path).stem
    output_path = Path(output_dir) / audio_name

    for stem_file in output_path.iterdir():
        stem = stem_file.stem
        result_dict[f"{stem}_path"] = str(stem_file)

    return result_dict


class SpleeterInput(BaseModel):
    audio_path: str = Field(..., description="音频文件的绝对路径")
    output_dir: str | None = Field(default=None, description="输出目录")
    stems: Literal["2", "4", "5"] = Field(
        default="4",
        description="分离轨道数"
    )


spleeter_separate_tool = StructuredTool.from_function(
    coroutine=separate_sources_spleeter,
    name="spleeter_separate",
    description=(
        "使用 Deezer 的 Spleeter 快速分离音频声部。"
        "速度极快（100 倍实时），但分离质量低于 Demucs。"
    ),
    args_schema=SpleeterInput,
)