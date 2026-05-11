# app/agent/atomic_tools/quality/overall_quality.py
from .loudness_check import check_loudness
from .spectral_balance import check_spectral_balance
from .dynamic_range import check_dynamic_range
from .zero_crossing_rate import get_zero_crossing_rate
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def evaluate_overall_quality(audio_path: str) -> dict:
    """
    聚合多个质量指标，返回总分及问题列表。

    Returns:
        dict: overall_score, naturalness, musicality, clarity, quality_issues, passed
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
    
    base_score = 4.0
    penalty = len(issues) * 0.5
    overall = max(1.0, min(5.0, base_score - penalty))
    
    return {
        "overall_score": overall,
        "naturalness": overall - 0.2,
        "musicality": overall - 0.3,
        "clarity": overall - 0.1,
        "quality_issues": issues,
        "passed": overall >= 3.5 and len(issues) == 0,
    }

class EvaluateOverallQualityInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

evaluate_overall_quality_tool = StructuredTool.from_function(
    coroutine=evaluate_overall_quality,
    name="evaluate_overall_quality",
    description="综合评估音频质量，返回总分（1-5）、问题列表以及是否通过。",
    args_schema=EvaluateOverallQualityInput,
)