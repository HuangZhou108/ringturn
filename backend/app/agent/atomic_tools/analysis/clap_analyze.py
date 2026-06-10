# backend/app/agent/atomic_tools/analysis/clap_analyze.py

"""
CLAP 音频理解原子工具

功能：
- 零样本音频分类（用户自定义标签列表）
- 支持流派、情感、乐器等多维度分类
- 无需训练，开箱即用
"""

from pathlib import Path
from typing import Dict, Any, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
import numpy as np


async def analyze_clap_zero_shot(
    audio_path: str,
    genre_labels: List[str] = None,
    emotion_labels: List[str] = None,
    instrument_labels: List[str] = None
) -> Dict[str, Any]:
    """
    使用 CLAP 进行零样本音频分类。

    CLAP (Contrastive Language-Audio Pretraining) 是 LAION 开源的音频-文本对比学习模型，
    支持零样本分类，用户只需提供候选标签列表，无需训练。

    Args:
        audio_path: 输入音频文件的绝对路径
        genre_labels: 流派标签列表
        emotion_labels: 情感标签列表
        instrument_labels: 乐器标签列表

    Returns:
        dict: 包含以下字段
            - genre: 最匹配的流派及置信度
            - emotion: 最匹配的情感及置信度
            - instrument: 最匹配的乐器及置信度
            - all_scores: 所有候选标签的分数详情
    """
    try:
        import laion_clap
        import torch
    except ImportError:
        raise RuntimeError(
            "CLAP not found. Please install with: "
            "git clone https://github.com/LAION-AI/CLAP && cd CLAP && pip install -e ."
        )

    model = laion_clap.CLAP_Module(enable_fusion=False)
    model.load_ckpt()

    # 加载音频
    audio_data = model.load_audio(audio_path, sr=48000)

    result = {}

    if genre_labels:
        genre_sim = model.compute_similarity(audio_data, genre_labels)
        genre_probs = torch.softmax(torch.tensor(genre_sim), dim=0)
        best_idx = torch.argmax(genre_probs).item()
        result["genre"] = {
            "label": genre_labels[best_idx],
            "confidence": float(genre_probs[best_idx])
        }
        result["genre_all_scores"] = {
            label: float(score) for label, score in zip(genre_labels, genre_probs.tolist())
        }

    if emotion_labels:
        emotion_sim = model.compute_similarity(audio_data, emotion_labels)
        emotion_probs = torch.softmax(torch.tensor(emotion_sim), dim=0)
        best_idx = torch.argmax(emotion_probs).item()
        result["emotion"] = {
            "label": emotion_labels[best_idx],
            "confidence": float(emotion_probs[best_idx])
        }

    if instrument_labels:
        instr_sim = model.compute_similarity(audio_data, instrument_labels)
        instr_probs = torch.softmax(torch.tensor(instr_sim), dim=0)
        best_idx = torch.argmax(instr_probs).item()
        result["instrument"] = {
            "label": instrument_labels[best_idx],
            "confidence": float(instr_probs[best_idx])
        }

    return result


class CLAPInput(BaseModel):
    audio_path: str = Field(..., description="音频文件的绝对路径")
    genre_labels: List[str] = Field(
        default=["pop", "rock", "jazz", "classical", "electronic", "hip hop"],
        description="流派标签列表"
    )
    emotion_labels: List[str] = Field(
        default=["happy", "sad", "energetic", "calm", "angry"],
        description="情感标签列表"
    )
    instrument_labels: List[str] = Field(
        default=["piano", "guitar", "violin", "drums", "bass", "vocals"],
        description="乐器标签列表"
    )


clap_analyze_tool = StructuredTool.from_function(
    coroutine=analyze_clap_zero_shot,
    name="clap_analyze",
    description=(
        "使用 CLAP 进行零样本音频分析。用户自定义标签列表（流派、情感、乐器等），"
        "CLAP 会自动计算音频与每个标签的相似度，无需训练。"
        "这是替代 MERT 的最佳选择，适合无法训练分类器的场景。"
    ),
    args_schema=CLAPInput,
)