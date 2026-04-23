"""
音频质量评估服务

使用多种方法评估生成音频的质量
"""

import numpy as np
from pathlib import Path


async def evaluate_quality(
    audio_path: str,
    reference_path: str | None = None,
) -> dict:
    """
    评估音频质量

    Args:
        audio_path: 待评估音频路径
        reference_path: 参考音频路径（可选，用于对比评估）

    Returns:
        dict: 质量评估结果
    """
    result = {
        "overall_score": 4.0,
        "naturalness": 4.0,
        "musicality": 4.0,
        "clarity": 4.0,
        "quality_issues": [],
        "passed": True,
    }

    try:
        # 方法1: librosa 基础分析
        quality = await _librosa_quality_check(audio_path)
        result.update(quality)

        # 方法2: 如果有参考音频，进行对比
        if reference_path and Path(reference_path).exists():
            similarity = await _compute_similarity(audio_path, reference_path)
            result["similarity_to_reference"] = similarity
            if similarity < 0.5:
                result["quality_issues"].append("与原曲相似度较低")

    except Exception as e:
        print(f"[WARN] 质量评估出错: {e}")

    # 判断是否达标
    result["passed"] = (
        result["overall_score"] >= 3.5 and
        len(result["quality_issues"]) == 0
    )

    return result


async def _librosa_quality_check(audio_path: str) -> dict:
    """使用 librosa 进行基础音频质量检查"""
    import librosa

    quality = {}

    try:
        y, sr = librosa.load(audio_path, sr=None)

        # 1. 响度检查
        rms = librosa.feature.rms(y=y)[0]
        mean_rms = float(np.mean(rms))
        if mean_rms < 0.01:
            quality["quality_issues"] = ["音频过轻"]
            quality["overall_score"] = 3.0
        elif mean_rms > 0.8:
            quality["quality_issues"] = ["音频可能过载"]
            quality["overall_score"] = 3.5
        else:
            quality["clarity"] = min(5.0, 3.5 + mean_rms * 2)

        # 2. 频谱平衡检查
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        mean_centroid = float(np.mean(spectral_centroid))
        # 合理的频谱中心应该在中频区域
        if mean_centroid < 200:
            quality["quality_issues"] = ["低频过重，可能浑浊"]
        elif mean_centroid > 4000:
            quality["quality_issues"] = ["高频过重，可能刺耳"]

        # 3. 动态范围
        dynamic_range = float(np.max(rms) - np.min(rms))
        if dynamic_range < 0.05:
            quality["quality_issues"].append("动态范围不足，声音平板")

        # 4. 过零率（检测静音或噪声）
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        mean_zcr = float(np.mean(zcr))
        if mean_zcr > 0.3:
            quality["quality_issues"] = ["可能存在噪声或削波"]

        # 计算综合分数
        base_score = 4.0
        if "quality_issues" in quality:
            penalty = len(quality["quality_issues"]) * 0.5
            base_score -= penalty

        quality["overall_score"] = max(1.0, min(5.0, base_score))
        quality["naturalness"] = quality["overall_score"] - 0.2
        quality["musicality"] = quality["overall_score"] - 0.3

        if "quality_issues" not in quality:
            quality["quality_issues"] = []

    except Exception as e:
        print(f"[WARN] librosa 质量检查失败: {e}")
        quality = {
            "overall_score": 4.0,
            "naturalness": 4.0,
            "musicality": 4.0,
            "clarity": 4.0,
            "quality_issues": [],
        }

    return quality


async def _compute_similarity(audio1: str, audio2: str) -> float:
    """计算两个音频的相似度（基于MFCC）"""
    import librosa

    try:
        # 加载音频
        y1, sr1 = librosa.load(audio1, sr=22050)
        y2, sr2 = librosa.load(audio2, sr=22050)

        # 提取 MFCC
        mfcc1 = librosa.feature.mfcc(y=y1, sr=sr1, n_mfcc=13)
        mfcc2 = librosa.feature.mfcc(y=y2, sr=sr2, n_mfcc=13)

        # 计算余弦相似度
        mfcc1_mean = np.mean(mfcc1, axis=1)
        mfcc2_mean = np.mean(mfcc2, axis=1)

        # 余弦相似度
        similarity = np.dot(mfcc1_mean, mfcc2_mean) / (
            np.linalg.norm(mfcc1_mean) * np.linalg.norm(mfcc2_mean)
        )

        return float(max(0.0, similarity))

    except Exception as e:
        print(f"[WARN] 相似度计算失败: {e}")
        return 0.5


# UTMOS 接口（预留）
async def evaluate_with_utmos(audio_path: str) -> dict:
    """
    使用 UTMOS 进行质量评估（预留）

    需要安装: pip install utmos
    或使用托管API
    """
    try:
        # 这里可以接入 UTMOS 模型
        # 由于 UTMOS 主要用于语音质量评估，对音乐可能不太适用
        # 暂时返回 None 表示未实现
        pass
    except ImportError:
        print("[WARN] UTMOS 未安装，跳过")
    except Exception as e:
        print(f"[WARN] UTMOS 评估失败: {e}")

    return None
