"""旋律音符稳定化。

Basic Pitch 在人声换气、辅音、滑音和颤音处容易产生极短音符或同一时刻的
多个候选音高。这个模块在节拍量化前做确定性的轻量清理，避免短误检被量化
成完整的十六分音符，同时保留正常的快速旋律进行。
"""

from __future__ import annotations

import math
from typing import Any


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _confidence(note: dict[str, Any]) -> float:
    confidence = _finite_number(note.get("confidence"))
    if confidence is not None:
        return max(0.0, min(1.0, confidence))

    velocity = _finite_number(note.get("velocity"))
    if velocity is None:
        return 0.5
    return max(0.0, min(1.0, velocity / 127.0))


def _duration(note: dict[str, Any]) -> float:
    return float(note["end"]) - float(note["start"])


def _candidate_score(note: dict[str, Any], previous_pitch: int | None) -> float:
    """在同一 onset 的候选中优先可靠、持续时间长且旋律连续的音高。"""
    duration_bonus = min(_duration(note), 0.5) / 0.5 * 0.15
    continuity_penalty = 0.0
    if previous_pitch is not None:
        distance = min(abs(int(note["pitch"]) - previous_pitch), 12)
        continuity_penalty = distance / 12.0 * 0.2
    return _confidence(note) + duration_bonus - continuity_penalty


def _normalize_notes(
    melody_notes: list[dict[str, Any]],
    min_duration: float,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw_note in melody_notes:
        if not isinstance(raw_note, dict):
            continue

        pitch = _finite_number(raw_note.get("pitch"))
        start = _finite_number(raw_note.get("start"))
        end = _finite_number(raw_note.get("end"))
        if pitch is None or start is None or end is None:
            continue
        if not 0 <= pitch <= 127 or start < 0 or end - start < min_duration:
            continue

        normalized.append(
            {
                **raw_note,
                "pitch": int(round(pitch)),
                "start": start,
                "end": end,
            }
        )

    return sorted(normalized, key=lambda note: (note["start"], note["end"]))


def _select_onset_candidates(
    notes: list[dict[str, Any]],
    onset_tolerance: float,
) -> list[dict[str, Any]]:
    """同一 onset 只保留一个最可能属于主旋律的候选。"""
    if not notes:
        return []

    groups: list[list[dict[str, Any]]] = []
    for note in notes:
        if not groups or note["start"] - groups[-1][0]["start"] > onset_tolerance:
            groups.append([note])
        else:
            groups[-1].append(note)

    selected: list[dict[str, Any]] = []
    for group in groups:
        previous_pitch = int(selected[-1]["pitch"]) if selected else None
        winner = max(
            group,
            key=lambda note: (
                _candidate_score(note, previous_pitch),
                _duration(note),
                -int(note["pitch"]),
            ),
        )
        selected.append(dict(winner))
    return selected


def _make_monophonic(
    notes: list[dict[str, Any]],
    min_duration: float,
) -> list[dict[str, Any]]:
    """消除残余叠音；新的可靠 onset 代表一次旋律音高切换。"""
    monophonic: list[dict[str, Any]] = []
    for note in notes:
        current = dict(note)
        if not monophonic:
            monophonic.append(current)
            continue

        previous = monophonic[-1]
        if current["start"] >= previous["end"]:
            monophonic.append(current)
            continue

        if current["pitch"] == previous["pitch"]:
            previous["end"] = max(previous["end"], current["end"])
            previous["velocity"] = max(
                previous.get("velocity", 0), current.get("velocity", 0)
            )
            previous["confidence"] = max(_confidence(previous), _confidence(current))
            continue

        # 当前音符完全被前一音符覆盖时，只有显著更可信才切换主旋律。
        if current["end"] <= previous["end"]:
            score_margin = _candidate_score(current, previous["pitch"]) - _candidate_score(
                previous,
                monophonic[-2]["pitch"] if len(monophonic) > 1 else None,
            )
            if score_margin < 0.15:
                continue

        previous["end"] = current["start"]
        if _duration(previous) < min_duration:
            monophonic.pop()
        monophonic.append(current)

    return monophonic


def _merge_same_pitch(
    notes: list[dict[str, Any]],
    merge_gap: float,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for note in notes:
        if (
            merged
            and note["pitch"] == merged[-1]["pitch"]
            and note["start"] - merged[-1]["end"] < merge_gap
        ):
            merged[-1]["end"] = max(merged[-1]["end"], note["end"])
            merged[-1]["velocity"] = max(
                merged[-1].get("velocity", 0), note.get("velocity", 0)
            )
            merged[-1]["confidence"] = max(
                _confidence(merged[-1]), _confidence(note)
            )
        else:
            merged.append(dict(note))
    return merged


def _collapse_returning_blips(
    notes: list[dict[str, Any]],
    merge_gap: float,
    blip_duration: float,
) -> list[dict[str, Any]]:
    """将短暂的 A-B-A 颤音/滑音误检折叠回主音高。"""
    result = [dict(note) for note in notes]
    index = 1
    while index < len(result) - 1:
        previous, current, following = result[index - 1 : index + 2]
        outer_pitch_distance = abs(previous["pitch"] - following["pitch"])
        blip_pitch_distance = min(
            abs(current["pitch"] - previous["pitch"]),
            abs(current["pitch"] - following["pitch"]),
        )
        left_gap = current["start"] - previous["end"]
        right_gap = following["start"] - current["end"]
        is_returning_blip = (
            outer_pitch_distance <= 1
            and current["pitch"] not in {previous["pitch"], following["pitch"]}
            and blip_pitch_distance <= 2
            and _duration(current) <= blip_duration
            and left_gap < merge_gap
            and right_gap < merge_gap
        )
        if not is_returning_blip:
            index += 1
            continue

        outer_notes = (previous, following)
        anchor = max(
            outer_notes,
            key=lambda note: (_duration(note) * (0.5 + _confidence(note)), _duration(note)),
        )
        replacement = {
            **anchor,
            "start": previous["start"],
            "end": following["end"],
            "velocity": max(
                note.get("velocity", 0) for note in (previous, current, following)
            ),
            "confidence": max(_confidence(previous), _confidence(following)),
        }
        result[index - 1 : index + 2] = [replacement]
        index = max(1, index - 1)
    return result


def stabilize_melody_notes(
    melody_notes: list[dict[str, Any]],
    min_duration: float = 0.1,
    onset_tolerance: float = 0.04,
    merge_gap: float = 0.1,
    blip_duration: float = 0.18,
) -> list[dict[str, Any]]:
    """在量化前抑制短碎音、叠音和短暂的返回型音高抖动。

    所有阈值均为秒。函数不修改输入列表，输出按开始时间排序且为单旋律。
    """
    if min_duration <= 0:
        raise ValueError("min_duration 必须大于 0")
    if onset_tolerance < 0 or merge_gap < 0 or blip_duration < min_duration:
        raise ValueError("旋律稳定化参数无效")

    normalized = _normalize_notes(melody_notes, min_duration)
    selected = _select_onset_candidates(normalized, onset_tolerance)
    monophonic = _make_monophonic(selected, min_duration)
    merged = _merge_same_pitch(monophonic, merge_gap)
    collapsed = _collapse_returning_blips(merged, merge_gap, blip_duration)
    return _merge_same_pitch(collapsed, merge_gap)
