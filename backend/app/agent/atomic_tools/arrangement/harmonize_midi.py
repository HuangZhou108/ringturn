# app/agent/atomic_tools/arrangement/harmonize_midi.py
"""
多轨和声编曲工具

在旋律 MIDI 之上添加：
1. 低音轨：每个和弦段的根音（低八度），使用贝斯音色
2. 和弦垫轨：根音 + 五度（持续音），使用柔和 Pad 音色

将旋律、低音、和弦垫合并为一个多轨 MIDI，让改编结果从"单薄旋律"变成"旋律 + 伴奏"。
"""
import shutil
import mido
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from app.agent.atomic_tools.arrangement.gap_accompaniment import select_accompaniment_channels


def _build_track(events: List[tuple]) -> mido.MidiTrack:
    """events: [(abs_tick, msg)]，按绝对 tick 排序后转换为 delta 时间构建音轨。"""
    events.sort(key=lambda x: x[0])
    track = mido.MidiTrack()
    last = 0
    for abs_t, msg in events:
        delta = max(0, abs_t - last)
        track.append(msg.copy(time=delta))
        last = abs_t
    return track


async def harmonize_midi(
    midi_path: str,
    chords: List[Dict[str, Any]],
    output_path: str,
    bpm: float = 120.0,
    bass_program: int = 32,   # Acoustic Bass
    pad_program: int = 89,    # Pad 2 (warm)
    bass_velocity: int = 50,
    pad_velocity: int = 35,
) -> str:
    """
    为旋律 MIDI 添加低音轨 + 和弦垫轨，合并成多轨 MIDI。

    Args:
        midi_path: 旋律 MIDI（单轨，已换乐器/变速）
        chords: 和弦根音进行，每个元素 {"start":秒, "end":秒, "root_midi":int}
        output_path: 输出多轨 MIDI 路径
        bpm: 旋律 MIDI 生成时使用的 BPM（用于把和弦的秒时间换算成 tick），须与旋律一致
        bass_program / pad_program: GM 乐器编号
    """
    if not chords:
        shutil.copy(midi_path, output_path)
        return output_path

    mid = mido.MidiFile(midi_path)
    ticks_per_beat = mid.ticks_per_beat

    def s2t(seconds: float) -> int:
        return int(round(seconds * ticks_per_beat * (bpm / 60.0)))

    # MIDI program 是按 channel 生效的。伴奏若与旋律共用 channel，Pad/Bass 的
    # program_change 会覆盖原音色，因此优先选择两个未占用的非鼓组 channel。
    used_channels = {
        msg.channel
        for track in mid.tracks
        for msg in track
        if hasattr(msg, "channel")
    }
    bass_channel, pad_channel = select_accompaniment_channels(used_channels)
    bass_events = [
        (
            0,
            mido.Message(
                'program_change', channel=bass_channel, program=bass_program, time=0
            ),
        )
    ]
    pad_events = [
        (
            0,
            mido.Message(
                'program_change', channel=pad_channel, program=pad_program, time=0
            ),
        )
    ]

    for ch in chords:
        root = int(ch["root_midi"])
        start = s2t(float(ch["start"]))
        end = s2t(float(ch["end"]))
        if end <= start:
            end = start + 1

        # 低音：根音低八度
        bass_note = root - 12
        if 0 <= bass_note <= 127:
            bass_events.append(
                (
                    start,
                    mido.Message(
                        'note_on',
                        channel=bass_channel,
                        note=bass_note,
                        velocity=bass_velocity,
                        time=0,
                    ),
                )
            )
            bass_events.append(
                (
                    end,
                    mido.Message(
                        'note_off', channel=bass_channel, note=bass_note, velocity=0, time=0
                    ),
                )
            )

        # 和弦垫：根音 + 五度
        for pn in (root, root + 7):
            if 0 <= pn <= 127:
                pad_events.append(
                    (
                        start,
                        mido.Message(
                            'note_on',
                            channel=pad_channel,
                            note=pn,
                            velocity=pad_velocity,
                            time=0,
                        ),
                    )
                )
                pad_events.append(
                    (
                        end,
                        mido.Message(
                            'note_off', channel=pad_channel, note=pn, velocity=0, time=0
                        ),
                    )
                )

    mid.tracks.append(_build_track(bass_events))
    mid.tracks.append(_build_track(pad_events))
    mid.save(output_path)
    return output_path


class HarmonizeMidiInput(BaseModel):
    midi_path: str = Field(..., description="旋律 MIDI 的完整绝对路径")
    chords: List[Dict[str, Any]] = Field(..., description="和弦根音进行，每个元素含 start/end/root_midi")
    output_path: str = Field(..., description="输出多轨 MIDI 的完整绝对路径")
    bpm: float = Field(default=120.0, description="旋律 MIDI 生成时使用的 BPM")
    bass_program: int = Field(default=32, description="低音 GM 乐器编号")
    pad_program: int = Field(default=89, description="和弦垫 GM 乐器编号")


harmonize_midi_tool = StructuredTool.from_function(
    coroutine=harmonize_midi,
    name="harmonize_midi",
    description="为旋律 MIDI 添加低音轨与和弦垫轨，合并成多轨 MIDI，使改编结果更饱满。",
    args_schema=HarmonizeMidiInput,
)
