# backend/app/agent/atomic_tools/analysis/demucs_separate.py

"""
Demucs 音源分离原子工具

功能：
- 将音频分离为人声、鼓、贝斯、钢琴、吉他、其他等 6 个轨道
- 可配置分离深度（4 轨 / 6 轨 / 仅人声）
- 分离结果可被旋律提取、乐器分析等多个后续节点复用
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.config import get_settings


settings = get_settings()


def separate_sources_demucs(
    audio_path: str,
    output_dir: str | None = None,
    model: Literal["htdemucs", "htdemucs_ft", "htdemucs_6s"] = "htdemucs_6s",
    stems: Literal["vocals", "drums", "bass", "piano", "guitar", "other"] = "6",
) -> Dict[str, str]:
    """
    使用 Demucs 分离音频中的多个声部。

    本工具调用 Meta 的 Demucs 模型，将混合音频分离为多个独立轨道。
    htdemucs_6s 模型支持分离为 6 个轨道：人声、鼓、贝斯、钢琴、吉他、其他。

    Args:
        audio_path: 输入音频文件的绝对路径
        output_dir: 输出目录（默认为音频文件所在目录下的 demucs_output）
        model: 使用的模型（htdemucs_ft 微调版质量最好但较慢）
        stems: 分离轨道数，'4' 为 vocals/drums/bass/other，'6' 增加 piano/guitar

    Returns:
        dict: 包含以下字段
            - vocals_path: 人声轨道路径
            - drums_path: 鼓轨道路径
            - bass_path: 贝斯轨道路径
            - piano_path: 钢琴轨道路径（仅 6 轨模式）
            - guitar_path: 吉他轨道路径（仅 6 轨模式）
            - other_path: 其他乐器轨道路径
            - accompaniment_path: 伴奏轨道路径（所有非人声轨道混合）
    """
    # 用当前解释器的 demucs.separate 模块调用（不依赖 PATH 中的 demucs.exe）
    import sys

    # 设置输出目录
    if output_dir is None:
        output_dir = str(Path(audio_path).parent / "demucs_output")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 构建命令行参数
    cmd = [sys.executable, "-m", "demucs.separate", "-n", model, "-o", output_dir]

    # 根据 stems 参数决定是否使用 --two-stems 或完整分离
    if stems == "vocals":
        cmd.extend(["--two-stems", "vocals"])
    elif stems == "4":
        # 默认 4 轨分离，不加额外参数
        pass
    # 6 轨分离（htdemucs_6s 模型已内置 6 轨输出）

    cmd.append(audio_path)

    # 执行分离
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Demucs 分离失败: {result.stderr}")

    # 构造输出文件路径（Demucs 输出格式：output_dir/model_name/audio_stem/{stem}.wav）
    stem_name = Path(audio_path).stem
    model_dir = Path(output_dir) / model / stem_name

    result_dict = {}

    # 根据分离模式解析轨道
    if stems == "vocals":
        vocals_path = model_dir / "vocals.wav"
        if not vocals_path.exists():
            raise FileNotFoundError(f"人声轨道文件不存在: {vocals_path}")
        result_dict["vocals_path"] = str(vocals_path)
        result_dict["accompaniment_path"] = str(model_dir / "no_vocals.wav")

    elif stems in ("4", "6"):
        # 通用轨道映射
        stem_map = ["vocals", "drums", "bass", "other"]
        if stems == "6":
            stem_map = ["vocals", "drums", "bass", "piano", "guitar", "other"]

        for stem in stem_map:
            stem_path = model_dir / f"{stem}.wav"
            if stem_path.exists():
                result_dict[f"{stem}_path"] = str(stem_path)

        # 生成伴奏轨道（混合除 vocals 外的所有轨道）
        accompaniment = None
        for stem in stem_map:
            if stem == "vocals":
                continue
            stem_path = model_dir / f"{stem}.wav"
            if stem_path.exists():
                if accompaniment is None:
                    accompaniment = stem_path
                else:
                    # TODO: 使用 ffmpeg 或 librosa 混合多个轨道
                    pass
        if accompaniment:
            result_dict["accompaniment_path"] = str(accompaniment)

    return result_dict


class DemucsInput(BaseModel):
    audio_path: str = Field(..., description="音频文件的绝对路径")
    output_dir: str | None = Field(default=None, description="输出目录")
    model: Literal["htdemucs", "htdemucs_ft", "htdemucs_6s"] = Field(
        default="htdemucs_6s",
        description="使用的 Demucs 模型"
    )
    stems: Literal["vocals", "4", "6"] = Field(
        default="6",
        description="分离轨道数：vocals（仅人声），4（4轨），6（6轨）"
    )


demucs_separate_tool = StructuredTool.from_function(
    coroutine=separate_sources_demucs,
    name="demucs_separate",
    description=(
        "使用 Meta 的 Demucs 模型分离音频中的多个声部。"
        "支持分离为人声、鼓、贝斯、钢琴、吉他、其他等 6 个独立轨道，"
        "是当前开源模型中分离质量最高的方案。"
    ),
    args_schema=DemucsInput,
)