# backend/app/agent/atomic_tools/analysis/msaf_analyze.py

"""
MSAF 音乐结构分析原子工具

功能：
- 基于 MSAF 框架进行音乐结构分割
- 支持多种算法（Spectral Clustering, C-NMF, SF 等）
- 输出段落边界和段落聚类标签
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


async def analyze_structure_msaf(
    audio_path: str,
    algorithm: Literal["scluster", "cnmf", "sf", "olda"] = "scluster"
) -> Dict[str, Any]:
    """
    使用 MSAF 框架分析音乐结构。

    MSAF 提供多种结构分割算法实现，其中 scluster（谱聚类）+ olda 边界检测的组合在评测中表现最佳[reference:4]。

    Args:
        audio_path: 输入音频文件的绝对路径
        algorithm: 使用的分割算法

    Returns:
        dict: 包含以下字段
            - sections: 段落列表，每个元素包含 start, end, label
            - boundaries: 边界时间点列表
            - hierar: 层次化分割结果
    """
    try:
        import msaf
    except ImportError:
        raise RuntimeError("MSAF not found. Please install with: pip install msaf")

    # 加载音频文件并运行结构分割
    # TODO: MSAF 的分割算法通常需要指定特征提取器
    # 完整示例见官方文档：https://msaf.readthedocs.io/

    result = msaf.process(
        audio_path,
        boundaries_id=algorithm if algorithm == "olda" else "cnmf",
        labels_id=algorithm if algorithm in ("scluster", "sf") else "scluster"
    )

    sections = []
    for i, bound in enumerate(result["boundaries"]):
        if i + 1 < len(result["boundaries"]):
            sections.append({
                "start": result["boundaries"][i],
                "end": result["boundaries"][i + 1],
                "label": result["labels"][i] if i < len(result["labels"]) else "unknown"
            })

    return {
        "sections": sections,
        "boundaries": result["boundaries"],
        "labels": result["labels"],
    }


class MSAFInput(BaseModel):
    audio_path: str = Field(..., description="音频文件的绝对路径")
    algorithm: Literal["scluster", "cnmf", "sf", "olda"] = Field(
        default="scluster",
        description="结构分割算法"
    )


msaf_analyze_tool = StructuredTool.from_function(
    coroutine=analyze_structure_msaf,
    name="msaf_analyze",
    description=(
        "使用 MSAF 框架分析音乐段落结构。支持多种算法（谱聚类、C-NMF 等），"
        "输出段落边界和聚类标签。"
    ),
    args_schema=MSAFInput,
)