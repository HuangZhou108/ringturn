"""旋律 benchmark 核心逻辑测试，不依赖音频模型。"""

import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).parent.parent / "evaluation" / "melody_benchmark.py"
_SPEC = importlib.util.spec_from_file_location("melody_benchmark", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"无法加载旋律 benchmark 模块: {_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

BenchmarkError = _MODULE.BenchmarkError
compare_benchmark_reports = _MODULE.compare_benchmark_reports
load_manifest = _MODULE.load_manifest
match_melody_notes = _MODULE.match_melody_notes
render_markdown_report = _MODULE.render_markdown_report
run_benchmark = _MODULE.run_benchmark
production_selection = _MODULE._production_selection


def _note(pitch, start, end):
    return {"pitch": pitch, "start": start, "end": end, "confidence": 0.9}


class MelodyMatchingTests(unittest.TestCase):
    def test_exact_notes_score_one(self):
        notes = [_note(60, 0.0, 0.5), _note(62, 0.5, 1.0)]

        result = match_melody_notes(notes, notes)

        self.assertEqual(result["precision"], 1.0)
        self.assertEqual(result["recall"], 1.0)
        self.assertEqual(result["f1"], 1.0)
        self.assertEqual(result["mean_onset_error_ms"], 0.0)

    def test_matching_is_one_to_one(self):
        predicted = [_note(60, 0.0, 0.5), _note(60, 0.03, 0.55)]
        reference = [_note(60, 0.02, 0.52)]

        result = match_melody_notes(predicted, reference, onset_tolerance=0.1)

        self.assertEqual(result["matched_note_count"], 1)
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 1.0)

    def test_pitch_mismatch_is_not_counted(self):
        result = match_melody_notes(
            [_note(61, 0.0, 0.5)],
            [_note(60, 0.0, 0.5)],
        )

        self.assertEqual(result["f1"], 0.0)


class ManifestTests(unittest.TestCase):
    def test_resolves_paths_relative_to_manifest(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "case-a",
                                "audio_path": "audio/a.wav",
                                "predictions": {"basic_pitch": "pred/a.json"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            manifest = load_manifest(manifest_path)

            self.assertEqual(
                manifest["cases"][0]["audio_path"],
                str((root / "audio/a.wav").resolve()),
            )
            self.assertEqual(
                manifest["cases"][0]["predictions"]["basic_pitch"],
                str((root / "pred/a.json").resolve()),
            )

    def test_rejects_duplicate_case_ids(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [{"id": "same"}, {"id": "same"}],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(BenchmarkError, "重复"):
                load_manifest(path)

    def test_rejects_unsafe_case_id(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "manifest.json"
            path.write_text(
                json.dumps({"version": 1, "cases": [{"id": "../escape"}]}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(BenchmarkError, "只能包含"):
                load_manifest(path)

    def test_rejects_invalid_analysis_settings(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [{"id": "case-a", "analysis": {"bpm": 0}}],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(BenchmarkError, "BPM"):
                load_manifest(path)


class BenchmarkReportTests(unittest.TestCase):
    def test_auto_route_retains_passing_primary(self):
        results = {
            "basic_pitch": {
                "status": "ok",
                "quality_report": {"score": 80.0, "passed": True, "usable": True},
                "reference_metrics": None,
                "error": None,
            },
            "librosa": {
                "status": "ok",
                "quality_report": {"score": 95.0, "passed": True, "usable": True},
                "reference_metrics": None,
                "error": None,
            },
        }

        auto = production_selection(
            results,
            {"basic_pitch": [_note(60, 0.0, 0.5)], "librosa": [_note(62, 0.0, 0.5)]},
            _MODULE._load_default_candidate_selector(),
        )

        self.assertEqual(auto["selected_extractor"], "basic_pitch")
        self.assertEqual(auto["selection_reason"], "primary_passed")

    def test_auto_route_uses_fallback_when_primary_fails(self):
        results = {
            "basic_pitch": {
                "status": "ok",
                "quality_report": {"score": 60.0, "passed": False, "usable": True},
                "reference_metrics": None,
                "error": None,
            },
            "librosa": {
                "status": "ok",
                "quality_report": {"score": 90.0, "passed": True, "usable": True},
                "reference_metrics": None,
                "error": None,
            },
        }

        auto = production_selection(
            results,
            {"basic_pitch": [_note(60, 0.0, 0.5)], "librosa": [_note(62, 0.0, 0.5)]},
            _MODULE._load_default_candidate_selector(),
        )

        self.assertEqual(auto["selected_extractor"], "librosa")

    def test_cached_predictions_generate_reports(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            reference = [_note(60, 0.0, 0.5), _note(62, 0.5, 1.0)]
            basic = [_note(60, 0.0, 0.5), _note(62, 0.5, 1.0)]
            librosa = [_note(60, 0.0, 0.5)]
            for name, notes in {
                "reference": reference,
                "basic": basic,
                "librosa": librosa,
            }.items():
                (root / f"{name}.json").write_text(
                    json.dumps({"melody_notes": notes}),
                    encoding="utf-8",
                )
            manifest = {
                "version": 1,
                "name": "unit-dataset",
                "cases": [
                    {
                        "id": "scale",
                        "audio_duration": 1.0,
                        "reference_path": "reference.json",
                        "predictions": {
                            "basic_pitch": "basic.json",
                            "librosa": "librosa.json",
                        },
                    }
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            output_dir = root / "out"

            report = asyncio.run(
                run_benchmark(
                    manifest_path,
                    output_dir,
                    reuse_predictions=True,
                )
            )

            self.assertEqual(report["summary"]["case_count"], 1)
            self.assertEqual(
                report["cases"][0]["results"]["auto"]["selected_extractor"],
                "basic_pitch",
            )
            self.assertEqual(
                report["cases"][0]["results"]["auto"]["reference_metrics"]["f1"],
                1.0,
            )
            self.assertTrue((output_dir / "report.json").is_file())
            self.assertTrue((output_dir / "report.md").is_file())

    def test_comparison_detects_reference_regression(self):
        def report(f1):
            result = {
                "quality_report": {"score": 90.0, "usable": True},
                "reference_metrics": {"f1": f1},
            }
            return {
                "cases": [
                    {
                        "id": "case-a",
                        "results": {
                            "basic_pitch": result,
                            "librosa": result,
                            "auto": result,
                        },
                    }
                ]
            }

        comparison = compare_benchmark_reports(report(0.7), report(0.9))

        self.assertFalse(comparison["passed"])
        self.assertEqual(len(comparison["regressions"]), 3)
        self.assertIn(
            "reference_f1_regression",
            comparison["regressions"][0]["reasons"],
        )

    def test_markdown_contains_selected_extractor(self):
        report = {
            "dataset": "demo",
            "generated_at": "now",
            "mode": "reuse_predictions",
            "summary": {
                "case_count": 1,
                "basic_pitch": {"success_count": 1},
                "librosa": {"success_count": 1},
                "auto": {"mean_quality_score": 90.0, "mean_reference_f1": 1.0},
                "selected_extractor_counts": {"basic_pitch": 1},
            },
            "cases": [
                {
                    "id": "case-a",
                    "results": {
                        "basic_pitch": {"quality_report": {"score": 90.0}},
                        "librosa": {"quality_report": {"score": 80.0}},
                        "auto": {
                            "selected_extractor": "basic_pitch",
                            "quality_report": {"score": 90.0, "issue_codes": []},
                            "reference_metrics": {"f1": 1.0},
                        },
                    },
                }
            ],
        }

        markdown = render_markdown_report(report)

        self.assertIn("basic_pitch", markdown)
        self.assertIn("Reference F1", markdown)


if __name__ == "__main__":
    unittest.main()
