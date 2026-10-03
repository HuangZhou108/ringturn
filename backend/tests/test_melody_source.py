"""旋律与和声输入源选择的轻量单元测试。"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).parent.parent / "app" / "agent" / "melody_source.py"
_MODULE_SPEC = importlib.util.spec_from_file_location("melody_source", _MODULE_PATH)
if _MODULE_SPEC is None or _MODULE_SPEC.loader is None:
    raise ImportError(f"无法加载旋律源选择模块: {_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_MODULE_SPEC)
_MODULE_SPEC.loader.exec_module(_MODULE)
select_melody_sources = _MODULE.select_melody_sources


class MelodySourceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _audio_file(self, filename: str) -> str:
        path = self.tmp_path / filename
        path.touch()
        return str(path)

    def test_prefers_vocals_for_melody_and_accompaniment_for_harmony(self):
        original = self._audio_file("song.wav")
        vocals = self._audio_file("vocals.wav")
        accompaniment = self._audio_file("other.wav")

        result = select_melody_sources(
            original_audio_path=original,
            vocals_path=vocals,
            accompaniment_path=accompaniment,
            demucs_separated=True,
        )

        self.assertEqual(
            result,
            {
                "melody_source_path": vocals,
                "harmony_source_path": accompaniment,
                "reason": "demucs_vocals",
            },
        )

    def test_missing_vocals_falls_back_to_original_but_keeps_harmony_stem(self):
        original = self._audio_file("song.wav")
        accompaniment = self._audio_file("other.wav")

        result = select_melody_sources(
            original_audio_path=original,
            vocals_path=str(self.tmp_path / "missing-vocals.wav"),
            accompaniment_path=accompaniment,
            demucs_separated=True,
        )

        self.assertEqual(result["melody_source_path"], original)
        self.assertEqual(result["harmony_source_path"], accompaniment)
        self.assertEqual(result["reason"], "original_audio_fallback")

    def test_ignores_stale_stems_when_separation_was_not_successful(self):
        original = self._audio_file("song.wav")
        vocals = self._audio_file("vocals.wav")
        accompaniment = self._audio_file("other.wav")

        result = select_melody_sources(
            original_audio_path=original,
            vocals_path=vocals,
            accompaniment_path=accompaniment,
            demucs_separated=False,
        )

        self.assertEqual(result["melody_source_path"], original)
        self.assertEqual(result["harmony_source_path"], original)
        self.assertEqual(result["reason"], "original_audio")

    def test_vocals_keep_priority_when_accompaniment_is_missing(self):
        original = self._audio_file("song.wav")
        vocals = self._audio_file("vocals.wav")

        result = select_melody_sources(
            original_audio_path=original,
            vocals_path=vocals,
            accompaniment_path=str(self.tmp_path / "missing-other.wav"),
            demucs_separated=True,
        )

        self.assertEqual(result["melody_source_path"], vocals)
        self.assertEqual(result["harmony_source_path"], original)

    def test_accompaniment_is_only_a_last_resort_when_original_is_missing(self):
        accompaniment = self._audio_file("other.wav")

        result = select_melody_sources(
            original_audio_path=str(self.tmp_path / "missing-song.wav"),
            vocals_path=str(self.tmp_path / "missing-vocals.wav"),
            accompaniment_path=accompaniment,
            demucs_separated=True,
        )

        self.assertEqual(result["melody_source_path"], accompaniment)
        self.assertEqual(result["harmony_source_path"], accompaniment)
        self.assertEqual(result["reason"], "accompaniment_last_resort")

    def test_raises_when_no_audio_source_exists(self):
        with self.assertRaisesRegex(ValueError, "没有可用的旋律提取音频"):
            select_melody_sources(
                original_audio_path=str(self.tmp_path / "missing-song.wav"),
                vocals_path=str(self.tmp_path / "missing-vocals.wav"),
                accompaniment_path=str(self.tmp_path / "missing-other.wav"),
                demucs_separated=True,
            )


if __name__ == "__main__":
    unittest.main()
