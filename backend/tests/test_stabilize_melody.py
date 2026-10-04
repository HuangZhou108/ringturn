"""量化前旋律稳定化的轻量单元测试。"""

import importlib.util
import unittest
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).parent.parent
    / "app"
    / "agent"
    / "atomic_tools"
    / "melody"
    / "stabilize_notes.py"
)
_MODULE_SPEC = importlib.util.spec_from_file_location("stabilize_notes", _MODULE_PATH)
if _MODULE_SPEC is None or _MODULE_SPEC.loader is None:
    raise ImportError(f"无法加载旋律稳定化模块: {_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_MODULE_SPEC)
_MODULE_SPEC.loader.exec_module(_MODULE)
stabilize_melody_notes = _MODULE.stabilize_melody_notes


def _note(pitch, start, end, confidence=0.8):
    return {
        "pitch": pitch,
        "start": start,
        "end": end,
        "velocity": 90,
        "confidence": confidence,
    }


class StabilizeMelodyTests(unittest.TestCase):
    def test_removes_sub_threshold_fragments_before_quantization(self):
        notes = [_note(60, 0.0, 0.04), _note(62, 0.2, 0.5)]

        result = stabilize_melody_notes(notes, min_duration=0.1)

        self.assertEqual([note["pitch"] for note in result], [62])

    def test_selects_one_reliable_pitch_from_same_onset(self):
        notes = [
            _note(72, 0.0, 0.3, confidence=0.45),
            _note(60, 0.01, 0.5, confidence=0.9),
        ]

        result = stabilize_melody_notes(notes)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pitch"], 60)

    def test_collapses_short_returning_pitch_blip(self):
        notes = [
            _note(60, 0.0, 0.4),
            _note(62, 0.4, 0.52),
            _note(60, 0.52, 1.0),
        ]

        result = stabilize_melody_notes(notes)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pitch"], 60)
        self.assertEqual(result[0]["start"], 0.0)
        self.assertEqual(result[0]["end"], 1.0)

    def test_preserves_directional_fast_melody(self):
        notes = [
            _note(60, 0.0, 0.12),
            _note(62, 0.12, 0.24),
            _note(64, 0.24, 0.36),
            _note(65, 0.36, 0.48),
        ]

        result = stabilize_melody_notes(notes)

        self.assertEqual([note["pitch"] for note in result], [60, 62, 64, 65])

    def test_preserves_short_intervallic_ornament(self):
        notes = [
            _note(60, 0.0, 0.4),
            _note(67, 0.4, 0.52),
            _note(60, 0.52, 1.0),
        ]

        result = stabilize_melody_notes(notes)

        self.assertEqual([note["pitch"] for note in result], [60, 67, 60])

    def test_merges_same_pitch_fragments_across_tiny_gap(self):
        notes = [_note(60, 0.0, 0.4), _note(60, 0.45, 0.9)]

        result = stabilize_melody_notes(notes, merge_gap=0.1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["end"], 0.9)

    def test_does_not_bridge_a_meaningful_rest(self):
        notes = [_note(60, 0.0, 0.4), _note(60, 0.6, 1.0)]

        result = stabilize_melody_notes(notes, merge_gap=0.1)

        self.assertEqual(len(result), 2)

    def test_does_not_mutate_input_and_ignores_invalid_notes(self):
        valid = _note(60, 0.0, 0.5)
        notes = [valid, {"pitch": 62, "start": "bad", "end": 0.8}]

        result = stabilize_melody_notes(notes)

        self.assertEqual(result, [valid])
        self.assertIsNot(result[0], valid)
        self.assertEqual(valid["end"], 0.5)


if __name__ == "__main__":
    unittest.main()
