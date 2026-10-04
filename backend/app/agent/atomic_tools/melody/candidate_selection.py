"""旋律候选的确定性选择策略。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_EXTRACTOR_ORDER = ("basic_pitch", "librosa")


def should_run_fallback_candidate(
    current_extractor: str | None,
    quality_report: dict[str, Any] | None,
    candidates: dict[str, dict[str, Any]] | None,
) -> bool:
    """仅在主候选未通过且 fallback 尚未运行时继续候选循环。"""
    return (
        current_extractor == "basic_pitch"
        and not bool((quality_report or {}).get("passed", False))
        and "librosa" not in (candidates or {})
    )


def _candidate_rank(
    extractor: str,
    candidate: dict[str, Any],
    preference_order: tuple[str, ...],
) -> tuple[int, int, float, int]:
    report = candidate.get("quality_report") or {}
    preference = (
        preference_order.index(extractor)
        if extractor in preference_order
        else len(preference_order)
    )
    return (
        int(bool(report.get("usable", False))),
        int(bool(report.get("passed", False))),
        float(report.get("score", 0.0)),
        -preference,
    )


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    report = candidate.get("quality_report") or {}
    metrics = report.get("metrics") or {}
    melody_data = candidate.get("melody_data") or {}
    return {
        "score": float(report.get("score", 0.0)),
        "passed": bool(report.get("passed", False)),
        "usable": bool(report.get("usable", False)),
        "issue_codes": list(report.get("issue_codes") or []),
        "note_count": int(metrics.get("note_count", 0)),
        "error": melody_data.get("extraction_error"),
    }


def select_best_melody_candidate(
    candidates: dict[str, dict[str, Any]],
    preference_order: tuple[str, ...] = DEFAULT_EXTRACTOR_ORDER,
) -> dict[str, Any]:
    """优先选择可用、已通过且分数更高的候选，平分时保持主提取器优先。"""
    if not candidates:
        raise ValueError("没有可供选择的旋律候选")

    valid_candidates = {
        extractor: candidate
        for extractor, candidate in candidates.items()
        if isinstance(candidate, dict)
        and isinstance(candidate.get("melody_data"), dict)
        and isinstance(candidate.get("quality_report"), dict)
    }
    if not valid_candidates:
        raise ValueError("旋律候选缺少 melody_data 或 quality_report")

    selected_extractor, selected_candidate = max(
        valid_candidates.items(),
        key=lambda item: _candidate_rank(item[0], item[1], preference_order),
    )
    summaries = {
        extractor: _candidate_summary(candidate)
        for extractor, candidate in valid_candidates.items()
    }

    primary_extractor = preference_order[0] if preference_order else None
    if len(valid_candidates) == 1:
        reason = "single_candidate"
    elif selected_extractor == primary_extractor:
        reason = "primary_retained"
    else:
        reason = "fallback_higher_quality"

    return {
        "selected_extractor": selected_extractor,
        "melody_data": deepcopy(selected_candidate["melody_data"]),
        "quality_report": deepcopy(selected_candidate["quality_report"]),
        "candidate_summaries": summaries,
        "reason": reason,
    }
