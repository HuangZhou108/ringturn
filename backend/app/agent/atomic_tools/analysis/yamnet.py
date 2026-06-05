"""
YAMNet 音频分析原子工具

基于 Google YAMNet 模型进行音频分类，输出乐器、人声、风格等信息。
"""

import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.services.audio_models.yamnet_service import get_yamnet


class AnalyzeYamnetInput(BaseModel):
    """YAMNet 分析工具的输入参数"""
    audio_path: str = Field(..., description="音频文件的绝对路径")
    top_k: int = Field(default=10, description="返回前 k 个最高分标签（原始预测）", ge=1, le=50)
    instrument_threshold: float = Field(default=0.3, description="乐器检测的置信度阈值", ge=0.0, le=1.0)


async def analyze_yamnet(audio_path: str, top_k: int = 10, instrument_threshold: float = 0.3) -> Dict[str, Any]:
    """
    使用 YAMNet 分析音频文件，返回乐器、人声、风格等信息。

    该工具封装了 YAMNetService，提供统一的原子接口，可被 LLM 调用或在其他节点中复用。

    Args:
        audio_path: 音频文件路径
        top_k: 返回原始预测中前 k 个最高分标签
        instrument_threshold: 乐器检测的置信度阈值

    Returns:
        dict: 包含以下字段：
            - instruments: List[Dict[str, float]]，检测到的乐器及其置信度
            - has_vocal: bool，是否有人声
            - vocal_confidence: float，人声置信度
            - genre: str，推断的风格（pop/rock/classical/jazz/electronic/hiphop）
            - raw_predictions: List[Dict[str, float]]，前 top_k 个原始标签及分数
            - all_scores_summary: dict，包含所有 521 类的简要统计（可选）
    """
    # 1. 验证文件存在
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    # 2. 获取 YAMNet 服务实例（单例）
    yamnet = get_yamnet()

    # 3. 执行预测（返回 521 维分数向量）
    scores = yamnet.predict(audio_path)   # numpy array of shape (521,)

    # 4. 获取标签列表（缓存于服务中）
    labels = yamnet.labels   # List[str] of length 521

    # 5. 构建原始预测列表（前 top_k 个）
    import numpy as np
    top_indices = np.argsort(scores)[::-1][:top_k]
    raw_predictions = [
        {"label": labels[idx], "score": float(scores[idx])}
        for idx in top_indices if scores[idx] > 0.01
    ]

    # 6. 硬编码映射（与原有 node_yamnet 保持一致，但可配置阈值）
    instrument_map = {
        "Piano": "piano",
        "Guitar": "guitar",
        "Drum": "drums",
        "Bass": "bass",
        "Violin": "violin",
        "Cello": "cello",
        "Flute": "flute",
        "Saxophone": "saxophone",
        "Trumpet": "trumpet",
        "Synthesizer": "synthesizer",
        "Singing": "vocals",
    }

    instruments = []
    for yamnet_name, our_name in instrument_map.items():
        try:
            idx = labels.index(yamnet_name)
            prob = float(scores[idx])
            if prob > instrument_threshold:
                instruments.append({"name": our_name, "confidence": prob})
        except ValueError:
            continue

    # 7. 人声检测（从 Singing 标签获取）
    has_vocal = any(i["name"] == "vocals" for i in instruments)
    vocal_confidence = next((i["confidence"] for i in instruments if i["name"] == "vocals"), 0.0)

    # 8. 风格映射
    genre_map = {
        "Pop music": "pop",
        "Rock music": "rock",
        "Classical music": "classical",
        "Jazz": "jazz",
        "Electronic music": "electronic",
        "Hip hop music": "hiphop",
    }
    genre = "pop"   # 默认
    for yamnet_genre, our_genre in genre_map.items():
        try:
            idx = labels.index(yamnet_genre)
            if scores[idx] > 0.3:
                genre = our_genre
                break
        except ValueError:
            continue

    # 9. 可选：汇总所有分数的统计（用于调试或高级分析）
    all_scores_summary = {
        "mean": float(np.mean(scores)),
        "std": float(np.std(scores)),
        "max": float(np.max(scores)),
        "min": float(np.min(scores)),
    }

    return {
        "instruments": instruments,
        "has_vocal": has_vocal,
        "vocal_confidence": vocal_confidence,
        "genre": genre,
        "raw_predictions": raw_predictions,
        "all_scores_summary": all_scores_summary,
    }


# 创建 LangChain 工具实例
analyze_yamnet_tool = StructuredTool.from_function(
    coroutine=analyze_yamnet,
    name="analyze_yamnet",
    description=(
        "使用 YAMNet 模型分析音频文件，返回检测到的乐器列表、是否有人声、风格类别（pop/rock/classical/jazz/electronic/hiphop）"
        "以及原始分类标签。适用于获取音频的全局声学特征。"
    ),
    args_schema=AnalyzeYamnetInput,
)