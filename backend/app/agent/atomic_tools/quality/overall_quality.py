# app/agent/atomic_tools/quality/overall_quality.py
from .loudness_check import check_loudness
from .spectral_balance import check_spectral_balance
from .dynamic_range import check_dynamic_range
from .zero_crossing_rate import get_zero_crossing_rate
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]


def _musicality_metrics(melody_notes, key_midi, mode):
    """
    从旋律音符计算音乐性指标，返回 (score, issues, metrics)。

    维度：
    - 相邻音高跳变（大步跳 > 7 半音的占比）
    - 离调率（不在调内音阶的音符占比）
    - 音符密度（个/秒）
    - 短碎音符占比（< 0.1 秒）
    """
    if not melody_notes:
        return 4.0, [], {}

    notes = sorted(melody_notes, key=lambda n: n["start"])
    pitches = [int(n["pitch"]) for n in notes]

    intervals = [abs(pitches[i] - pitches[i - 1]) for i in range(1, len(pitches))]
    large_jump_ratio = sum(1 for iv in intervals if iv > 7) / len(intervals) if intervals else 0.0

    out_of_key_ratio = 0.0
    if key_midi is not None:
        scale_pcs = set((int(key_midi) + iv) % 12 for iv in (MINOR if mode == "minor" else MAJOR))
        out_of_key_ratio = sum(1 for p in pitches if p % 12 not in scale_pcs) / len(pitches)

    duration = notes[-1]["end"] - notes[0]["start"]
    note_density = len(notes) / duration if duration > 0 else 0.0

    short_note_ratio = sum(1 for n in notes if (n["end"] - n["start"]) < 0.1) / len(notes)

    issues = []
    if large_jump_ratio > 0.3:
        issues.append("旋律音高跳变过多")
    if out_of_key_ratio > 0.3:
        issues.append("离调音符偏多")
    if note_density > 15:
        issues.append("音符过于密集")
    if short_note_ratio > 0.4:
        issues.append("短碎音符偏多")

    score = max(1.0, 5.0 - len(issues) * 0.5)
    metrics = {
        "large_jump_ratio": round(large_jump_ratio, 3),
        "out_of_key_ratio": round(out_of_key_ratio, 3),
        "note_density": round(note_density, 2),
        "short_note_ratio": round(short_note_ratio, 3),
    }
    return round(score, 2), issues, metrics


async def evaluate_overall_quality(
    audio_path: str,
    melody_notes: Optional[List[Dict[str, Any]]] = None,
    key_midi: Optional[int] = None,
    mode: str = "major",
) -> dict:
    """
    聚合音频工程指标 + 音乐性指标，返回总分及问题列表。

    - 工程指标：响度 / 频谱平衡 / 动态范围 / 过零率（基于渲染音频）
    - 音乐性：音高跳变 / 离调率 / 音符密度 / 短碎音（基于旋律音符，可选）
    """
    loud = await check_loudness(audio_path)
    spectral = await check_spectral_balance(audio_path)
    dr = await check_dynamic_range(audio_path)
    zcr = await get_zero_crossing_rate(audio_path)

    issues = []
    if loud["is_too_quiet"]:
        issues.append("音频过轻")
    if loud["is_clipped"]:
        issues.append("音频可能过载")
    if spectral["low_freq_heavy"]:
        issues.append("低频过重，可能浑浊")
    if spectral["high_freq_harsh"]:
        issues.append("高频过重，可能刺耳")
    if dr["is_narrow"]:
        issues.append("动态范围不足，声音平板")
    if zcr > 0.3:
        issues.append("可能存在噪声或削波")

    audio_score = max(1.0, min(5.0, 4.0 - len(issues) * 0.5))

    # 音乐性评估
    mus_score, mus_issues, mus_metrics = _musicality_metrics(melody_notes, key_midi, mode)
    issues = issues + mus_issues

    overall = round((audio_score + mus_score) / 2, 2)

    return {
        "overall_score": overall,
        "naturalness": round(audio_score, 2),
        "musicality": mus_score,
        "clarity": round(audio_score, 2),
        "quality_issues": issues,
        "musicality_metrics": mus_metrics,
        "passed": overall >= 3.5 and len(issues) == 0,
    }


class EvaluateOverallQualityInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")
    melody_notes: Optional[List[Dict[str, Any]]] = Field(default=None, description="旋律音符列表（可选，用于音乐性评估）")
    key_midi: Optional[int] = Field(default=None, description="调性根音 MIDI（可选）")
    mode: str = Field(default="major", description="调式：major 或 minor")


evaluate_overall_quality_tool = StructuredTool.from_function(
    coroutine=evaluate_overall_quality,
    name="evaluate_overall_quality",
    description="综合评估音频质量（工程指标 + 音乐性指标），返回总分（1-5）、问题列表以及是否通过。",
    args_schema=EvaluateOverallQualityInput,
)
