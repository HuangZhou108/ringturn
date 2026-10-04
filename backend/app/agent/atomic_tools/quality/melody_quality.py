"""确定性的旋律质量指标与门禁。

这里评估的是提取结果本身是否适合继续生成 MIDI，并不声称在没有标注旋律的
情况下计算真实的转录准确率。报告同时提供稳定的机器可读 code，供 Agent
路由、日志和离线基准复用。
"""

from __future__ import annotations

import math
from typing import Any


REPORT_VERSION = 1


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalize_note(note: Any) -> dict[str, Any] | None:
    if not isinstance(note, dict):
        return None

    pitch = _finite(note.get("pitch"))
    start = _finite(note.get("start"))
    end = _finite(note.get("end"))
    if pitch is None or start is None or end is None:
        return None
    if not 0 <= pitch <= 127 or start < 0 or end <= start:
        return None

    return {
        **note,
        "pitch": int(round(pitch)),
        "start": start,
        "end": end,
    }


def _note_confidence(note: dict[str, Any]) -> float:
    confidence = _finite(note.get("confidence"))
    if confidence is not None:
        return max(0.0, min(1.0, confidence))

    velocity = _finite(note.get("velocity"))
    if velocity is None:
        return 0.5
    return max(0.0, min(1.0, velocity / 127.0))


def _active_duration(
    notes: list[dict[str, Any]],
    audio_duration: float | None,
) -> float:
    if not notes:
        return 0.0

    intervals: list[tuple[float, float]] = []
    for note in notes:
        start = note["start"]
        end = note["end"]
        if audio_duration is not None:
            start = min(max(start, 0.0), audio_duration)
            end = min(max(end, 0.0), audio_duration)
        if end > start:
            intervals.append((start, end))

    if not intervals:
        return 0.0

    intervals.sort()
    total = 0.0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    return total + current_end - current_start


def _issue(
    code: str,
    severity: str,
    message: str,
    value: float,
    threshold: float,
    blocking: bool = False,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "value": round(value, 4),
        "threshold": threshold,
        "blocking": blocking,
    }


def evaluate_melody_quality(
    melody_notes: list[dict[str, Any]] | None,
    audio_duration: float | None = None,
    short_note_threshold: float = 0.12,
) -> dict[str, Any]:
    """评估旋律事件的结构质量，返回分数、指标和结构化问题。

    ``passed`` 是正常质量阈值；``usable`` 只在结果严重异常、继续生成 MIDI
    几乎必然产生垃圾输出时为 False。普通警告不会中断主流程。
    """
    parsed_short_threshold = _finite(short_note_threshold)
    if parsed_short_threshold is None or parsed_short_threshold <= 0:
        raise ValueError("short_note_threshold 必须为正数")

    raw_notes = melody_notes or []
    normalized = [note for raw in raw_notes if (note := _normalize_note(raw))]
    notes = sorted(normalized, key=lambda note: (note["start"], note["end"]))

    parsed_audio_duration = _finite(audio_duration)
    if parsed_audio_duration is not None and parsed_audio_duration <= 0:
        parsed_audio_duration = None

    raw_count = len(raw_notes)
    note_count = len(notes)
    invalid_note_ratio = (raw_count - note_count) / raw_count if raw_count else 0.0

    if not notes:
        issue = _issue(
            "no_valid_notes",
            "error",
            "旋律提取未产生有效音符",
            0.0,
            1.0,
            blocking=True,
        )
        return {
            "version": REPORT_VERSION,
            "score": 0.0,
            "passed": False,
            "usable": False,
            "issues": [issue],
            "issue_codes": [issue["code"]],
            "metrics": {
                "note_count": 0,
                "invalid_note_ratio": round(invalid_note_ratio, 4),
                "audio_duration": round(parsed_audio_duration or 0.0, 4),
                "active_duration": 0.0,
                "active_coverage_ratio": 0.0,
                "note_density": 0.0,
                "short_note_ratio": 0.0,
                "overlap_ratio": 0.0,
                "large_leap_ratio": 0.0,
                "extreme_leap_ratio": 0.0,
                "pitch_range": 0,
                "mean_confidence": 0.0,
                "out_of_bounds_ratio": 0.0,
            },
            "penalties": {"no_valid_notes": 100.0},
        }

    first_start = notes[0]["start"]
    last_end = max(note["end"] for note in notes)
    timeline_duration = max(last_end - first_start, 0.0)
    scoring_duration = parsed_audio_duration or timeline_duration
    active_duration = _active_duration(notes, parsed_audio_duration)
    active_coverage_ratio = (
        active_duration / scoring_duration if scoring_duration > 0 else 0.0
    )
    note_density = note_count / scoring_duration if scoring_duration > 0 else 0.0

    durations = [note["end"] - note["start"] for note in notes]
    short_note_ratio = sum(
        duration < parsed_short_threshold for duration in durations
    ) / note_count

    pitches = [note["pitch"] for note in notes]
    pitch_range = max(pitches) - min(pitches)
    intervals = [
        abs(current - previous)
        for previous, current in zip(pitches, pitches[1:])
    ]
    large_leap_ratio = (
        sum(interval > 12 for interval in intervals) / len(intervals) if intervals else 0.0
    )
    extreme_leap_ratio = (
        sum(interval > 24 for interval in intervals) / len(intervals) if intervals else 0.0
    )

    overlap_count = 0
    running_end = notes[0]["end"]
    for note in notes[1:]:
        if note["start"] < running_end:
            overlap_count += 1
        running_end = max(running_end, note["end"])
    overlap_ratio = overlap_count / (note_count - 1) if note_count > 1 else 0.0

    mean_confidence = sum(_note_confidence(note) for note in notes) / note_count
    out_of_bounds_ratio = 0.0
    if parsed_audio_duration is not None:
        out_of_bounds_ratio = sum(
            note["start"] > parsed_audio_duration
            or note["end"] > parsed_audio_duration + 0.1
            for note in notes
        ) / note_count

    issues: list[dict[str, Any]] = []
    if invalid_note_ratio > 0.1:
        blocking = invalid_note_ratio >= 0.5
        issues.append(
            _issue(
                "invalid_notes",
                "error" if blocking else "warning",
                "无效音符数据偏多",
                invalid_note_ratio,
                0.1,
                blocking,
            )
        )
    if short_note_ratio > 0.25:
        issues.append(
            _issue(
                "fragmented_notes",
                "error" if short_note_ratio > 0.5 else "warning",
                "短碎音符偏多",
                short_note_ratio,
                0.25,
            )
        )
    if overlap_ratio > 0.1:
        blocking = overlap_ratio > 0.75
        issues.append(
            _issue(
                "overlapping_notes",
                "error" if overlap_ratio > 0.5 else "warning",
                "单旋律中存在过多重叠音符",
                overlap_ratio,
                0.1,
                blocking,
            )
        )
    if note_density > 10.0:
        blocking = note_density > 30.0
        issues.append(
            _issue(
                "excessive_note_density",
                "error" if note_density > 18.0 else "warning",
                "单位时间音符过密",
                note_density,
                10.0,
                blocking,
            )
        )
    if large_leap_ratio > 0.25:
        issues.append(
            _issue(
                "large_pitch_leaps",
                "warning",
                "旋律中的大跳音程偏多",
                large_leap_ratio,
                0.25,
            )
        )
    if extreme_leap_ratio > 0.1:
        issues.append(
            _issue(
                "extreme_pitch_leaps",
                "error",
                "旋律中疑似存在八度或泛音误判",
                extreme_leap_ratio,
                0.1,
            )
        )
    if pitch_range > 36:
        issues.append(
            _issue(
                "excessive_pitch_range",
                "warning",
                "旋律音域异常宽",
                float(pitch_range),
                36.0,
            )
        )
    if mean_confidence < 0.4:
        issues.append(
            _issue(
                "low_confidence",
                "warning",
                "旋律提取平均置信度偏低",
                mean_confidence,
                0.4,
            )
        )
    if parsed_audio_duration is not None and parsed_audio_duration >= 5.0:
        if active_coverage_ratio < 0.08:
            blocking = active_coverage_ratio < 0.01
            issues.append(
                _issue(
                    "low_melody_coverage",
                    "error" if active_coverage_ratio < 0.02 else "warning",
                    "有效旋律覆盖时长过低",
                    active_coverage_ratio,
                    0.08,
                    blocking,
                )
            )
        if note_count < 3:
            issues.append(
                _issue(
                    "too_few_notes",
                    "warning",
                    "有效旋律音符数量过少",
                    float(note_count),
                    3.0,
                )
            )
    if out_of_bounds_ratio > 0.1:
        issues.append(
            _issue(
                "notes_out_of_bounds",
                "error",
                "部分音符超出源音频时间范围",
                out_of_bounds_ratio,
                0.1,
            )
        )

    penalties = {
        "invalid_notes": min(30.0, invalid_note_ratio * 50.0),
        "fragmentation": min(30.0, max(0.0, short_note_ratio - 0.1) * 50.0),
        "overlap": min(30.0, overlap_ratio * 40.0),
        "large_leaps": min(20.0, max(0.0, large_leap_ratio - 0.1) * 35.0),
        "extreme_leaps": min(20.0, extreme_leap_ratio * 50.0),
        "density": min(25.0, max(0.0, note_density - 8.0) * 3.0),
        "pitch_range": min(15.0, max(0.0, pitch_range - 36.0) * 0.5),
        "low_confidence": min(15.0, max(0.0, 0.5 - mean_confidence) * 30.0),
        "out_of_bounds": min(25.0, out_of_bounds_ratio * 50.0),
    }
    if parsed_audio_duration is not None and parsed_audio_duration >= 5.0:
        penalties["low_coverage"] = min(
            25.0,
            max(0.0, 0.08 - active_coverage_ratio) / 0.08 * 25.0,
        )

    score = round(max(0.0, 100.0 - sum(penalties.values())), 2)
    usable = not any(issue["blocking"] for issue in issues)
    passed = usable and score >= 70.0 and not any(
        issue["severity"] == "error" for issue in issues
    )

    metrics = {
        "note_count": note_count,
        "invalid_note_ratio": round(invalid_note_ratio, 4),
        "audio_duration": round(scoring_duration, 4),
        "active_duration": round(active_duration, 4),
        "active_coverage_ratio": round(active_coverage_ratio, 4),
        "note_density": round(note_density, 4),
        "short_note_ratio": round(short_note_ratio, 4),
        "overlap_ratio": round(overlap_ratio, 4),
        "large_leap_ratio": round(large_leap_ratio, 4),
        "extreme_leap_ratio": round(extreme_leap_ratio, 4),
        "pitch_range": pitch_range,
        "mean_confidence": round(mean_confidence, 4),
        "out_of_bounds_ratio": round(out_of_bounds_ratio, 4),
    }
    return {
        "version": REPORT_VERSION,
        "score": score,
        "passed": passed,
        "usable": usable,
        "issues": issues,
        "issue_codes": [issue["code"] for issue in issues],
        "metrics": metrics,
        "penalties": {key: round(value, 2) for key, value in penalties.items()},
    }
