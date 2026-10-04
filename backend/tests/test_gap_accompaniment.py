"""长休止伴奏策略的无外部依赖单元测试。"""

import importlib.util
import unittest
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).parent.parent
    / "app"
    / "agent"
    / "atomic_tools"
    / "arrangement"
    / "gap_accompaniment.py"
)
_MODULE_SPEC = importlib.util.spec_from_file_location("gap_accompaniment", _MODULE_PATH)
if _MODULE_SPEC is None or _MODULE_SPEC.loader is None:
    raise ImportError(f"无法加载长休止伴奏策略模块: {_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_MODULE_SPEC)
_MODULE_SPEC.loader.exec_module(_MODULE)
plan_gap_accompaniment = _MODULE.plan_gap_accompaniment
select_accompaniment_channels = _MODULE.select_accompaniment_channels


class GapAccompanimentPlanTests(unittest.TestCase):
    def test_selects_free_non_drum_midi_channels(self):
        bass_channel, pad_channel = select_accompaniment_channels({0, 1, 9})

        self.assertEqual((bass_channel, pad_channel), (2, 3))
        self.assertNotEqual(bass_channel, pad_channel)
        self.assertNotIn(9, (bass_channel, pad_channel))

    def test_fills_only_gap_remaining_after_sustain(self):
        plan = plan_gap_accompaniment(
            melody_notes=[
                {"start": 0.0, "end": 0.5},
                {"start": 3.0, "end": 3.5},
            ],
            chords=[{"start": 0.0, "end": 4.0, "root_midi": 60}],
            key_midi=60,
        )

        self.assertEqual(plan["reason"], "validated_chords")
        self.assertEqual(plan["gap_count"], 1)
        self.assertEqual(
            plan["segments"],
            [
                {
                    "start": 1.5,
                    "end": 3.0,
                    "root_midi": 60,
                    "source": "validated_chord",
                }
            ],
        )

    def test_ignores_short_vocal_breath(self):
        plan = plan_gap_accompaniment(
            melody_notes=[
                {"start": 0.0, "end": 0.5},
                {"start": 2.0, "end": 2.5},
            ],
            chords=[{"start": 0.0, "end": 3.0, "root_midi": 60}],
            key_midi=60,
        )

        self.assertEqual(plan["segments"], [])
        self.assertEqual(plan["reason"], "no_long_gaps")

    def test_aligns_chords_after_leading_silence_is_removed(self):
        plan = plan_gap_accompaniment(
            melody_notes=[
                {"start": 10.0, "end": 10.5},
                {"start": 13.0, "end": 13.5},
            ],
            chords=[{"start": 10.0, "end": 14.0, "root_midi": 67}],
            key_midi=60,
        )

        self.assertEqual(plan["timeline_offset"], 10.0)
        self.assertEqual(plan["segments"][0]["start"], 1.5)
        self.assertEqual(plan["segments"][0]["end"], 3.0)
        self.assertEqual(plan["segments"][0]["root_midi"], 67)

    def test_rejects_out_of_key_chords_and_uses_tonic(self):
        plan = plan_gap_accompaniment(
            melody_notes=[
                {"start": 0.0, "end": 0.5},
                {"start": 3.0, "end": 3.5},
            ],
            chords=[{"start": 0.0, "end": 4.0, "root_midi": 61}],
            key_midi=60,
            mode="major",
        )

        self.assertEqual(plan["in_key_ratio"], 0.0)
        self.assertEqual(plan["reason"], "key_fallback")
        self.assertEqual(plan["segments"][0]["root_midi"], 60)
        self.assertEqual(plan["segments"][0]["source"], "key_tonic_fallback")

    def test_repeats_gap_plan_when_short_melody_is_looped(self):
        plan = plan_gap_accompaniment(
            melody_notes=[
                {"start": 0.0, "end": 0.5},
                {"start": 3.0, "end": 3.5},
            ],
            chords=[{"start": 0.0, "end": 4.0, "root_midi": 60}],
            key_midi=60,
            target_duration=8.0,
        )

        self.assertEqual(plan["gap_count"], 2)
        self.assertEqual(
            [(segment["start"], segment["end"]) for segment in plan["segments"]],
            [(1.5, 3.0), (5.0, 6.5)],
        )

    def test_skips_when_harmony_and_key_are_unavailable(self):
        plan = plan_gap_accompaniment(
            melody_notes=[
                {"start": 0.0, "end": 0.5},
                {"start": 3.0, "end": 3.5},
            ],
            chords=[],
            key_midi=None,
        )

        self.assertEqual(plan["segments"], [])
        self.assertEqual(plan["reason"], "no_reliable_harmony")

    def test_ignores_malformed_notes_and_chords(self):
        plan = plan_gap_accompaniment(
            melody_notes=[
                {"start": "bad", "end": 0.5},
                {"start": 0.0, "end": 0.5},
                {"start": 3.0, "end": 3.5},
            ],
            chords=[
                {"start": 0.0, "end": 4.0, "root_midi": 999},
                {"start": 0.0, "end": 4.0, "root_midi": 65},
            ],
            key_midi=65,
        )

        self.assertEqual(plan["valid_chord_count"], 1)
        self.assertEqual(plan["segments"][0]["root_midi"], 65)


if __name__ == "__main__":
    unittest.main()
