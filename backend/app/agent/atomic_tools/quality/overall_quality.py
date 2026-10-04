# app/agent/atomic_tools/quality/overall_quality.py
from .loudness_check import check_loudness
from .spectral_balance import check_spectral_balance
from .dynamic_range import check_dynamic_range
from .zero_crossing_rate import get_zero_crossing_rate
from .melody_quality import REPORT_VERSION, evaluate_melody_quality
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]


def _musicality_metrics(melody_notes, key_midi, mode, melody_quality_report=None):
    """
    从旋律音符计算音乐性指标，返回 (score, issues, metrics, report)。

    复用提取阶段的版本化旋律质量报告，并补充调内音比例。
    """
    if melody_notes is None:
        return 4.0, [], {}, None

    required_report_keys = {"score", "passed", "issues", "metrics"}
    if (
        isinstance(melody_quality_report, dict)
        and required_report_keys.issubset(melody_quality_report)
        and melody_quality_report.get("version") == REPORT_VERSION
    ):
        melody_report = melody_quality_report
    else:
        melody_report = evaluate_melody_quality(melody_notes)
    metrics = dict(melody_report["metrics"])
    pitches = []
    for note in melody_notes:
        try:
            pitch = int(note["pitch"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= pitch <= 127:
            pitches.append(pitch)

    out_of_key_ratio = 0.0
    if key_midi is not None and pitches:
        scale = MINOR if mode == "minor" else MAJOR
        scale_pcs = {(int(key_midi) + interval) % 12 for interval in scale}
        out_of_key_ratio = sum(1 for p in pitches if p % 12 not in scale_pcs) / len(pitches)

    issues = [issue["message"] for issue in melody_report["issues"]]
    if out_of_key_ratio > 0.3:
        issues.append("离调音符偏多")

    score = 1.0 + melody_report["score"] / 25.0
    if out_of_key_ratio > 0.3:
        score -= 0.5
    metrics["out_of_key_ratio"] = round(out_of_key_ratio, 3)
    return round(max(1.0, min(5.0, score)), 2), issues, metrics, melody_report


async def evaluate_overall_quality(
    audio_path: str,
    melody_notes: Optional[List[Dict[str, Any]]] = None,
    melody_quality_report: Optional[Dict[str, Any]] = None,
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

    audio_issues = list(issues)
    audio_score = max(1.0, min(5.0, 4.0 - len(audio_issues) * 0.5))

    # 音乐性评估
    mus_score, mus_issues, mus_metrics, melody_report = _musicality_metrics(
        melody_notes, key_midi, mode, melody_quality_report
    )
    issues = issues + mus_issues

    overall = round((audio_score + mus_score) / 2, 2)

    return {
        "overall_score": overall,
        "naturalness": round(audio_score, 2),
        "musicality": mus_score,
        "clarity": round(audio_score, 2),
        "quality_issues": issues,
        "musicality_metrics": mus_metrics,
        "melody_quality_report": melody_report,
        "passed": (
            overall >= 3.5
            and not audio_issues
            and (melody_report is None or melody_report["passed"])
            and mus_metrics.get("out_of_key_ratio", 0.0) <= 0.3
        ),
    }


class EvaluateOverallQualityInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")
    melody_notes: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="旋律音符列表（可选，用于音乐性评估）",
    )
    melody_quality_report: Optional[Dict[str, Any]] = Field(
        default=None,
        description="提取阶段生成的版本化旋律质量报告（可选）",
    )
    key_midi: Optional[int] = Field(default=None, description="调性根音 MIDI（可选）")
    mode: str = Field(default="major", description="调式：major 或 minor")


evaluate_overall_quality_tool = StructuredTool.from_function(
    coroutine=evaluate_overall_quality,
    name="evaluate_overall_quality",
    description=(
        "综合评估音频质量（工程指标 + 音乐性指标），"
        "返回总分（1-5）、问题列表以及是否通过。"
    ),
    args_schema=EvaluateOverallQualityInput,
)
