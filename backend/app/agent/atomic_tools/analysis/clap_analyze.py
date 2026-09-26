# backend/app/agent/atomic_tools/analysis/clap_analyze.py

"""
CLAP 音频理解原子工具

功能：
- 零样本音频分类（用户自定义标签列表）
- 支持流派、情感、乐器等多维度分类
- 无需训练，开箱即用
"""

import os
import contextlib
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
import numpy as np
from torch.nn.functional import cosine_similarity
from msclap import CLAP


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
    except Exception as e:
        import traceback
        print("=" * 50)
        print("导入 laion_clap 或 torch 时发生异常：")
        traceback.print_exc()
        print("异常详情：", repr(e))
        print("=" * 50)
        raise RuntimeError(f"CLAP 相关模块导入失败: {e}")

    # 你可以修改这个路径，例如指向你手动下载的文件夹
    local_cache_dir = Path(__file__).parent.parent.parent.parent.parent / "models" / "clap"
    local_cache_dir.mkdir(parents=True, exist_ok=True)

    # 构造权重文件路径
    ckpt_file = local_cache_dir / "630k-audioset-fusion-best.pt"
    if not ckpt_file.exists():
        raise RuntimeError(f"权重文件不存在: {ckpt_file}")

    # 让 laion_clap 优先使用这个目录
    # os.environ["LAION_CLAP_CACHE"] = str(local_cache_dir)

    model = laion_clap.CLAP_Module(enable_fusion=True)
    # load_ckpt 会自动检查 LAION_CLAP_CACHE 目录下是否有模型文件
    # 如果没有，则会下载到该目录
    with open(os.devnull, 'w') as devnull, contextlib.redirect_stdout(devnull):
        try:
            model.load_ckpt(ckpt=ckpt_file)
        except Exception as e:
            raise RuntimeError(f"CLAP 模型加载失败: {e}")
        
    # 加载音频
    audio_embed = model.get_audio_embedding_from_filelist([audio_path], use_tensor=True)

    result = {}

    if genre_labels:
        text_embeds = model.get_text_embedding(genre_labels, use_tensor=True)
        genre_sim = cosine_similarity(audio_embed, text_embeds)   
        # genre_sim = model.compute_similarity(audio_embed, genre_labels)
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
        text_embeds = model.get_text_embedding(emotion_labels, use_tensor=True)
        emotion_sim = cosine_similarity(audio_embed, text_embeds)   
        # emotion_sim = model.compute_similarity(audio_embed, emotion_labels)
        emotion_probs = torch.softmax(torch.tensor(emotion_sim), dim=0)
        best_idx = torch.argmax(emotion_probs).item()
        result["emotion"] = {
            "label": emotion_labels[best_idx],
            "confidence": float(emotion_probs[best_idx])
        }

    if instrument_labels:
        text_embeds = model.get_text_embedding(instrument_labels, use_tensor=True)
        instr_sim = cosine_similarity(audio_embed, text_embeds)   
        # instr_sim = model.compute_similarity(audio_embed, instrument_labels)
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

async def analyze_clap_caption(
    audio_path: str,
) -> Dict[str, Any]:
    """
    使用 msclap 的 clapcap 模型为音频生成描述性文本。
    完全零样本、零训练、零成本。
    """
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    # 1. 加载专门用于生成音频描述的 clapcap 模型
    # 设置 use_cuda=False 强制使用 CPU，符合你的要求
    model = CLAP(version='clapcap', use_cuda=False)

    # 2. 生成描述
    # generate_caption 方法接收一个文件路径列表，返回一个描述列表
    captions = model.generate_caption(audio_files=[audio_path])
    
    # 3. 提取生成的描述文本
    generated_caption = captions[0] if captions else "无法生成描述"

    # 4. 返回结果，保持原有数据结构以便于集成
    return {
        "caption": generated_caption,
        "model": "msclap/clapcap",
        "status": "success"
    }

# 更新输入参数，保留 audio_path 作为必填
class CLAPCaptionInput(BaseModel):
    audio_path: str = Field(..., description="音频文件的绝对路径")

# 创建新的 LangChain 工具
clap_caption_tool = StructuredTool.from_function(
    coroutine=analyze_clap_caption,
    name="clap_caption",
    description=(
        "使用微软 msclap 的 clapcap 模型为音频生成自然语言描述。"
        "完全零样本，无需任何训练。"
    ),
    args_schema=CLAPCaptionInput,
)

async def classify_task_type(
    audio_path: str,
    labels: List[str] = None,
) -> Dict[str, Any]:
    """
    使用 CLAP 对音频进行二分类：主旋律主导 vs 复杂配器。
    
    返回结果包含：
        - predicted_label: 预测的标签
        - confidence: 该标签的置信度
        - all_scores: 所有标签的得分
    """
    if labels is None:
        labels = ["simple melody dominant, one clear melody, few instruments, simple arrangement", "multiple overlapping melodies, many instruments, dense polyphonic texture"]
    
    # 复用已有的零样本分类逻辑，但直接计算所有标签的相似度
    try:
        import laion_clap
        import torch
    except Exception as e:
        raise RuntimeError(f"CLAP 相关模块导入失败: {e}")
    
    # 本地权重路径（与 analyze_clap_zero_shot 保持一致）
    local_cache_dir = Path(__file__).parent.parent.parent.parent.parent / "models" / "clap"
    local_cache_dir.mkdir(parents=True, exist_ok=True)
    ckpt_file = local_cache_dir / "630k-audioset-fusion-best.pt"
    if not ckpt_file.exists():
        raise RuntimeError(f"权重文件不存在: {ckpt_file}")
    
    model = laion_clap.CLAP_Module(enable_fusion=True)
    try:
        model.load_ckpt(ckpt=str(ckpt_file))
    except Exception as e:
        raise RuntimeError(f"CLAP 模型加载失败: {e}")
    model.eval()
    
    # 获取音频嵌入
    audio_embed = model.get_audio_embedding_from_filelist([audio_path], use_tensor=True)  # (1, embed_dim)
    
    # 获取文本嵌入
    text_embeds = model.get_text_embedding(labels, use_tensor=True)  # (n_labels, embed_dim)
    
    # 计算余弦相似度并确保维度正确
    from torch.nn.functional import cosine_similarity
    sim = cosine_similarity(audio_embed, text_embeds)  # 期望 (1, n_labels)
    
    # 防御：如果 sim 是 1 维，则添加 batch 维度
    if sim.dim() == 1:
        sim = sim.unsqueeze(0)
    
    probs = torch.softmax(sim, dim=1).squeeze(0)  # (n_labels,)
    
    best_idx = torch.argmax(probs).item()
    predicted_label = labels[best_idx]
    confidence = float(probs[best_idx])
    
    all_scores = {label: float(probs[i]) for i, label in enumerate(labels)}
    
    return {
        "predicted_label": predicted_label,
        "confidence": confidence,
        "all_scores": all_scores,
        "labels_used": labels,
    }

# ========== 新增二分类工具 ==========

async def classify_vocal_presence(
    audio_path: str,
    labels: List[str] = None,
) -> Dict[str, Any]:
    """
    使用 CLAP 进行人声二分类：有人声 vs 无人声。
    
    返回结果包含：
        - predicted_label: 预测的标签（"有清晰人声" / "无清晰人声"）
        - confidence: 该标签的置信度
        - all_scores: 所有标签的得分
    """
    if labels is None:
        labels = [
            "singing, vocals, human vocal, human voice",
            "no vocal, only instruments"
        ]
    return await asyncio.to_thread(_clap_binary_classify, audio_path, labels)


async def classify_piano_presence(
    audio_path: str,
    labels: List[str] = None,
) -> Dict[str, Any]:
    """
    使用 CLAP 进行钢琴重要旋律二分类：钢琴为主旋律 vs 钢琴不重要。
    
    返回结果包含：
        - predicted_label: 预测的标签（"钢琴为主旋律" / "钢琴不重要"）
        - confidence: 该标签的置信度
        - all_scores: 所有标签的得分
    """
    if labels is None:
        labels = [
            "prominent piano melody, piano is a main instrument, clear piano part",
            "no piano, or piano not important, piano is background or absent"
        ]
    return await asyncio.to_thread(_clap_binary_classify, audio_path, labels)


async def classify_guitar_presence(
    audio_path: str,
    labels: List[str] = None,
) -> Dict[str, Any]:
    """
    使用 CLAP 进行吉他重要旋律二分类：吉他为主旋律 vs 吉他不重要。
    
    返回结果包含：
        - predicted_label: 预测的标签（"吉他为主旋律" / "吉他不重要"）
        - confidence: 该标签的置信度
        - all_scores: 所有标签的得分
    """
    if labels is None:
        labels = [
            "prominent guitar melody, guitar is a main instrument, clear guitar part",
            "no guitar, or guitar not important, guitar is background or absent"
        ]
    return await asyncio.to_thread(_clap_binary_classify, audio_path, labels)


def _clap_binary_classify(audio_path: str, labels: List[str]) -> Dict[str, Any]:
    """
    内部通用二分类函数，复用模型加载和推理逻辑。
    （同步函数，调用方须用 asyncio.to_thread 在子线程执行，避免阻塞事件循环。）
    """
    try:
        import laion_clap
        import torch
    except ImportError as e:
        raise RuntimeError(f"CLAP 相关模块导入失败: {e}")
    
    # 本地权重路径（与原有函数保持一致）
    local_cache_dir = Path(__file__).parent.parent.parent.parent.parent / "models" / "clap"
    local_cache_dir.mkdir(parents=True, exist_ok=True)
    ckpt_file = local_cache_dir / "630k-audioset-fusion-best.pt"
    if not ckpt_file.exists():
        raise RuntimeError(f"权重文件不存在: {ckpt_file}")
    
    model = laion_clap.CLAP_Module(enable_fusion=True)
    with open(os.devnull, 'w') as devnull, contextlib.redirect_stdout(devnull):
        try:
            model.load_ckpt(ckpt=str(ckpt_file))
        except Exception as e:
            raise RuntimeError(f"CLAP 模型加载失败: {e}")
    model.eval()
    
    # 获取音频嵌入
    audio_embed = model.get_audio_embedding_from_filelist([audio_path], use_tensor=True)  # (1, embed_dim)
    
    # 获取文本嵌入
    text_embeds = model.get_text_embedding(labels, use_tensor=True)  # (n_labels, embed_dim)
    
    # 计算余弦相似度
    from torch.nn.functional import cosine_similarity
    sim = cosine_similarity(audio_embed, text_embeds)  # (1, n_labels)
    if sim.dim() == 1:
        sim = sim.unsqueeze(0)
    
    probs = torch.softmax(sim, dim=1).squeeze(0)  # (n_labels,)
    best_idx = torch.argmax(probs).item()
    predicted_label = labels[best_idx]
    confidence = float(probs[best_idx])
    
    all_scores = {label: float(probs[i]) for i, label in enumerate(labels)}
    
    return {
        "predicted_label": predicted_label,
        "confidence": confidence,
        "all_scores": all_scores,
        "labels_used": labels,
    }