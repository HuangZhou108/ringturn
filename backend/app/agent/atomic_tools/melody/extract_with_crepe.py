# app/agent/atomic_tools/melody/extract_with_crepe.py
"""
CREPE（torchcrepe）旋律提取工具

使用 CREPE 单音基频追踪（CNN），专门用于人声/主旋律，比 Basic Pitch 更适合
"贴近原曲旋律"的场景。基于 PyTorch，CPU 可跑。
"""
import numpy as np
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


def extract_melody_crepe(audio_path: str, output_midi_path: str | None = None) -> dict:
    """
    使用 CREPE 提取主旋律。

    Returns:
        dict: {"melody_notes": [...], "confidence": float, "midi_path": str}
    """
    import torch
    import torchcrepe
    import pretty_midi
    import librosa

    sample_rate = 16000
    hop_length = 160  # 10ms 帧

    # 加载单声道音频（16kHz）
    audio, _ = librosa.load(audio_path, sr=sample_rate, mono=True)
    if audio.size == 0:
        return {"melody_notes": [], "confidence": 0.0, "midi_path": output_midi_path or ""}

    audio_tensor = torch.from_numpy(audio).float().unsqueeze(0)

    # CREPE 基频追踪
    frequency, periodicity = torchcrepe.predict(
        audio_tensor,
        sample_rate,
        hop_length=hop_length,
        fmin=80,
        fmax=2000,
        model='full',
        batch_size=2048,
        device='cpu',
        return_periodicity=True,
    )

    freq = frequency.squeeze(0).cpu().numpy()
    conf = periodicity.squeeze(0).cpu().numpy()

    times = np.arange(len(freq)) * hop_length / sample_rate

    # 基频 → 音符事件（连续同音高帧合并为一个音符）
    melody_notes = []
    min_note_len = 0.05
    note_start = None
    last_midi = None

    for i in range(len(freq)):
        f = float(freq[i])
        c = float(conf[i]) if i < len(conf) else 1.0
        voiced = f > 0 and c > 0.1

        if voiced:
            midi = int(round(69 + 12 * np.log2(f / 440.0)))
            if midi != last_midi:
                if note_start is not None and last_midi is not None:
                    dur = times[i] - note_start
                    if dur >= min_note_len:
                        melody_notes.append({
                            "pitch": last_midi, "start": float(note_start), "end": float(times[i]),
                            "velocity": 80, "confidence": 0.8,
                        })
                note_start = times[i]
                last_midi = midi
        else:
            if note_start is not None and last_midi is not None:
                dur = times[i] - note_start
                if dur >= min_note_len:
                    melody_notes.append({
                        "pitch": last_midi, "start": float(note_start), "end": float(times[i]),
                        "velocity": 80, "confidence": 0.8,
                    })
            note_start = None
            last_midi = None

    if note_start is not None and last_midi is not None:
        dur = times[-1] - note_start
        if dur >= min_note_len:
            melody_notes.append({
                "pitch": last_midi, "start": float(note_start), "end": float(times[-1]),
                "velocity": 80, "confidence": 0.8,
            })

    # 生成 MIDI
    if output_midi_path is None:
        output_midi_path = str(Path(audio_path).parent / f"{Path(audio_path).stem}_melody.mid")
    Path(output_midi_path).parent.mkdir(parents=True, exist_ok=True)

    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    for n in melody_notes:
        inst.notes.append(pretty_midi.Note(
            velocity=n["velocity"], pitch=n["pitch"], start=n["start"], end=n["end"]
        ))
    pm.instruments.append(inst)
    pm.write(output_midi_path)

    return {
        "melody_notes": melody_notes,
        "confidence": 0.8,
        "midi_path": output_midi_path,
    }


class ExtractMelodyCrepeInput(BaseModel):
    audio_path: str = Field(description="音频文件的绝对路径")
    output_midi_path: str | None = Field(default=None, description="可选的输出 MIDI 路径")


extract_melody_crepe_tool = StructuredTool.from_function(
    func=extract_melody_crepe,
    name="extract_melody_crepe",
    description="使用 CREPE 提取音频主旋律（单音基频追踪，适合人声/主旋律），返回音符列表和 MIDI 路径。",
    args_schema=ExtractMelodyCrepeInput,
)
