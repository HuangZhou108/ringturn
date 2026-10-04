"""旋律候选选择策略的轻量单元测试。"""

import importlib.util
import json
import unittest
from copy import deepcopy
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).parent.parent
    / "app"
    / "agent"
    / "atomic_tools"
    / "melody"
    / "candidate_selection.py"
)
_SPEC = importlib.util.spec_from_file_location("candidate_selection", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"无法加载旋律候选选择模块: {_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
select_best_melody_candidate = _MODULE.select_best_melody_candidate
should_run_fallback_candidate = _MODULE.should_run_fallback_candidate


def _candidate(score, passed=True, usable=True, note_count=8, error=None):
    return {
        "melody_data": {
            "melody_notes": [{"pitch": 60, "start": 0.0, "end": 0.5}],
            "extraction_error": error,
        },
        "quality_report": {
            "score": score,
            "passed": passed,
            "usable": usable,
            "issue_codes": [] if passed else ["fragmented_notes"],
            "metrics": {"note_count": note_count},
        },
    }


class MelodyCandidateSelectionTests(unittest.TestCase):
    def test_runs_fallback_only_for_unpassed_primary(self):
        self.assertTrue(
            should_run_fallback_candidate(
                "basic_pitch",
                {"passed": False},
                {"basic_pitch": _candidate(60.0, passed=False)},
            )
        )
        self.assertFalse(
            should_run_fallback_candidate(
                "basic_pitch",
                {"passed": True},
                {"basic_pitch": _candidate(85.0)},
            )
        )
        self.assertFalse(
            should_run_fallback_candidate(
                "librosa",
                {"passed": False},
                {
                    "basic_pitch": _candidate(60.0, passed=False),
                    "librosa": _candidate(55.0, passed=False),
                },
            )
        )

    def test_keeps_single_primary_candidate(self):
        result = select_best_melody_candidate(
            {"basic_pitch": _candidate(92.0)}
        )

        self.assertEqual(result["selected_extractor"], "basic_pitch")
        self.assertEqual(result["reason"], "single_candidate")

    def test_selects_passing_fallback_over_failing_primary(self):
        result = select_best_melody_candidate(
            {
                "basic_pitch": _candidate(68.0, passed=False),
                "librosa": _candidate(82.0),
            }
        )

        self.assertEqual(result["selected_extractor"], "librosa")
        self.assertEqual(result["reason"], "fallback_higher_quality")

    def test_usable_candidate_beats_higher_scoring_unusable_candidate(self):
        result = select_best_melody_candidate(
            {
                "basic_pitch": _candidate(95.0, passed=False, usable=False),
                "librosa": _candidate(60.0, passed=False, usable=True),
            }
        )

        self.assertEqual(result["selected_extractor"], "librosa")

    def test_passing_candidate_beats_higher_scoring_warning_candidate(self):
        result = select_best_melody_candidate(
            {
                "basic_pitch": _candidate(88.0, passed=False),
                "librosa": _candidate(75.0, passed=True),
            }
        )

        self.assertEqual(result["selected_extractor"], "librosa")

    def test_tie_prefers_basic_pitch(self):
        result = select_best_melody_candidate(
            {
                "librosa": _candidate(80.0),
                "basic_pitch": _candidate(80.0),
            }
        )

        self.assertEqual(result["selected_extractor"], "basic_pitch")
        self.assertEqual(result["reason"], "primary_retained")

    def test_returns_compact_candidate_summaries(self):
        result = select_best_melody_candidate(
            {
                "basic_pitch": _candidate(50.0, passed=False, error="model failed"),
                "librosa": _candidate(81.0, note_count=12),
            }
        )

        self.assertEqual(result["candidate_summaries"]["librosa"]["note_count"], 12)
        self.assertEqual(
            result["candidate_summaries"]["basic_pitch"]["error"],
            "model failed",
        )
        self.assertNotIn(
            "melody_notes",
            result["candidate_summaries"]["basic_pitch"],
        )

    def test_does_not_mutate_candidates(self):
        candidates = {
            "basic_pitch": _candidate(70.0, passed=False),
            "librosa": _candidate(80.0),
        }
        original = deepcopy(candidates)

        result = select_best_melody_candidate(candidates)
        result["melody_data"]["melody_notes"][0]["pitch"] = 72

        self.assertEqual(candidates, original)

    def test_rejects_missing_candidates(self):
        with self.assertRaisesRegex(ValueError, "没有可供选择"):
            select_best_melody_candidate({})


class MelodyCandidateGraphConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_path = (
            Path(__file__).parent.parent
            / "app"
            / "agent"
            / "tool_graphs"
            / "extract_graph.json"
        )
        cls.config = json.loads(config_path.read_text(encoding="utf-8"))

    def test_candidate_nodes_precede_quality_gate(self):
        default_edges = {
            (edge["from"], edge["to"])
            for edge in self.config["default_edges"]
        }

        self.assertIn(("snap", "evaluate_candidate"), default_edges)
        self.assertIn(("select_candidate", "ensure_midi"), default_edges)
        self.assertNotIn(("snap", "ensure_midi"), default_edges)

    def test_candidate_route_can_only_fallback_or_select(self):
        edge = next(
            item
            for item in self.config["conditional_edges"]
            if item["condition"] == "extract_route_after_candidate"
        )

        self.assertEqual(edge["from"], "evaluate_candidate")
        self.assertEqual(
            edge["mapping"],
            {
                "librosa_fallback": "librosa_fallback",
                "select_candidate": "select_candidate",
            },
        )


if __name__ == "__main__":
    unittest.main()
