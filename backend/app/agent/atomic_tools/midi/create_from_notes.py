# app/agent/atomic_tools/midi/create_from_notes.py
import mido
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import List, Dict, Any

def _apply_legato(notes: list[dict], overlap: float, max_gap: float) -> list[dict]:
    """将间隔很小的相邻音符轻微重叠，形成连奏（legato）效果。"""
    if not notes:
        return notes
    ordered = sorted(notes, key=lambda n: n["start"])
    result = [dict(n) for n in ordered]
    for i in range(len(result) - 1):
        cur = result[i]
        nxt = result[i + 1]
        gap = nxt["start"] - cur["end"]
        if 0 <= gap < max_gap:
            # 桥接小间隙：延长当前音符，使其与下一音符轻微重叠
            new_end = min(nxt["start"] + overlap, nxt["end"])
            if new_end > cur["end"]:
                cur["end"] = new_end
    return result


def _apply_sustain(notes: list[dict], sustain: float) -> list[dict]:
    """延音：把每个音符向后延长 sustain 秒，填补稀疏旋律的空隙，让听感更连贯。"""
    if not notes:
        return notes
    ordered = sorted(notes, key=lambda n: n["start"])
    result = [dict(n) for n in ordered]
    for i in range(len(result) - 1):
        cur = result[i]
        nxt = result[i + 1]
        # 延长到 min(下一音符起点, 原终点 + sustain)，不覆盖下一个音符
        cur["end"] = min(nxt["start"], cur["end"] + sustain)
    result[-1]["end"] = result[-1]["end"] + sustain
    return result


def _loop_notes(notes: list[dict], target_duration: float) -> list[dict]:
    """旋律短于目标时长时，循环重复直到填满（把短副歌做成完整铃声）。"""
    ordered = sorted(notes, key=lambda n: n["start"])
    if not ordered:
        return notes
    mel_dur = ordered[-1]["end"] - ordered[0]["start"]
    if mel_dur <= 0 or mel_dur >= target_duration:
        return ordered
    result = []
    offset = 0.0
    while offset < target_duration:
        for n in ordered:
            result.append({**n, "start": n["start"] + offset, "end": n["end"] + offset})
        offset += mel_dur
    # 只保留起点在目标时长内的音符
    result = [n for n in result if n["start"] < target_duration]
    result.sort(key=lambda n: n["start"])
    return result


async def create_midi_from_notes(
    notes: list[dict],
    bpm: float,
    output_path: str,
    ticks_per_beat: int = 480,
    legato_overlap: float = 0.0,
    legato_max_gap: float = 0.08,
    shift_to_zero: bool = True,
    sustain: float = 0.0,
    loop_to_duration: float = 0.0,
) -> str:
    """
    根据音符列表生成 MIDI 文件。

    Args:
        notes: 每个音符包含 pitch, start, end, velocity
        bpm: 节拍速度
        output_path: 输出 MIDI 路径
        ticks_per_beat: MIDI 时钟精度
        legato_overlap: 相邻音符轻微重叠时长（秒），0 表示不启用连奏
        legato_max_gap: 间隔小于该值（秒）的相邻音符才做连奏桥接
        shift_to_zero: 是否把所有音符整体平移到从 0 开始（去掉前奏/静音段）
        sustain: 延音时长（秒），把每个音符向后延长以填补稀疏旋律的空隙
        loop_to_duration: 目标时长（秒），旋律短于此值时循环重复填满

    Returns:
        str: 输出路径
    """
    # 整体平移到从 0 开始：旋律可能从绝对时间（如副歌在 82s）开始，
    # 不平移会导致渲染出的音频前段全是静音、截取出"没声音"。
    if shift_to_zero and notes:
        min_start = min(n["start"] for n in notes)
        if min_start > 0:
            notes = [{**n, "start": n["start"] - min_start, "end": n["end"] - min_start} for n in notes]

    if loop_to_duration > 0:
        notes = _loop_notes(notes, loop_to_duration)

    if sustain > 0:
        notes = _apply_sustain(notes, sustain)

    if legato_overlap > 0:
        notes = _apply_legato(notes, legato_overlap, legato_max_gap)

    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    tempo = mido.bpm2tempo(bpm)
    track.append(mido.MetaMessage('set_tempo', tempo=tempo, time=0))

    last_ticks = 0
    for note in notes:
        start_ticks = int(note["start"] * ticks_per_beat * (bpm / 60))
        dur_ticks = int((note["end"] - note["start"]) * ticks_per_beat * (bpm / 60))
        wait = max(0, start_ticks - last_ticks)
        track.append(mido.Message('note_on', channel=0, note=note["pitch"], velocity=note["velocity"], time=wait))
        track.append(mido.Message('note_off', channel=0, note=note["pitch"], velocity=0, time=dur_ticks))
        last_ticks = start_ticks + dur_ticks

    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        mid.save(output_path)
        print(f"[MIDI] 文件已成功保存至 {output_path}")
    except Exception as e:
        print(f"[ERROR] MIDI 文件保存失败: {e}")
        raise
    return output_path

class CreateMidiFromNotesInput(BaseModel):
    notes: List[Dict[str, Any]] = Field(description="音符列表，每个音符需包含 pitch, start, end, velocity")
    bpm: float = Field(description="速度（BPM）")
    output_path: str = Field(description="输出 MIDI 文件路径")
    ticks_per_beat: int = Field(default=480, description="MIDI 时钟精度")
    legato_overlap: float = Field(default=0.0, description="相邻音符轻微重叠时长（秒），0 表示不启用连奏")
    legato_max_gap: float = Field(default=0.08, description="间隔小于该值（秒）的相邻音符才做连奏桥接")
    shift_to_zero: bool = Field(default=True, description="是否把所有音符整体平移到从 0 开始")
    sustain: float = Field(default=0.0, description="延音时长（秒），填补稀疏旋律的空隙")

create_midi_from_notes_tool = StructuredTool.from_function(
    coroutine=create_midi_from_notes,
    name="create_midi_from_notes",
    description="根据音符列表和 BPM 生成 MIDI 文件。",
    args_schema=CreateMidiFromNotesInput,
)