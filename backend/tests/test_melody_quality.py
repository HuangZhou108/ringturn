"""旋律质量指标与门禁的轻量单元测试。"""

import importlib.util
import unittest
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).parent.parent
    / "app"
    / "agent"
    / "atomic_tools"
    / "quality"
    / "melody_quality.py"
)
_SPEC = importlib.util.spec_from_file_location("melody_quality", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"无法加载旋律质量模块: {_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
evaluate_melody_quality = _MODULE.evaluate_melody_quality


def _note(pitch, start, end, confidence=0.85):
    return {
        "pitch": pitch,
        "start": start,
        "end": end,
        "velocity": 90,
        "confidence": confidence,
    }


class MelodyQualityTests(unittest.TestCase):
    def test_clean_melody_passes(self):
        notes = [
            _note(60, 0.0, 0.45),
            _note(62, 0.5, 0.95),
            _note(64, 1.0, 1.45),
            _note(65, 1.5, 1.95),
            _note(67, 2.0, 2.45),
            _note(65, 2.5, 2.95),
        ]

        report = evaluate_melody_quality(notes, audio_duration=3.0)

        self.assertTrue(report["passed"])
        self.assertTrue(report["usable"])
        self.assertGreaterEqual(report["score"], 90)
        self.assertEqual(report["issue_codes"], [])

    def test_fragmented_notes_are_detected(self):
        notes = [
            _note(60 + index % 3, index * 0.1, index * 0.1 + 0.05)
            for index in range(20)
        ]

        report = evaluate_melody_quality(notes, audio_duration=2.0)

        self.assertFalse(report["passed"])
        self.assertTrue(report["usable"])
        self.assertIn("fragmented_notes", report["issue_codes"])

    def test_empty_result_is_blocked(self):
        report = evaluate_melody_quality([], audio_duration=30.0)

        self.assertFalse(report["passed"])
        self.assertFalse(report["usable"])
        self.assertEqual(report["issue_codes"], ["no_valid_notes"])

    def test_mostly_invalid_notes_are_blocked(self):
        notes = [
            _note(60, 0.0, 0.5),
            {"pitch": 200, "start": 0.5, "end": 1.0},
            {"pitch": 62, "start": 1.0, "end": 0.5},
        ]

        report = evaluate_melody_quality(notes)

        self.assertFalse(report["usable"])
        self.assertIn("invalid_notes", report["issue_codes"])

    def test_extreme_overlap_is_blocked(self):
        notes = [_note(60 + index, 0.0, 1.0) for index in range(6)]

        report = evaluate_melody_quality(notes, audio_duration=2.0)

        self.assertFalse(report["usable"])
        self.assertIn("overlapping_notes", report["issue_codes"])

    def test_near_zero_source_coverage_is_blocked(self):
        notes = [_note(60, 10.0, 10.15)]

        report = evaluate_melody_quality(notes, audio_duration=30.0)

        self.assertFalse(report["usable"])
        self.assertIn("low_melody_coverage", report["issue_codes"])

    def test_meaningful_vocal_rests_do_not_fail_gate(self):
        notes = [
            _note(60, 1.0, 2.0),
            _note(62, 5.0, 6.0),
            _note(64, 10.0, 11.0),
            _note(65, 20.0, 21.0),
        ]

        report = evaluate_melody_quality(notes, audio_duration=30.0)

        self.assertTrue(report["usable"])
        self.assertNotIn("low_melody_coverage", report["issue_codes"])

    def test_extreme_octave_errors_are_reported(self):
        notes = [
            _note(60, 0.0, 0.4),
            _note(96, 0.5, 0.9),
            _note(61, 1.0, 1.4),
            _note(97, 1.5, 1.9),
        ]

        report = evaluate_melody_quality(notes, audio_duration=2.0)

        self.assertFalse(report["passed"])
        self.assertIn("extreme_pitch_leaps", report["issue_codes"])
        self.assertIn("excessive_pitch_range", report["issue_codes"])

    def test_report_is_deterministic_and_versioned(self):
        notes = [_note(60, 0.0, 0.5), _note(62, 0.5, 1.0)]

        first = evaluate_melody_quality(notes)
        second = evaluate_melody_quality(list(reversed(notes)))

        self.assertEqual(first, second)
        self.assertEqual(first["version"], 1)

    def test_rejects_invalid_short_note_threshold(self):
        with self.assertRaisesRegex(ValueError, "short_note_threshold"):
            evaluate_melody_quality([_note(60, 0.0, 0.5)], short_note_threshold=0)


if __name__ == "__main__":
    unittest.main()
