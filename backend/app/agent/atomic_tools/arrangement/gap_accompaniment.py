"""为主旋律长休止生成低干扰伴奏计划。"""

from math import isfinite
from typing import Any, TypedDict


class GapAccompanimentPlan(TypedDict):
    """长休止伴奏策略的可观测结果。"""

    segments: list[dict[str, Any]]
    reason: str
    gap_count: int
    valid_chord_count: int
    in_key_ratio: float | None
    timeline_offset: float


_MAJOR_SCALE = {0, 2, 4, 5, 7, 9, 11}
_MINOR_SCALE = {0, 2, 3, 5, 7, 8, 10}


def select_accompaniment_channels(used_channels: set[int]) -> tuple[int, int]:
    """为 Bass/Pad 选择互不相同且尽量未占用的非鼓组 MIDI channel。"""
    occupied = {channel for channel in used_channels if 0 <= channel <= 15}
    selected = [
        channel
        for channel in range(16)
        if channel != 9 and channel not in occupied
    ][:2]
    if len(selected) < 2:
        for channel in range(15, -1, -1):
            if channel != 9 and channel not in selected:
                selected.append(channel)
            if len(selected) == 2:
                break
    return selected[0], selected[1]


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _midi_root(value: Any) -> int | None:
    number = _finite_float(value)
    if number is None:
        return None
    note = int(round(number))
    if not 0 <= note <= 127:
        return None
    # 将伴奏根音统一放在 C4-B4，低音轨会再降低一个八度。
    return 60 + (note % 12)


def _melody_gaps(
    melody_notes: list[dict[str, Any]],
    *,
    min_gap_seconds: float,
    sustain_tail_seconds: float,
    target_duration: float | None,
) -> tuple[list[tuple[float, float]], float]:
    intervals: list[tuple[float, float]] = []
    for note in melody_notes:
        start = _finite_float(note.get("start"))
        end = _finite_float(note.get("end"))
        if start is None or end is None or end <= start:
            continue
        intervals.append((start, end))

    if not intervals:
        return [], 0.0

    intervals.sort()
    timeline_offset = intervals[0][0]
    shifted = [(start - timeline_offset, end - timeline_offset) for start, end in intervals]

    melody_duration = max(end for _, end in shifted)
    if target_duration and 0 < melody_duration < target_duration:
        original = shifted
        shifted = []
        offset = 0.0
        while offset < target_duration:
            shifted.extend(
                (start + offset, end + offset)
                for start, end in original
                if start + offset < target_duration
            )
            offset += melody_duration

    merged: list[list[float]] = []
    for start, end in shifted:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    gaps: list[tuple[float, float]] = []
    active_end = merged[0][1]
    for next_start, next_end in merged[1:]:
        # generate_midi 已使用 sustain=1.0；这里只为策略建模，不重复修改旋律。
        audible_end = min(next_start, active_end + sustain_tail_seconds)
        if next_start - audible_end >= min_gap_seconds:
            gaps.append((audible_end, next_start))
        active_end = max(active_end, next_end)

    return gaps, timeline_offset


def _valid_chords(
    chords: list[dict[str, Any]],
    *,
    timeline_offset: float,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for chord in chords:
        start = _finite_float(chord.get("start"))
        end = _finite_float(chord.get("end"))
        root = _midi_root(chord.get("root_midi"))
        if start is None or end is None or root is None or end <= start:
            continue

        start -= timeline_offset
        end -= timeline_offset
        if end <= 0:
            continue
        result.append({"start": max(0.0, start), "end": end, "root_midi": root})

    return sorted(result, key=lambda item: (item["start"], item["end"]))


def plan_gap_accompaniment(
    *,
    melody_notes: list[dict[str, Any]],
    chords: list[dict[str, Any]],
    key_midi: int | float | None,
    mode: str = "major",
    min_gap_seconds: float = 1.25,
    sustain_tail_seconds: float = 1.0,
    target_duration: int | float | None = None,
) -> GapAccompanimentPlan:
    """
    仅为主旋律中的长休止生成伴奏段。

    和弦根音必须落在检测调式内；不可靠或缺失的和弦会回退到主调 tonic。
    不为开头、结尾或短换气生成伴奏，避免改变旋律节奏和过度填充。
    """
    min_gap = max(0.0, float(min_gap_seconds))
    sustain_tail = max(0.0, float(sustain_tail_seconds))
    duration = _finite_float(target_duration)
    if duration is not None and duration <= 0:
        duration = None
    gaps, timeline_offset = _melody_gaps(
        melody_notes,
        min_gap_seconds=min_gap,
        sustain_tail_seconds=sustain_tail,
        target_duration=duration,
    )
    if not gaps:
        return {
            "segments": [],
            "reason": "no_long_gaps",
            "gap_count": 0,
            "valid_chord_count": 0,
            "in_key_ratio": None,
            "timeline_offset": timeline_offset,
        }

    valid_chords = _valid_chords(chords, timeline_offset=timeline_offset)
    tonic = _midi_root(key_midi)
    in_key_ratio: float | None = None
    usable_chords = valid_chords

    if tonic is not None and valid_chords:
        scale = _MINOR_SCALE if str(mode).lower().startswith("minor") else _MAJOR_SCALE
        tonic_pc = tonic % 12
        in_key = [
            chord
            for chord in valid_chords
            if ((chord["root_midi"] % 12) - tonic_pc) % 12 in scale
        ]
        in_key_ratio = len(in_key) / len(valid_chords)
        # 大多数根音都不在调内时，放弃整条和弦检测结果，使用更安全的 tonic。
        usable_chords = in_key if in_key_ratio >= 0.6 else []

    segments: list[dict[str, Any]] = []
    used_chord = False
    used_tonic = False
    for gap_start, gap_end in gaps:
        midpoint = (gap_start + gap_end) / 2.0
        overlapping = [
            chord
            for chord in usable_chords
            if chord["start"] < gap_end and chord["end"] > gap_start
        ]
        if overlapping:
            selected = max(
                overlapping,
                key=lambda chord: min(chord["end"], gap_end) - max(chord["start"], gap_start),
            )
            root = selected["root_midi"]
            source = "validated_chord"
            used_chord = True
        elif tonic is not None:
            root = tonic
            source = "key_tonic_fallback"
            used_tonic = True
        elif usable_chords:
            selected = min(
                usable_chords,
                key=lambda chord: abs(((chord["start"] + chord["end"]) / 2.0) - midpoint),
            )
            root = selected["root_midi"]
            source = "nearest_validated_chord"
            used_chord = True
        else:
            continue

        segments.append(
            {
                "start": gap_start,
                "end": gap_end,
                "root_midi": root,
                "source": source,
            }
        )

    if used_chord and used_tonic:
        reason = "validated_chords_with_key_fallback"
    elif used_chord:
        reason = "validated_chords"
    elif used_tonic:
        reason = "key_fallback"
    else:
        reason = "no_reliable_harmony"

    return {
        "segments": segments,
        "reason": reason,
        "gap_count": len(gaps),
        "valid_chord_count": len(valid_chords),
        "in_key_ratio": in_key_ratio,
        "timeline_offset": timeline_offset,
    }
