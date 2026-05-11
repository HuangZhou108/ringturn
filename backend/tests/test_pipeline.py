"""测试 atomic_tools 音频处理流程"""

import asyncio
import os
import sys
from pathlib import Path

import pytest
import numpy as np
import scipy.io.wavfile as wavfile

sys.path.insert(0, str(Path(__file__).parent.parent))


def _check_soundfont():
    """检查 FluidSynth 音色库是否存在"""
    sf_paths = [
        "/usr/share/sounds/sf2/default.sf2",
        "/usr/share/sounds/sf2/GeneralUser_GS.sf2",
        "/usr/share/fluidsynth/soundfonts/FluidR3_GM.sf2",
        os.environ.get("SOUNDFONT_PATH", ""),
    ]
    return any(os.path.exists(p) for p in sf_paths if p)


def _check_basic_pitch():
    """检查 basic-pitch 模型是否可用"""
    try:
        from basic_pitch.inference import predict
        return True
    except Exception:
        return False


has_soundfont = pytest.mark.skipif(
    not _check_soundfont(),
    reason="FluidSynth 音色库未安装，跳过渲染测试"
)

has_basic_pitch = pytest.mark.skipif(
    not _check_basic_pitch(),
    reason="Basic Pitch 模型不可用"
)


def _generate_sine_wave(tmp_path: Path, frequency: float = 440.0, duration: float = 2.0) -> Path:
    """生成测试用正弦波音频"""
    sample_rate = 16000
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    audio = (np.sin(2 * np.pi * frequency * t) * 32767 * 0.5).astype(np.int16)
    audio_path = tmp_path / "sample.wav"
    wavfile.write(str(audio_path), sample_rate, audio)
    return audio_path


# ============================
# 1. 旋律提取测试
# ============================
@pytest.mark.asyncio
@has_basic_pitch
async def test_extract_melody_basic_pitch(tmp_path):
    """测试 Basic Pitch 旋律提取"""
    audio_path = _generate_sine_wave(tmp_path)

    from app.agent.atomic_tools.melody.extract_with_basic_pitch import extract_melody_basic_pitch
    result = await extract_melody_basic_pitch(str(audio_path))

    assert "melody_notes" in result
    assert isinstance(result["melody_notes"], list)
    assert "confidence" in result
    assert "midi_path" in result
    assert os.path.exists(result["midi_path"])


@pytest.mark.asyncio
async def test_extract_melody_librosa(tmp_path):
    """测试 librosa 旋律提取"""
    audio_path = _generate_sine_wave(tmp_path)

    from app.agent.atomic_tools.melody.extract_with_librosa import extract_melody_librosa
    result = await extract_melody_librosa(str(audio_path))

    assert "melody_notes" in result
    assert isinstance(result["melody_notes"], list)


# ============================
# 2. MIDI 生成测试
# ============================
@pytest.mark.asyncio
async def test_create_midi_from_notes(tmp_path):
    """测试从音符列表生成 MIDI"""
    notes = [
        {"pitch": 60, "start": 0.0, "end": 0.5, "velocity": 80},
        {"pitch": 64, "start": 0.5, "end": 1.0, "velocity": 80},
        {"pitch": 67, "start": 1.0, "end": 1.5, "velocity": 80},
    ]
    midi_path = tmp_path / "test.mid"

    from app.agent.atomic_tools.midi.create_from_notes import create_midi_from_notes
    result = await create_midi_from_notes(
        notes=notes,
        bpm=120.0,
        output_path=str(midi_path)
    )

    assert result == str(midi_path)
    assert os.path.exists(result)

    # 验证 MIDI 文件有效性
    import mido
    mid = mido.MidiFile(result)
    assert len(mid.tracks) > 0


# ============================
# 3. MIDI 验证测试
# ============================
@pytest.mark.asyncio
async def test_validate_midi_file(tmp_path):
    """测试 MIDI 文件验证"""
    notes = [
        {"pitch": 60, "start": 0.0, "end": 0.5, "velocity": 80},
    ]
    midi_path = tmp_path / "test.mid"

    from app.agent.atomic_tools.midi.create_from_notes import create_midi_from_notes
    from app.agent.atomic_tools.midi.validate_midi import validate_midi_file
    await create_midi_from_notes(notes=notes, bpm=120.0, output_path=str(midi_path))

    result = await validate_midi_file(str(midi_path))

    assert isinstance(result, bool)
    assert result is True


# ============================
# 4. 渲染测试（需要音色库）
# ============================
@pytest.mark.asyncio
@has_soundfont
async def test_render_midi_with_fluidsynth(tmp_path):
    """测试 FluidSynth MIDI 渲染"""
    notes = [
        {"pitch": 60, "start": 0.0, "end": 0.5, "velocity": 80},
        {"pitch": 64, "start": 0.5, "end": 1.0, "velocity": 80},
    ]
    midi_path = tmp_path / "test.mid"
    wav_path = tmp_path / "test.wav"

    from app.agent.atomic_tools.midi.create_from_notes import create_midi_from_notes
    from app.agent.atomic_tools.rendering.fluidsynth_render import render_midi_with_fluidsynth

    await create_midi_from_notes(notes=notes, bpm=120.0, output_path=str(midi_path))

    # 获取 soundfont 路径
    soundfont_paths = [
        "/usr/share/sounds/sf2/default.sf2",
        "/usr/share/sounds/sf2/GeneralUser_GS.sf2",
        "/usr/share/fluidsynth/soundfonts/FluidR3_GM.sf2",
        os.environ.get("SOUNDFONT_PATH", ""),
    ]
    soundfont_path = next(p for p in soundfont_paths if p and os.path.exists(p))

    result = await render_midi_with_fluidsynth(
        midi_path=str(midi_path),
        soundfont_path=soundfont_path,
        output_wav_path=str(wav_path),
        duration_limit=5.0
    )

    assert result == str(wav_path)
    assert os.path.exists(result)


# ============================
# 5. 完整流程测试（需要音色库和 basic-pitch）
# ============================
@pytest.mark.asyncio
@has_soundfont
@has_basic_pitch
async def test_pipeline_end_to_end(tmp_path):
    """端到端测试：音频 -> 旋律提取 -> MIDI -> 渲染"""
    audio_path = _generate_sine_wave(tmp_path)

    from app.agent.atomic_tools.melody.extract_with_basic_pitch import extract_melody_basic_pitch
    from app.agent.atomic_tools.midi.create_from_notes import create_midi_from_notes
    from app.agent.atomic_tools.rendering.fluidsynth_render import render_midi_with_fluidsynth

    # 1. 提取旋律
    melody_result = await extract_melody_basic_pitch(str(audio_path))
    assert "melody_notes" in melody_result
    assert len(melody_result["melody_notes"]) > 0

    # 2. 生成 MIDI
    midi_path = tmp_path / "test.mid"
    midi_result = await create_midi_from_notes(
        notes=melody_result["melody_notes"],
        bpm=120.0,
        output_path=str(midi_path)
    )
    assert os.path.exists(midi_result)

    # 3. 渲染音频
    wav_path = tmp_path / "test.wav"
    soundfont_paths = [
        "/usr/share/sounds/sf2/default.sf2",
        "/usr/share/sounds/sf2/GeneralUser_GS.sf2",
        "/usr/share/fluidsynth/soundfonts/FluidR3_GM.sf2",
        os.environ.get("SOUNDFONT_PATH", ""),
    ]
    soundfont_path = next(p for p in soundfont_paths if p and os.path.exists(p))

    final_audio = await render_midi_with_fluidsynth(
        midi_path=midi_result,
        soundfont_path=soundfont_path,
        output_wav_path=str(wav_path),
        duration_limit=30.0
    )
    assert os.path.exists(final_audio)
