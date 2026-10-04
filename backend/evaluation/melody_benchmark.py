"""可复现的旋律提取离线 benchmark。

该模块把两类指标明确分开：

1. 无参考结构质量：复用生产环境的 ``evaluate_melody_quality``；
2. 有参考转录质量：对预测与参考音符做一对一 onset/pitch 匹配。

真实提取依赖 Basic Pitch 与 librosa。CI 可以使用 manifest 中缓存的音符 JSON，
因此无需下载模型或提交版权音频。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import re
import time
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from statistics import fmean
from typing import Any, Awaitable, Callable

SCHEMA_VERSION = 1
SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
EXTRACTORS = ("basic_pitch", "librosa")
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ATOMIC_TOOLS_DIR = (
    Path(__file__).resolve().parents[1] / "app" / "agent" / "atomic_tools"
)

QualityEvaluator = Callable[[list[dict[str, Any]], float | None], dict[str, Any]]
CandidateSelector = Callable[[dict[str, dict[str, Any]]], dict[str, Any]]
ExtractorRunner = Callable[
    [str, Path, Path, dict[str, Any]],
    Awaitable[list[dict[str, Any]]],
]


class BenchmarkError(RuntimeError):
    """Manifest、依赖或评测输入不合法。"""


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalize_notes(notes: Any) -> list[dict[str, Any]]:
    if not isinstance(notes, list):
        raise BenchmarkError("音符数据必须是 JSON 数组或包含 melody_notes 的对象")

    normalized: list[dict[str, Any]] = []
    for raw in notes:
        if not isinstance(raw, dict):
            continue
        pitch = _finite(raw.get("pitch"))
        start = _finite(raw.get("start"))
        end = _finite(raw.get("end"))
        if pitch is None or start is None or end is None:
            continue
        if not 0 <= pitch <= 127 or start < 0 or end <= start:
            continue
        normalized.append(
            {
                **raw,
                "pitch": int(round(pitch)),
                "start": start,
                "end": end,
            }
        )
    return sorted(
        normalized, key=lambda note: (note["start"], note["pitch"], note["end"])
    )


def load_notes_json(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BenchmarkError(f"音符文件不存在: {path}") from error
    except json.JSONDecodeError as error:
        raise BenchmarkError(f"音符文件不是合法 JSON: {path}: {error}") from error

    if isinstance(payload, dict):
        payload = payload.get("melody_notes")
    return _normalize_notes(payload)


def load_reference_midi(
    path: Path, instrument_index: int | None = None
) -> list[dict[str, Any]]:
    try:
        import pretty_midi
    except ImportError as error:
        raise BenchmarkError(
            "读取参考 MIDI 需要安装 requirements.txt 中的 pretty_midi"
        ) from error

    try:
        midi = pretty_midi.PrettyMIDI(str(path))
    except Exception as error:
        raise BenchmarkError(f"无法读取参考 MIDI {path}: {error}") from error

    instruments = [
        instrument for instrument in midi.instruments if not instrument.is_drum
    ]
    if not instruments:
        return []
    if instrument_index is not None and (
        isinstance(instrument_index, bool) or not isinstance(instrument_index, int)
    ):
        raise BenchmarkError("reference_instrument 必须是从 0 开始的整数")
    if instrument_index is None and len(instruments) > 1:
        raise BenchmarkError(
            f"参考 MIDI {path} 含多个非鼓轨，请在 manifest 设置 reference_instrument"
        )
    selected_index = instrument_index or 0
    if selected_index < 0 or selected_index >= len(instruments):
        raise BenchmarkError(
            f"reference_instrument={selected_index} 超出 MIDI 非鼓轨范围 0..{len(instruments) - 1}"
        )

    return _normalize_notes(
        [
            {
                "pitch": note.pitch,
                "start": note.start,
                "end": note.end,
                "velocity": note.velocity,
            }
            for note in instruments[selected_index].notes
        ]
    )


def load_reference_notes(case: dict[str, Any]) -> list[dict[str, Any]] | None:
    reference_path = case.get("reference_path")
    if not reference_path:
        return None
    path = Path(reference_path)
    if path.suffix.lower() in {".mid", ".midi"}:
        return load_reference_midi(path, case.get("reference_instrument"))
    return load_notes_json(path)


def _duration_iou(predicted: dict[str, Any], reference: dict[str, Any]) -> float:
    overlap = max(
        0.0,
        min(predicted["end"], reference["end"])
        - max(predicted["start"], reference["start"]),
    )
    union = max(predicted["end"], reference["end"]) - min(
        predicted["start"], reference["start"]
    )
    return overlap / union if union > 0 else 0.0


def match_melody_notes(
    predicted_notes: list[dict[str, Any]],
    reference_notes: list[dict[str, Any]],
    onset_tolerance: float = 0.1,
    pitch_tolerance: int = 0,
) -> dict[str, Any]:
    """对预测与参考音符做确定性的一对一贪心匹配。"""
    if onset_tolerance < 0 or pitch_tolerance < 0:
        raise ValueError("匹配容差不能为负数")

    predicted = _normalize_notes(predicted_notes)
    reference = _normalize_notes(reference_notes)
    pairs: list[tuple[float, int, int, int]] = []
    for predicted_index, predicted_note in enumerate(predicted):
        for reference_index, reference_note in enumerate(reference):
            onset_error = abs(predicted_note["start"] - reference_note["start"])
            pitch_error = abs(predicted_note["pitch"] - reference_note["pitch"])
            if onset_error <= onset_tolerance and pitch_error <= pitch_tolerance:
                pairs.append(
                    (onset_error, pitch_error, predicted_index, reference_index)
                )

    matched_predicted: set[int] = set()
    matched_reference: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for onset_error, _pitch_error, predicted_index, reference_index in sorted(pairs):
        if predicted_index in matched_predicted or reference_index in matched_reference:
            continue
        matched_predicted.add(predicted_index)
        matched_reference.add(reference_index)
        matches.append((predicted_index, reference_index, onset_error))

    matched_count = len(matches)
    precision = matched_count / len(predicted) if predicted else 0.0
    recall = matched_count / len(reference) if reference else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    onset_errors = [match[2] for match in matches]
    duration_ious = [
        _duration_iou(predicted[predicted_index], reference[reference_index])
        for predicted_index, reference_index, _ in matches
    ]

    return {
        "reference_note_count": len(reference),
        "predicted_note_count": len(predicted),
        "matched_note_count": matched_count,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "mean_onset_error_ms": (
            round(fmean(onset_errors) * 1000, 2) if onset_errors else None
        ),
        "mean_duration_iou": round(fmean(duration_ious), 4) if duration_ious else None,
        "onset_tolerance": onset_tolerance,
        "pitch_tolerance": pitch_tolerance,
    }


def _load_default_quality_evaluator() -> QualityEvaluator:
    module = _load_source_module(
        "ringturn_benchmark_melody_quality",
        ATOMIC_TOOLS_DIR / "quality" / "melody_quality.py",
    )
    return module.evaluate_melody_quality


def _load_default_candidate_selector() -> CandidateSelector:
    module = _load_source_module(
        "ringturn_benchmark_candidate_selection",
        ATOMIC_TOOLS_DIR / "melody" / "candidate_selection.py",
    )
    return module.select_best_melody_candidate


@lru_cache(maxsize=None)
def _load_source_module(module_name: str, path: Path):
    """只加载所需源文件，避免离线工具触发整个 FastAPI/Agent 包初始化。"""
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise BenchmarkError(f"无法加载评测依赖: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError as error:
        raise BenchmarkError(
            f"无法导入评测依赖 {path.name}，请先安装 backend/requirements.txt"
        ) from error
    return module


def _resolve_manifest_path(base_dir: Path, value: Any) -> str | None:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return str(path.resolve())


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BenchmarkError(f"Manifest 不存在: {path}") from error
    except json.JSONDecodeError as error:
        raise BenchmarkError(f"Manifest 不是合法 JSON: {error}") from error

    if manifest.get("version") != SCHEMA_VERSION:
        raise BenchmarkError(f"Manifest version 必须为 {SCHEMA_VERSION}")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise BenchmarkError("Manifest cases 必须是数组")

    base_dir = path.parent.resolve()
    resolved_cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_case in cases:
        if not isinstance(raw_case, dict) or not raw_case.get("id"):
            raise BenchmarkError("每个 benchmark case 必须包含非空 id")
        case_id = str(raw_case["id"])
        if not CASE_ID_PATTERN.fullmatch(case_id):
            raise BenchmarkError(
                f"Benchmark case id 只能包含字母、数字、点、下划线和连字符: {case_id}"
            )
        if case_id in seen_ids:
            raise BenchmarkError(f"Benchmark case id 重复: {case_id}")
        seen_ids.add(case_id)

        resolved = dict(raw_case)
        resolved["id"] = case_id
        enabled = raw_case.get("enabled", True)
        if not isinstance(enabled, bool):
            raise BenchmarkError(f"Case {case_id} 的 enabled 必须是布尔值")
        resolved["enabled"] = enabled
        duration = _finite(raw_case.get("audio_duration"))
        if raw_case.get("audio_duration") is not None and (
            duration is None or duration <= 0
        ):
            raise BenchmarkError(f"Case {case_id} 的 audio_duration 必须大于 0")
        resolved["audio_duration"] = duration
        tags = raw_case.get("tags") or []
        if not isinstance(tags, list):
            raise BenchmarkError(f"Case {case_id} 的 tags 必须是数组")
        resolved["tags"] = [str(tag) for tag in tags]
        analysis = raw_case.get("analysis") or {}
        if not isinstance(analysis, dict):
            raise BenchmarkError(f"Case {case_id} 的 analysis 必须是对象")
        resolved_analysis = dict(analysis)
        bpm = _finite(analysis.get("bpm"))
        if analysis.get("bpm") is not None and (bpm is None or bpm <= 0):
            raise BenchmarkError(f"Case {case_id} 的 BPM 必须大于 0")
        resolved_analysis["bpm"] = bpm or 120.0
        mode = str(analysis.get("mode", "major")).lower()
        if mode not in {"major", "minor"}:
            raise BenchmarkError(f"Case {case_id} 的 mode 必须是 major 或 minor")
        resolved_analysis["mode"] = mode
        key_midi = _finite(analysis.get("key_midi"))
        if analysis.get("key_midi") is not None and (
            key_midi is None or not 0 <= key_midi <= 127
        ):
            raise BenchmarkError(f"Case {case_id} 的 key_midi 必须在 0..127")
        resolved_analysis["key_midi"] = (
            int(round(key_midi)) if key_midi is not None else None
        )
        resolved["analysis"] = resolved_analysis
        resolved["audio_path"] = _resolve_manifest_path(
            base_dir, raw_case.get("audio_path")
        )
        resolved["reference_path"] = _resolve_manifest_path(
            base_dir, raw_case.get("reference_path")
        )
        predictions = raw_case.get("predictions") or {}
        if not isinstance(predictions, dict):
            raise BenchmarkError(f"Case {case_id} 的 predictions 必须是对象")
        resolved["predictions"] = {
            extractor: _resolve_manifest_path(base_dir, predictions.get(extractor))
            for extractor in EXTRACTORS
            if predictions.get(extractor)
        }
        resolved_cases.append(resolved)

    return {
        **manifest,
        "manifest_path": str(path.resolve()),
        "cases": resolved_cases,
    }


async def _default_extractor_runner(
    extractor: str,
    audio_path: Path,
    output_midi_path: Path,
    case: dict[str, Any],
) -> list[dict[str, Any]]:
    """运行提取器，并复用生产图当前的确定性后处理参数。"""
    melody_dir = ATOMIC_TOOLS_DIR / "melody"
    if extractor == "basic_pitch":
        extractor_func = _load_source_module(
            "ringturn_benchmark_extract_basic_pitch",
            melody_dir / "extract_with_basic_pitch.py",
        ).extract_melody_basic_pitch
    elif extractor == "librosa":
        extractor_func = _load_source_module(
            "ringturn_benchmark_extract_librosa",
            melody_dir / "extract_with_librosa.py",
        ).extract_melody_librosa
    else:
        raise BenchmarkError(f"未知旋律提取器: {extractor}")
    stabilize_module = _load_source_module(
        "ringturn_benchmark_stabilize_notes",
        melody_dir / "stabilize_notes.py",
    )
    quantize_module = _load_source_module(
        "ringturn_benchmark_quantize_notes",
        melody_dir / "quantize_notes.py",
    )
    merge_module = _load_source_module(
        "ringturn_benchmark_merge_notes",
        melody_dir / "merge_notes.py",
    )
    snap_module = _load_source_module(
        "ringturn_benchmark_snap_to_key",
        melody_dir / "snap_to_key.py",
    )

    result = await extractor_func(
        str(audio_path),
        output_midi_path=str(output_midi_path),
    )
    notes = result.get("melody_notes") or []

    tags = {str(tag).lower() for tag in case.get("tags") or []}
    is_vocal = str(case.get("source_kind", "")).lower() == "vocals" or "vocal" in tags
    notes = stabilize_module.stabilize_melody_notes(
        notes,
        min_duration=0.1 if is_vocal else 0.05,
        onset_tolerance=0.04 if is_vocal else 0.025,
        merge_gap=0.1 if is_vocal else 0.05,
        blip_duration=0.18 if is_vocal else 0.12,
    )
    analysis = case.get("analysis") or {}
    bpm = analysis.get("bpm", 120.0)
    mode = analysis.get("mode", "major")
    notes = await quantize_module.quantize_notes(notes, grid=0.25, bpm=bpm)
    notes = await merge_module.merge_notes(notes, merge_gap=0.05)
    notes = await snap_module.snap_to_key(
        notes,
        key_midi=analysis.get("key_midi"),
        mode=mode,
    )
    return _normalize_notes(notes)


def _call_quality_evaluator(
    evaluator: QualityEvaluator,
    notes: list[dict[str, Any]],
    audio_duration: float | None,
) -> dict[str, Any]:
    return evaluator(notes, audio_duration=audio_duration)


def _write_notes(path: Path, notes: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"melody_notes": notes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _evaluate_candidate(
    extractor: str,
    case: dict[str, Any],
    case_output_dir: Path,
    reference_notes: list[dict[str, Any]] | None,
    reuse_predictions: bool,
    quality_evaluator: QualityEvaluator,
    extractor_runner: ExtractorRunner,
    onset_tolerance: float,
    pitch_tolerance: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = time.perf_counter()
    notes: list[dict[str, Any]] = []
    error_message: str | None = None
    source = "cached_prediction" if reuse_predictions else "audio_extraction"
    try:
        if reuse_predictions:
            prediction_path = case.get("predictions", {}).get(extractor)
            if not prediction_path:
                raise BenchmarkError(f"Case {case['id']} 缺少 predictions.{extractor}")
            notes = load_notes_json(Path(prediction_path))
        else:
            audio_path_value = case.get("audio_path")
            if not audio_path_value:
                raise BenchmarkError(f"Case {case['id']} 缺少 audio_path")
            audio_path = Path(audio_path_value)
            if audio_path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
                raise BenchmarkError(f"不支持的音频格式: {audio_path.suffix}")
            if not audio_path.is_file():
                raise BenchmarkError(f"音频文件不存在: {audio_path}")
            notes = await extractor_runner(
                extractor,
                audio_path,
                case_output_dir / f"{extractor}.mid",
                case,
            )
    except Exception as error:
        error_message = f"{type(error).__name__}: {error}"

    duration = _finite(case.get("audio_duration"))
    quality_report = _call_quality_evaluator(quality_evaluator, notes, duration)
    reference_metrics = (
        match_melody_notes(notes, reference_notes, onset_tolerance, pitch_tolerance)
        if reference_notes is not None
        else None
    )
    notes_path = case_output_dir / f"{extractor}.notes.json"
    _write_notes(notes_path, notes)
    result = {
        "status": "error" if error_message else "ok",
        "source": source,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "notes_path": notes_path.name,
        "quality_report": quality_report,
        "reference_metrics": reference_metrics,
        "error": error_message,
    }
    return result, notes


def _production_selection(
    candidate_results: dict[str, dict[str, Any]],
    candidate_notes: dict[str, list[dict[str, Any]]],
    selector: CandidateSelector,
) -> dict[str, Any]:
    basic_report = candidate_results["basic_pitch"]["quality_report"]
    if basic_report.get("passed", False):
        selected_extractor = "basic_pitch"
        reason = "primary_passed"
    else:
        selection = selector(
            {
                extractor: {
                    "melody_data": {"melody_notes": candidate_notes[extractor]},
                    "quality_report": candidate_results[extractor]["quality_report"],
                }
                for extractor in EXTRACTORS
            }
        )
        selected_extractor = selection["selected_extractor"]
        reason = selection["reason"]

    selected = candidate_results[selected_extractor]
    return {
        "status": selected["status"],
        "selected_extractor": selected_extractor,
        "selection_reason": reason,
        "quality_report": selected["quality_report"],
        "reference_metrics": selected["reference_metrics"],
        "error": selected["error"],
    }


def _mean(values: list[float]) -> float | None:
    return round(fmean(values), 4) if values else None


def summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    selected_counts: Counter[str] = Counter()
    summaries: dict[str, Any] = {"case_count": len(cases)}
    for extractor in (*EXTRACTORS, "auto"):
        quality_scores: list[float] = []
        reference_f1: list[float] = []
        usable_count = 0
        success_count = 0
        for case in cases:
            result = case["results"][extractor]
            if result.get("status") == "ok":
                success_count += 1
            report = result.get("quality_report") or {}
            score = _finite(report.get("score"))
            if score is not None:
                quality_scores.append(score)
            usable_count += int(bool(report.get("usable", False)))
            metrics = result.get("reference_metrics") or {}
            f1 = _finite(metrics.get("f1"))
            if f1 is not None:
                reference_f1.append(f1)
            if extractor == "auto" and result.get("selected_extractor"):
                selected_counts[result["selected_extractor"]] += 1
        summaries[extractor] = {
            "success_count": success_count,
            "usable_count": usable_count,
            "mean_quality_score": _mean(quality_scores),
            "mean_reference_f1": _mean(reference_f1),
        }
    summaries["selected_extractor_counts"] = dict(sorted(selected_counts.items()))
    return summaries


def compare_benchmark_reports(
    current: dict[str, Any],
    baseline: dict[str, Any],
    quality_tolerance: float = 2.0,
    f1_tolerance: float = 0.02,
) -> dict[str, Any]:
    """逐 case/variant 比较报告，标记新不可用或超出容差的回归。"""
    baseline_cases = {case["id"]: case for case in baseline.get("cases", [])}
    regressions: list[dict[str, Any]] = []
    deltas: list[dict[str, Any]] = []
    for current_case in current.get("cases", []):
        baseline_case = baseline_cases.get(current_case.get("id"))
        if not baseline_case:
            continue
        for variant in (*EXTRACTORS, "auto"):
            current_result = current_case.get("results", {}).get(variant) or {}
            baseline_result = baseline_case.get("results", {}).get(variant) or {}
            current_quality = current_result.get("quality_report") or {}
            baseline_quality = baseline_result.get("quality_report") or {}
            quality_delta = (_finite(current_quality.get("score")) or 0.0) - (
                _finite(baseline_quality.get("score")) or 0.0
            )
            current_f1 = _finite(
                (current_result.get("reference_metrics") or {}).get("f1")
            )
            baseline_f1 = _finite(
                (baseline_result.get("reference_metrics") or {}).get("f1")
            )
            f1_delta = (
                current_f1 - baseline_f1
                if current_f1 is not None and baseline_f1 is not None
                else None
            )
            reasons: list[str] = []
            if baseline_quality.get("usable", False) and not current_quality.get(
                "usable", False
            ):
                reasons.append("newly_unusable")
            if quality_delta < -quality_tolerance:
                reasons.append("quality_score_regression")
            if f1_delta is not None and f1_delta < -f1_tolerance:
                reasons.append("reference_f1_regression")
            delta = {
                "case_id": current_case["id"],
                "variant": variant,
                "quality_score_delta": round(quality_delta, 4),
                "reference_f1_delta": (
                    round(f1_delta, 4) if f1_delta is not None else None
                ),
                "reasons": reasons,
            }
            deltas.append(delta)
            if reasons:
                regressions.append(delta)

    return {
        "passed": not regressions,
        "quality_tolerance": quality_tolerance,
        "f1_tolerance": f1_tolerance,
        "compared_result_count": len(deltas),
        "regressions": regressions,
        "deltas": deltas,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    def result_score(result: dict[str, Any]) -> Any:
        if result.get("status") == "error":
            return "ERR"
        return (result.get("quality_report") or {}).get("score", "-")

    lines = [
        f"# Melody Benchmark: {report['dataset']}",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Cases: **{report['summary']['case_count']}**",
        f"- Mode: `{report['mode']}`",
        "",
        "| Case | Basic Pitch | librosa | Auto selected | Auto score | Reference F1 | Issues |",
        "|---|---:|---:|---|---:|---:|---|",
    ]
    for case in report["cases"]:
        results = case["results"]
        auto = results["auto"]
        quality = auto.get("quality_report") or {}
        reference = auto.get("reference_metrics") or {}
        issues = ", ".join(quality.get("issue_codes") or []) or "-"
        reference_f1 = reference.get("f1")
        lines.append(
            "| {case_id} | {basic} | {librosa} | {selected} | {score} | {f1} | {issues} |".format(
                case_id=case["id"],
                basic=result_score(results["basic_pitch"]),
                librosa=result_score(results["librosa"]),
                selected=auto.get("selected_extractor", "-"),
                score=quality.get("score", "-"),
                f1=reference_f1 if reference_f1 is not None else "-",
                issues=issues,
            )
        )

    summary = report["summary"]
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Auto mean quality score: `{summary['auto']['mean_quality_score']}`",
            f"- Auto mean reference F1: `{summary['auto']['mean_reference_f1']}`",
            f"- Selected extractors: `{json.dumps(summary['selected_extractor_counts'], ensure_ascii=False)}`",
            f"- Basic Pitch successful cases: `{summary['basic_pitch']['success_count']}/{summary['case_count']}`",
            f"- librosa successful cases: `{summary['librosa']['success_count']}/{summary['case_count']}`",
        ]
    )
    comparison = report.get("comparison")
    if comparison:
        lines.extend(
            [
                "",
                "## Baseline comparison",
                "",
                f"- Passed: **{comparison['passed']}**",
                f"- Regressions: **{len(comparison['regressions'])}**",
            ]
        )
        for regression in comparison["regressions"]:
            lines.append(
                f"- `{regression['case_id']}/{regression['variant']}`: "
                f"{', '.join(regression['reasons'])}"
            )
    return "\n".join(lines) + "\n"


async def run_benchmark(
    manifest_path: Path,
    output_dir: Path,
    *,
    reuse_predictions: bool = False,
    baseline_path: Path | None = None,
    case_ids: set[str] | None = None,
    onset_tolerance: float = 0.1,
    pitch_tolerance: int = 0,
    quality_tolerance: float = 2.0,
    f1_tolerance: float = 0.02,
    quality_evaluator: QualityEvaluator | None = None,
    candidate_selector: CandidateSelector | None = None,
    extractor_runner: ExtractorRunner | None = None,
) -> dict[str, Any]:
    if onset_tolerance < 0 or pitch_tolerance < 0:
        raise BenchmarkError("onset/pitch 匹配容差不能为负数")
    if quality_tolerance < 0 or f1_tolerance < 0:
        raise BenchmarkError("回归容差不能为负数")
    manifest = load_manifest(manifest_path)
    quality_evaluator = quality_evaluator or _load_default_quality_evaluator()
    candidate_selector = candidate_selector or _load_default_candidate_selector()
    extractor_runner = extractor_runner or _default_extractor_runner
    enabled_case_ids = {
        case["id"] for case in manifest["cases"] if case.get("enabled", True)
    }
    if case_ids:
        missing_case_ids = case_ids - enabled_case_ids
        if missing_case_ids:
            raise BenchmarkError(
                f"请求的 case 不存在或未启用: {', '.join(sorted(missing_case_ids))}"
            )
    selected_cases = [
        case
        for case in manifest["cases"]
        if case.get("enabled", True) and (not case_ids or case["id"] in case_ids)
    ]
    if not selected_cases:
        raise BenchmarkError("没有启用且匹配筛选条件的 benchmark case")

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    case_reports: list[dict[str, Any]] = []
    for case in selected_cases:
        case_output_dir = output_dir / case["id"]
        case_output_dir.mkdir(parents=True, exist_ok=True)
        reference_notes = load_reference_notes(case)
        candidate_results: dict[str, dict[str, Any]] = {}
        candidate_notes: dict[str, list[dict[str, Any]]] = {}
        for extractor in EXTRACTORS:
            result, notes = await _evaluate_candidate(
                extractor,
                case,
                case_output_dir,
                reference_notes,
                reuse_predictions,
                quality_evaluator,
                extractor_runner,
                onset_tolerance,
                pitch_tolerance,
            )
            candidate_results[extractor] = result
            candidate_notes[extractor] = notes
        auto_result = _production_selection(
            candidate_results,
            candidate_notes,
            candidate_selector,
        )
        case_report = {
            "id": case["id"],
            "tags": list(case.get("tags") or []),
            "audio_path": case.get("audio_path"),
            "reference_path": case.get("reference_path"),
            "results": {**candidate_results, "auto": auto_result},
        }
        case_reports.append(case_report)
        (case_output_dir / "result.json").write_text(
            json.dumps(case_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "dataset": manifest.get("name") or manifest_path.stem,
        "manifest_path": manifest["manifest_path"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "reuse_predictions" if reuse_predictions else "audio_extraction",
        "config": {
            "onset_tolerance": onset_tolerance,
            "pitch_tolerance": pitch_tolerance,
            "quality_tolerance": quality_tolerance,
            "f1_tolerance": f1_tolerance,
        },
        "summary": summarize_cases(case_reports),
        "cases": case_reports,
    }
    if baseline_path:
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BenchmarkError(
                f"无法读取 baseline 报告 {baseline_path}: {error}"
            ) from error
        report["comparison"] = compare_benchmark_reports(
            report,
            baseline,
            quality_tolerance=quality_tolerance,
            f1_tolerance=f1_tolerance,
        )

    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        render_markdown_report(report),
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RingTurn 旋律提取回归 benchmark")
    parser.add_argument(
        "--manifest", required=True, type=Path, help="Benchmark manifest JSON"
    )
    parser.add_argument(
        "--output-dir", required=True, type=Path, help="报告和候选产物目录"
    )
    parser.add_argument(
        "--reuse-predictions",
        action="store_true",
        help="读取 manifest 中缓存的 predictions，不运行音频模型",
    )
    parser.add_argument("--baseline", type=Path, help="用于回归比较的旧 report.json")
    parser.add_argument(
        "--case", action="append", dest="case_ids", help="只运行指定 case，可重复"
    )
    parser.add_argument("--onset-tolerance", type=float, default=0.1)
    parser.add_argument("--pitch-tolerance", type=int, default=0)
    parser.add_argument("--quality-tolerance", type=float, default=2.0)
    parser.add_argument("--f1-tolerance", type=float, default=0.02)
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="与 baseline 比较失败时返回非零退出码",
    )
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    if args.fail_on_regression and not args.baseline:
        raise BenchmarkError("--fail-on-regression 必须同时提供 --baseline")
    report = await run_benchmark(
        args.manifest,
        args.output_dir,
        reuse_predictions=args.reuse_predictions,
        baseline_path=args.baseline,
        case_ids=set(args.case_ids) if args.case_ids else None,
        onset_tolerance=args.onset_tolerance,
        pitch_tolerance=args.pitch_tolerance,
        quality_tolerance=args.quality_tolerance,
        f1_tolerance=args.f1_tolerance,
    )
    print(f"Benchmark JSON: {args.output_dir.resolve() / 'report.json'}")
    print(f"Benchmark Markdown: {args.output_dir.resolve() / 'report.md'}")
    comparison = report.get("comparison")
    if args.fail_on_regression and comparison and not comparison["passed"]:
        return 2
    case_count = report["summary"]["case_count"]
    if any(
        report["summary"][extractor]["success_count"] < case_count
        for extractor in EXTRACTORS
    ):
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_async_main(args))
    except BenchmarkError as error:
        print(f"Benchmark failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
