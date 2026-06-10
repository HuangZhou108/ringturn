# backend/app/agent/atomic_tools/analysis/open_unmix_separate.py

"""
Open-Unmix 音源分离原子工具

功能：
- 使用 Inria 的 Open-Unmix 分离音频
- 质量介于 Spleeter 和 Demucs 之间
- 轻量级，适合资源受限环境
"""

from pathlib import Path
from typing import Dict, Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


async def separate_sources_open_unmix(
    audio_path: str,
    output_dir: str | None = None,
    stems: Literal["vocals", "drums", "bass", "other"] = "all"
) -> Dict[str, str]:
    """
    使用 Open-Unmix 分离音频声部。

    Open-Unmix 是基于 PyTorch 的轻量级分离模型，在质量与速度之间取得平衡。

    Args:
        audio_path: 输入音频文件的绝对路径
        output_dir: 输出目录
        stems: 要分离的声部（默认为所有四个声部）

    Returns:
        dict: 包含各轨道路径
    """
    try:
        import torch
        import openunmix
        from openunmix import predict
    except ImportError:
        raise RuntimeError("openunmix not found. Please install with: pip install openunmix")

    if output_dir is None:
        output_dir = str(Path(audio_path).parent / "openunmix_output")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 加载音频
    audio, rate = openunmix.utils.load_audio(audio_path)

    # 执行分离
    estimates = predict.separate(
        audio=audio,
        rate=rate,
        targets=["vocals", "drums", "bass", "other"],
        device="cuda" if torch.cuda.is_available() else "cpu"
    )

    # 保存分离结果
    result_dict = {}
    for target, estimate in estimates.items():
        output_path = Path(output_dir) / f"{target}.wav"
        openunmix.utils.save_audio(estimate, output_path, rate)
        result_dict[f"{target}_path"] = str(output_path)

    return result_dict


class OpenUnmixInput(BaseModel):
    audio_path: str = Field(..., description="音频文件的绝对路径")
    output_dir: str | None = Field(default=None, description="输出目录")


open_unmix_separate_tool = StructuredTool.from_function(
    coroutine=separate_sources_open_unmix,
    name="open_unmix_separate",
    description=(
        "使用 Open-Unmix 分离音频声部。"
        "基于 PyTorch，轻量且易于部署，质量与速度平衡。"
    ),
    args_schema=OpenUnmixInput,
)