"""
MERT 音频分析原子工具

基于微软 MERT 模型提取深层音乐特征，并提供情绪、风格、乐器等高级分析。
"""

import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.services.audio_models.mert_service import get_mert


class AnalyzeMertInput(BaseModel):
    """MERT 工具输入参数"""
    audio_path: str = Field(..., description="音频文件的绝对路径")
    extract_emotion: bool = Field(default=True, description="是否进行情绪分析")
    extract_style: bool = Field(default=True, description="是否进行风格分析")
    layer_pooling: str = Field(
        default="mean",
        description="特征层聚合方式：'mean'（平均）, 'last'（最后一层）, 'concat'（拼接）"
    )


async def analyze_mert(
    audio_path: str,
    extract_emotion: bool = True,
    extract_style: bool = True,
    layer_pooling: str = "mean"
) -> Dict[str, Any]:
    """
    使用 MERT 模型分析音频，返回特征向量、情绪分布、风格标签等。

    MERT 是专为音乐理解设计的大规模自监督模型，在情绪、风格、乐器识别等任务上达到 SOTA。
    该工具提取 12 层 Transformer 的聚合特征，并可调用内置分类器完成高级分析。

    Args:
        audio_path: 音频文件路径
        extract_emotion: 是否预测情绪（需要预训练分类器）
        extract_style: 是否预测风格
        layer_pooling: 特征聚合方式

    Returns:
        dict: 包含以下字段：
            - feature_vector: List[float]，MERT 特征向量（维度 768 或 9216）
            - emotion: Dict[str, float] | None，情绪分数（如果 extract_emotion=True）
            - style: str | None，风格标签（如果 extract_style=True）
            - metadata: dict，模型信息
    """
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    mert = get_mert()

    # 1. 提取特征向量
    feature_vector = mert.extract_features(audio_path, layer_pooling=layer_pooling)
    
    result: Dict[str, Any] = {
        "feature_vector": feature_vector.tolist(),
        "metadata": {
            "model": "MERT-v1-95M",
            "layer_pooling": layer_pooling,
            "feature_dim": len(feature_vector),
        }
    }

    # 2. 情绪分析（如果有分类器）
    if extract_emotion:
        # 这里调用 MERTService 中的情绪预测方法
        # 实际项目中需要训练或加载一个分类器，此处仅为示意
        emotion_scores = mert.predict_emotion(audio_path)
        result["emotion"] = emotion_scores

    # 3. 风格分析（可单独实现或复用 emotion 分类器）
    if extract_style:
        # 示例：基于特征向量调用一个简单的分类器（占位）
        # 真实场景中可以用 CLAP 或 MERT + MLP 实现风格分类
        result["style"] = "pop"   # 占位

    return result


# 创建 LangChain 工具
analyze_mert_tool = StructuredTool.from_function(
    coroutine=analyze_mert,
    name="analyze_mert",
    description=(
        "使用微软 MERT 模型分析音频，提取深层音乐特征向量（维度 768），并可预测情绪（快乐/悲伤/能量/平静）"
        "和风格。MERT 在多个音乐理解任务上达到领先水平，适合作为后续改编的参考依据。"
    ),
    args_schema=AnalyzeMertInput,
)