import numpy as np
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
import librosa
import pretty_midi

async def extract_melody_librosa(
    audio_path: str,
    output_midi_path: str | None = None
) -> dict:
    """
    使用 librosa.pyin 从音频中提取主旋律，生成 MIDI 文件。

    Args:
        audio_path: 音频文件的绝对路径
        output_midi_path: 可选，输出 MIDI 路径

    Returns:
        dict: melody_notes (list), confidence (float), midi_path (str)
    """
    # 1. 加载音频（单声道，22050 Hz 便于音高追踪）
    y, sr = librosa.load(audio_path, sr=22050, mono=True)

    # 2. PYIN 提取基频 (f0) 和有声概率
    f0, voiced_flag, voiced_prob = librosa.pyin(
        y,
        fmin=librosa.note_to_hz('A0'),   # ~27.5 Hz
        fmax=librosa.note_to_hz('C8'),   # ~4186 Hz
        sr=sr
    )
    f0 = np.nan_to_num(f0)
    times = librosa.times_like(f0, sr=sr)

    # 3. 连续 f0 转为离散音符事件
    melody_notes = []
    min_note_len = 0.05      # 最短 50 ms
    note_start = None
    last_midi = None

    for i in range(len(f0)):
        if voiced_flag[i] and f0[i] > 0:
            midi = librosa.hz_to_midi(f0[i])
            midi_round = int(round(midi))
            # 音符变化时结束上一个音符，开始新音符
            if midi_round != last_midi:
                if note_start is not None and last_midi is not None:
                    duration = times[i] - note_start
                    if duration >= min_note_len:
                        melody_notes.append({
                            "pitch": last_midi,
                            "start": note_start,
                            "end": times[i],
                            "velocity": 80,
                            "confidence": 0.8
                        })
                note_start = times[i]
                last_midi = midi_round
        else:
            # 无声区域结束当前音符
            if note_start is not None and last_midi is not None:
                duration = times[i] - note_start
                if duration >= min_note_len:
                    melody_notes.append({
                        "pitch": last_midi,
                        "start": note_start,
                        "end": times[i],
                        "velocity": 80,
                        "confidence": 0.8
                    })
            note_start = None
            last_midi = None

    # 处理持续到文件末尾的音符
    if note_start is not None and last_midi is not None:
        duration = times[-1] - note_start
        if duration >= min_note_len:
            melody_notes.append({
                "pitch": last_midi,
                "start": note_start,
                "end": times[-1],
                "velocity": 80,
                "confidence": 0.8
            })

    # 4. 生成 MIDI 文件
    if output_midi_path is None:
        output_midi_path = str(Path(audio_path).parent / f"{Path(audio_path).stem}_melody.mid")

    pm = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0)  # 默认钢琴
    for note in melody_notes:
        midi_note = pretty_midi.Note(
            velocity=note["velocity"],
            pitch=note["pitch"],
            start=note["start"],
            end=note["end"]
        )
        instrument.notes.append(midi_note)
    pm.instruments.append(instrument)
    pm.write(output_midi_path)

    print(f"[DEBUG Librosa] 提取完成，音符数: {len(melody_notes)}，midi_path: {output_midi_path}")
    # 5. 返回与原来一致的数据结构
    return {
        "melody_notes": melody_notes,
        "confidence": 0.8,
        "midi_path": output_midi_path,
    }


class ExtractMelodyInput(BaseModel):
    audio_path: str = Field(description="音频文件的绝对路径")
    output_midi_path: str | None = Field(default=None, description="可选的输出 MIDI 路径")


extract_melody_librosa_tool = StructuredTool.from_function(
    coroutine=extract_melody_librosa,
    name="extract_melody_librosa",
    description="使用 librosa.pyin 从音频中提取主旋律，返回音符列表和生成的 MIDI 文件路径。",
    args_schema=ExtractMelodyInput,
)