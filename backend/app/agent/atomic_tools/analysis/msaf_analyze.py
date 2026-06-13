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
    # MSAF 内部会使用默认特征（PCP + MFCC 混合），无需手动指定特征提取器。
    # 如需自定义特征（如 'pcp'、'mfcc'）或算法（boundaries_id/labels_id），可参考官方文档：https://msaf.readthedocs.io/

    # 根据算法选择合适的边界检测器和标签分配器
    # 最佳实践组合：olda (边界) + scluster (标签)
    if algorithm == "scluster":
        boundaries, labels = msaf.process(
            audio_path,
            boundaries_id='olda',      # 高精度边界检测
            labels_id='scluster'       # 谱聚类标记段落
        )
    elif algorithm == "cnmf":
        boundaries, labels = msaf.process(
            audio_path,
            boundaries_id='cnmf',
            labels_id='cnmf'
        )
    elif algorithm == "sf":
        boundaries, labels = msaf.process(
            audio_path,
            boundaries_id='sf',
            labels_id='sf'
        )
    elif algorithm == "olda":
        boundaries, labels = msaf.process(
            audio_path,
            boundaries_id='olda',
            labels_id='scluster'       # olda 本身只做边界，标签仍用 scluster
        )
    else:
        # 降级：使用默认配置
        boundaries, labels = msaf.process(audio_path)

    # 转换为标准输出格式
    sections = []
    for i in range(len(boundaries) - 1):
        sections.append({
            "start": float(boundaries[i]),
            "end": float(boundaries[i + 1]),
            "label": labels[i] if i < len(labels) else "unknown"
        })

    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent.parent.parent
    estimation_path = project_root / "estimations"
    features_temp_file = project_root / ".features_msaf_tmp.json"

    import shutil
    if estimation_path.exists() and estimation_path.is_dir():
        shutil.rmtree(estimation_path)
        features_temp_file.unlink()
        print(f"已删除临时目录: {estimation_path.resolve()}, 临时输出文件: {features_temp_file.resolve()}")
    else:
        print(f"MSAF临时目录: {estimation_path}删除失败！")

    return {
        "sections": sections,
        "boundaries": [float(b) for b in boundaries],
        "labels": list(labels),
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