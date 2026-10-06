# backend/app/agent/atomic_tools/analysis/zerauCap_tool.py
"""
ZerAuCap: 零样本音频描述生成工具

基于 laion_clap + MTG-Jamendo 195 个专业标签集 + 本地 GLM 模型。
支持可选的长音频切割与关键词融合，完全零样本、零训练、零费用。
"""

import os
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import urllib.request
import numpy as np
import librosa

# CLAP 相关
import torch
from laion_clap import CLAP_Module

# 项目内部
from app.services.llm_service import llm_service

# 配置文件
from app.core.config import get_settings
settings = get_settings()

# 标签集 URL (MTG-Jamendo 195 标签)
MTG_TAGS_URL = "https://raw.githubusercontent.com/MTG/mtg-jamendo-dataset/master/data/autotagging.tsv"
TAGS_CACHE_FILE = Path(settings.STATIC_DIR) / "models" / "autotagging_top50tags.tsv"

# 默认参数
DEFAULT_TOP_K = 10
DEFAULT_CHUNK_DURATION = 10.0   # 秒
DEFAULT_SAMPLE_RATE = 48000     # CLAP 期望采样率


def _ensure_tags_file() -> List[str]:
    """确保标签文件存在，必要时下载并解析。返回标签列表。"""
    # 打印缓存路径
    print(f"[ZerAuCap] 标签缓存路径: {TAGS_CACHE_FILE.absolute()}")
    
    # 检查缓存文件
    if TAGS_CACHE_FILE.exists():
        with open(TAGS_CACHE_FILE, "r", encoding="utf-8") as f:
            tags = [line.strip() for line in f if line.strip()]
            if tags:
                print(f"[ZerAuCap] 从缓存加载 {len(tags)} 个标签")
                return tags

    # 定义搜索路径（打印每个路径）
    search_paths = [
        Path(settings.STATIC_DIR) / "data" / "autotagging.tsv",
        Path(settings.STATIC_DIR) / "data" / "autotagging_top50tags.tsv",
    ]
    for local_path in search_paths:
        if local_path.exists():
            print(f"[ZerAuCap] 使用本地文件: {local_path}")
            # 读取 TSV 文件，跳过表头，取除第一列外的所有列名
            try:
                import pandas as pd
                df = pd.read_csv(local_path, sep='\t')
                tags = list(df.columns[1:])
                # 保存到缓存文件
                with open(TAGS_CACHE_FILE, "w", encoding="utf-8") as f:
                    for tag in tags:
                        f.write(tag + "\n")
                print(f"[ZerAuCap] 已从本地文件加载 {len(tags)} 个标签")
                return tags
            except Exception as e:
                print(f"[ZerAuCap] 读取本地文件失败: {e}")
                continue

    # 尝试从网络下载（优先使用 top50 文件，更小）
    top50_url = "https://raw.githubusercontent.com/MTG/mtg-jamendo-dataset/master/data/autotagging_top50tags.tsv"
    full_url = MTG_TAGS_URL
    for url in (top50_url, full_url):
        print(f"[ZerAuCap] 尝试从网络下载: {url}")
        TAGS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = TAGS_CACHE_FILE.with_suffix(".tsv.tmp")
        try:
            urllib.request.urlretrieve(url, tmp_file)
            file_size = tmp_file.stat().st_size
            print(f"[ZerAuCap] 下载完成，大小: {file_size} 字节")
            # 检查内容是否以 track_id 开头（简单验证）
            with open(tmp_file, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
            if not first_line.startswith("track_id"):
                print(f"[ZerAuCap] 下载内容异常，首行: {first_line[:100]}")
                continue  # 尝试下一个 URL
        except Exception as e:
            print(f"[ZerAuCap] 下载失败: {e}")
            continue

        # 解析 TSV
        tags = []
        try:
            import pandas as pd
            df = pd.read_csv(tmp_file, sep='\t')
            if 'track_id' in df.columns:
                tags = list(df.columns[1:])
            else:
                tags = list(df.columns)
            print(f"[ZerAuCap] 解析到 {len(tags)} 个标签列")
        except ImportError:
            print("[ZerAuCap] pandas 未安装，使用手动解析")
            with open(tmp_file, "r", encoding="utf-8") as f:
                header = f.readline().strip()
                parts = header.split('\t')
                tags = parts[1:]
        except Exception as e:
            print(f"[ZerAuCap] 解析失败: {e}")
            continue
        finally:
            if tmp_file.exists():
                tmp_file.unlink()
        
        if tags:
            # 保存到缓存
            with open(TAGS_CACHE_FILE, "w", encoding="utf-8") as f:
                for tag in tags:
                    f.write(tag + "\n")
            print(f"[ZerAuCap] 已加载 {len(tags)} 个标签")
            return tags

    # 所有方法都失败，使用内置的 50 个常用标签（确保工具可用）
    fallback_tags = [
        "rock", "pop", "electronic", "hip hop", "jazz", "classical", "blues", "country", "folk", "metal",
        "punk", "reggae", "soul", "funk", "disco", "house", "techno", "trance", "drum and bass", "ambient",
        "piano", "guitar", "drums", "bass", "violin", "cello", "flute", "saxophone", "trumpet", "voice",
        "happy", "sad", "energetic", "calm", "romantic", "dark", "bright", "aggressive", "relaxing", "melancholic",
        "fast", "slow", "dance", "party", "love", "angry", "hopeful", "mysterious", "epic", "funny"
    ]
    print(f"[ZerAuCap] 使用内置 fallback 标签集: {len(fallback_tags)} 个标签")
    # 也将 fallback 保存到缓存，以便下次直接使用
    with open(TAGS_CACHE_FILE, "w", encoding="utf-8") as f:
        for tag in fallback_tags:
            f.write(tag + "\n")
    return fallback_tags

class ZerAuCap:
    """零样本音频描述生成器（单例模式，复用 CLAP 模型）"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.tags = _ensure_tags_file()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self._load_clap_model()
        # 构建文本嵌入（无梯度）
        with torch.no_grad():
            text_embeds_list = []
            for tag in self.tags:
                text_embed = self.model.get_text_embedding([tag], use_tensor=True)
                text_embeds_list.append(text_embed)
            self.text_embeds = torch.cat(text_embeds_list, dim=0)  # (N_tags, embed_dim)
        self._initialized = True

    def _load_clap_model(self):
        """加载 laion_clap 模型（使用预训练权重，自动下载）"""
        print("[ZerAuCap] 加载 laion_clap 模型...")
        # 打印 HuggingFace 缓存路径
        import huggingface_hub
        cache_dir = huggingface_hub.constants.HF_HUB_CACHE
        print(f"[ZerAuCap] HuggingFace 缓存目录: {cache_dir}")
        
        # 定义本地权重路径（与 clap_analyze.py 保持一致）
        local_cache_dir = Path(__file__).parent.parent.parent.parent.parent / "models" / "clap"
        local_cache_dir.mkdir(parents=True, exist_ok=True)
        ckpt_file = local_cache_dir / "630k-audioset-fusion-best.pt"

        self.model = CLAP_Module(enable_fusion=True)
        try:
            # 尝试加载模型（自动下载）
            self.model.load_ckpt(ckpt=str(ckpt_file))
        except Exception as e:
            # 捕获并给出更详细的错误信息
            error_msg = str(e)
            if "roberta-base" in error_msg and "TensorFlow" in error_msg:
                print("[ZerAuCap] 模型缓存可能损坏，建议执行以下命令修复：")
                print("    rm -rf ~/.cache/huggingface/hub/models--roberta-base")
                print("然后重新运行。")
            raise RuntimeError(f"CLAP 模型加载失败: {error_msg}")
        self.model.eval()
        print("[ZerAuCap] CLAP 模型加载完成")

    async def _extract_keywords_single(
        self,
        audio_path: str,
        start_sec: float = 0.0,
        end_sec: float = None,
        top_k: int = DEFAULT_TOP_K
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """
        从单个音频片段（或完整文件）中提取关键词。

        返回:
            keywords: 列表，每个元素 {"keyword": str, "confidence": float}
            all_scores: 字典 {keyword: confidence}
        """
        # 1. 加载音频片段
        try:
            # 加载指定区间，保证采样率为 48000（CLAP 所需）
            y, sr = librosa.load(
                audio_path,
                sr=DEFAULT_SAMPLE_RATE,
                mono=True,
                offset=start_sec,
                duration=(end_sec - start_sec) if end_sec is not None else None
            )
            if y is None or len(y) == 0:
                raise ValueError("音频片段为空")
        except Exception as e:
            raise RuntimeError(f"加载音频片段失败 [{start_sec:.1f}s - {end_sec if end_sec else 'end'}]: {e}")

        # 2. 转换为张量并获取音频嵌入
        audio_tensor = torch.from_numpy(y).float().unsqueeze(0).to(self.device)
        with torch.no_grad():
            audio_embed = self.model.get_audio_embedding_from_data(
                audio_tensor, use_tensor=True
            )  # shape: (1, embed_dim)

        # 3. 计算余弦相似度（无需梯度的张量）
        sim = torch.matmul(audio_embed, self.text_embeds.T).squeeze(0).detach()
        probs = torch.softmax(sim, dim=0).cpu().numpy()

        # 4. 获取文本嵌入（所有标签）
        # 批量计算（避免重复计算，但标签数量固定，可以缓存）
        if not hasattr(self, "text_embeds"):
            text_embeds_list = []
            for tag in self.tags:
                # 简单文本格式化: 保留原始标签，不加修饰
                text_embed = self.model.get_text_embedding([tag], use_tensor=True)
                text_embeds_list.append(text_embed)
            self.text_embeds = torch.cat(text_embeds_list, dim=0)  # (N_tags, embed_dim)

        # # 计算余弦相似度
        # sim = torch.matmul(audio_embed, self.text_embeds.T).squeeze(0)  # (N_tags,)
        # probs = torch.softmax(sim, dim=0).cpu().numpy()

        # 5. 取 top_k
        top_indices = np.argsort(probs)[::-1][:top_k]
        keywords = []
        all_scores = {}
        for idx in top_indices:
            kw = self.tags[idx]
            score = float(probs[idx])
            keywords.append({"keyword": kw, "confidence": score})
            all_scores[kw] = score

        return keywords, all_scores

    async def _extract_keywords_full(
        self,
        audio_path: str,
        top_k: int = DEFAULT_TOP_K
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """不切割，直接对整个音频提取关键词"""
        return await self._extract_keywords_single(audio_path, top_k=top_k)

    async def _extract_keywords_chunked(
        self,
        audio_path: str,
        chunk_duration: float = DEFAULT_CHUNK_DURATION,
        top_k: int = DEFAULT_TOP_K,
        use_time_weight: bool = True
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float], int]:
        """
        切割音频并提取关键词，融合所有片段的结果。

        返回:
            keywords: 融合后的 top_k 关键词
            all_scores: 所有关键词的融合分数
            chunks_processed: 成功处理的片段数
        """
        # 获取总时长
        try:
            duration = librosa.get_duration(filename=audio_path)
        except Exception as e:
            raise RuntimeError(f"无法获取音频时长: {e}")

        if duration <= chunk_duration:
            # 无需切割
            kw, scores = await self._extract_keywords_full(audio_path, top_k=top_k)
            return kw, scores, 1

        # 计算片段数
        num_chunks = int(np.ceil(duration / chunk_duration))
        aggregated_scores = {}   # keyword -> total_weighted_score
        total_weights = 0.0
        chunks_ok = 0

        for i in range(num_chunks):
            start = i * chunk_duration
            end = min(start + chunk_duration, duration)
            if end - start < 0.5:  # 太短的片段跳过
                continue
            try:
                _, scores = await self._extract_keywords_single(
                    audio_path, start, end, top_k=top_k
                )
                # 权重：时间靠后的片段权重略高（线性递增）
                weight = (i + 1) / num_chunks if use_time_weight else 1.0
                for kw, conf in scores.items():
                    aggregated_scores[kw] = aggregated_scores.get(kw, 0.0) + conf * weight
                total_weights += weight
                chunks_ok += 1
            except Exception as e:
                print(f"[ZerAuCap] 片段 {i+1} 处理失败: {e}")
                continue

        if chunks_ok == 0:
            # 全部失败，回退到不切割
            print("[ZerAuCap] 所有片段处理失败，回退到不切割")
            return await self._extract_keywords_full(audio_path, top_k=top_k) + (0,)

        # 归一化
        for kw in aggregated_scores:
            aggregated_scores[kw] /= total_weights

        # 排序并取 top_k
        sorted_items = sorted(aggregated_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        keywords = [{"keyword": kw, "confidence": score} for kw, score in sorted_items]
        return keywords, aggregated_scores, chunks_ok

    async def generate_caption(
        self,
        keywords: List[Dict[str, Any]],
        lang: str = "zh"
    ) -> str:
        """调用 LLM 生成自然语言描述"""
        if not keywords:
            return "无法从音频中提取有效特征。"

        # 构建关键词列表字符串（只取关键词名，不含置信度）
        kw_list = ", ".join([item["keyword"] for item in keywords])

        # 根据语言选择 prompt
        if lang == "zh":
            prompt = f"""你是一个音乐描述专家。根据以下检测到的声音关键词（按置信度降序），生成一句流畅、详细的中文描述。
关键词：{kw_list}
描述中应包含音乐类型、主要乐器、节奏感、情绪氛围。
描述："""
        else:
            prompt = f"""You are a music description expert. Based on the following audio keywords (in descending confidence), generate a fluent and detailed English description.
Keywords: {kw_list}
The description should include music genre, main instruments, rhythmic feel, and emotional atmosphere.
Description:"""

        messages = [{"role": "user", "content": prompt}]
        try:
            # 使用项目中已有的 LLM 服务（GLM 模型）
            caption = await llm_service.chat(
                messages,
                temperature=0.6,
                max_tokens=150
            )
            # 清理可能的引号或多余换行
            caption = caption.strip().strip('"')
            return caption
        except Exception as e:
            print(f"[ZerAuCap] LLM 调用失败: {e}")
            return f"检测到关键词: {kw_list}"


# 全局单例
_zerau_cap = None

def get_zerau_cap() -> ZerAuCap:
    global _zerau_cap
    if _zerau_cap is None:
        _zerau_cap = ZerAuCap()
    return _zerau_cap


async def generate_audio_caption(
    audio_path: str,
    use_chunking: bool = False,
    chunk_duration: float = DEFAULT_CHUNK_DURATION,
    top_k: int = DEFAULT_TOP_K,
    use_time_weight: bool = True,
    language: str = "zh"
) -> Dict[str, Any]:
    """
    主函数：生成音频的自然语言描述及关键词。

    Args:
        audio_path: 音频文件路径
        use_chunking: 是否启用长音频切割（超过 chunk_duration 时自动切分）
        chunk_duration: 片段时长（秒），默认 10 秒
        top_k: 返回的关键词数量
        use_time_weight: 切割时是否启用时间加权（靠后片段权重略高）
        language: 描述语言 ("zh" 或 "en")

    Returns:
        dict: {
            "caption": str,
            "keywords": List[{"keyword": str, "confidence": float}],
            "used_labelset": str,
            "chunks_processed": int,   # 如果 use_chunking=False，则为 1
            "success": bool,
            "error": str | None
        }
    """
    if not os.path.exists(audio_path):
        return {
            "caption": "",
            "keywords": [],
            "used_labelset": "MTG-Jamendo 195",
            "chunks_processed": 0,
            "success": False,
            "error": f"文件不存在: {audio_path}"
        }

    try:
        zerau = get_zerau_cap()

        if use_chunking:
            keywords, all_scores, chunks = await zerau._extract_keywords_chunked(
                audio_path,
                chunk_duration=chunk_duration,
                top_k=top_k,
                use_time_weight=use_time_weight
            )
        else:
            keywords, all_scores = await zerau._extract_keywords_full(
                audio_path, top_k=top_k
            )
            chunks = 1

        # 生成自然语言描述
        caption = await zerau.generate_caption(keywords, lang=language)

        return {
            "caption": caption,
            "keywords": keywords,
            "used_labelset": "MTG-Jamendo 195",
            "chunks_processed": chunks,
            "success": True,
            "error": None
        }

    except Exception as e:
        return {
            "caption": "",
            "keywords": [],
            "used_labelset": "MTG-Jamendo 195",
            "chunks_processed": 0,
            "success": False,
            "error": str(e)
        }
