"""测试音频->MIDI->音频流程"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

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
        from basic_pitch.inference import predict  # noqa: F401
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


# ============================
# 1. 旋律提取测试
# ============================
@pytest.mark.asyncio
async def test_extract_melody(tmp_path):
    """测试旋律提取（使用生成的测试音频）"""
    import numpy as np
    import scipy.io.wavfile as wavfile

    sample_rate = 16000
    duration = 2.0
    frequency = 440.0
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    audio = (np.sin(2 * np.pi * frequency * t) * 32767 * 0.5).astype(np.int16)

    audio_path = tmp_path / "sample.wav"
    wavfile.write(str(audio_path), sample_rate, audio)

    from app.agent.tools import tool_gateway
    result = await tool_gateway.extract_melody(str(audio_path))

    assert "melody_notes" in result
    assert isinstance(result["melody_notes"], list)


# ============================
# 2. MIDI 生成测试
# ============================
@pytest.mark.asyncio
async def test_generate_midi(tmp_path):
    """测试 MIDI 生成"""
    melody_data = {
        "melody_notes": [
            {"pitch": 60, "start": 0.0, "duration": 0.5},
            {"pitch": 64, "start": 0.5, "duration": 0.5},
            {"pitch": 67, "start": 1.0, "duration": 0.5},
        ],
        "confidence": 0.9
    }

    midi_path = tmp_path / "test.mid"
    from app.agent.tools import tool_gateway
    result = await tool_gateway.generate_midi(
        melody_data=melody_data,
        analysis_result={"bpm": 120},
        output_path=str(midi_path)
    )

    assert result is not None
    assert os.path.exists(result)


# ============================
# 3. 完整流程测试（需要音色库）
# ============================
@pytest.mark.asyncio
@has_soundfont
@has_basic_pitch
async def test_pipeline_end_to_end(tmp_path):
    """端到端测试：音频 -> 旋律提取 -> MIDI -> 渲染（需要音色库）"""
    import numpy as np
    import scipy.io.wavfile as wavfile

    sample_rate = 16000
    duration = 2.0
    frequency = 440.0
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    audio = (np.sin(2 * np.pi * frequency * t) * 32767 * 0.5).astype(np.int16)

    audio_path = tmp_path / "sample.wav"
    wavfile.write(str(audio_path), sample_rate, audio)

    from app.agent.tools import tool_gateway

    melody_result = await tool_gateway.extract_melody(str(audio_path))
    assert "melody_notes" in melody_result

    midi_path = tmp_path / "test.mid"
    midi_result = await tool_gateway.generate_midi(
        melody_data=melody_result,
        analysis_result={"bpm": 120},
        output_path=str(midi_path)
    )
    assert midi_result is not None
    assert os.path.exists(midi_result)

    audio_output = tmp_path / "test.wav"
    final_audio = await tool_gateway.render_audio(
        midi_path=midi_result,
        instruments={},
        output_path=str(audio_output),
        duration=30.0
    )
    assert final_audio is not None
    assert os.path.exists(final_audio)
