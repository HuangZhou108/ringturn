"""
MIDI乐器改编服务

实现MIDI文件中的乐器替换和风格调整
"""

import mido
from pathlib import Path


# GM乐器编号 (General MIDI)
INSTRUMENTS = {
    "piano": 0,           # Acoustic Grand Piano
    "electric_piano": 4,  # Electric Piano 1
    "guitar": 24,          # Acoustic Guitar (nylon)
    "electric_guitar": 27, # Electric Guitar (clean)
    "bass": 32,            # Acoustic Bass
    "violin": 40,          # Violin
    "cello": 42,          # Cello
    "strings": 48,         # Orchestral Strings
    "flute": 73,           # Flute
    "saxophone": 66,       # Tenor Saxophone
    "organ": 19,           # Church Organ
    "harp": 46,           # Harp
    "bell": 14,           # Glockenspiel
    "chime": 91,          # Sound FX / Atmosphere
}


def get_instrument_number(name: str) -> int:
    """获取乐器编号"""
    name_lower = name.lower()
    for key, value in INSTRUMENTS.items():
        if key in name_lower or name_lower in key:
            return value
    return 0  # 默认钢琴


async def arrange_midi(
    midi_path: str,
    target_instruments: list[str],
    style: str = "",
    output_path: str | None = None
) -> str:
    """
    改编MIDI文件的乐器

    Args:
        midi_path: 原始MIDI路径
        target_instruments: 目标乐器列表
        style: 风格描述（用于后续扩展）

    Returns:
        str: 改编后的MIDI路径
    """
    if output_path is None:
        output_path = midi_path.replace(".mid", "_arranged.mid")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        # 读取原MIDI
        mid = mido.MidiFile(midi_path)

        # 确定主乐器
        main_instrument = get_instrument_number(target_instruments[0]) if target_instruments else 0

        # 修改每个音轨的乐器
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'program_change':
                    msg.program = main_instrument

        # 如果原MIDI没有program_change，在第一个轨道添加
        has_program_change = any(
            msg.type == 'program_change'
            for track in mid.tracks
            for msg in track
        )

        if not has_program_change and mid.tracks:
            # 在第一个非元消息前插入program_change
            track = mid.tracks[0]
            new_track = []
            inserted = False
            for msg in track:
                if not inserted and msg.type not in ('track_name', 'time_signature', 'set_tempo'):
                    new_track.append(mido.Message('program_change', program=main_instrument, time=0))
                    inserted = True
                new_track.append(msg)
            if not inserted:
                new_track.insert(0, mido.Message('program_change', program=main_instrument, time=0))
            mid.tracks[0] = new_track

        mid.save(output_path)
        return output_path

    except Exception as e:
        print(f"[WARN] MIDI改编失败: {e}，使用原文件")
        import shutil
        shutil.copy(midi_path, output_path)
        return output_path


async def change_tempo(midi_path: str, bpm: float, output_path: str | None = None) -> str:
    """
    调整MIDI速度

    Args:
        midi_path: MIDI路径
        bpm: 目标BPM
        output_path: 输出路径

    Returns:
        str: 输出路径
    """
    if output_path is None:
        output_path = midi_path.replace(".mid", f"_{int(bpm)}bpm.mid")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        mid = mido.MidiFile(midi_path)

        # 计算新tempo (微秒每拍)
        new_tempo = mido.bpm2tempo(bpm)

        # 替换所有set_tempo消息
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'set_tempo':
                    msg.tempo = new_tempo

        # 如果没有set_tempo，在第一轨开头添加
        has_tempo = any(
            msg.type == 'set_tempo'
            for track in mid.tracks
            for msg in track
        )

        if not has_tempo and mid.tracks:
            mid.tracks[0].insert(0, mido.MetaMessage('set_tempo', tempo=new_tempo, time=0))

        mid.save(output_path)
        return output_path

    except Exception as e:
        print(f"[WARN] 速度调整失败: {e}")
        import shutil
        shutil.copy(midi_path, output_path)
        return output_path


async def quantize_notes(midi_path: str, grid: float = 0.25, output_path: str | None = None) -> str:
    """
    量化音符（对齐到网格）

    Args:
        midi_path: MIDI路径
        grid: 网格大小（拍数），0.25=16分音符
        output_path: 输出路径

    Returns:
        str: 输出路径
    """
    if output_path is None:
        output_path = midi_path.replace(".mid", "_quantized.mid")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        mid = mido.MidiFile(midi_path)
        ticks_per_beat = mid.ticks_per_beat
        grid_ticks = int(ticks_per_beat * grid)

        for track in mid.tracks:
            note_start_times = {}

            current_time = 0
            i = 0
            new_track = []

            while i < len(track):
                msg = track[i]
                current_time += msg.time

                if msg.type == 'note_on' and msg.velocity > 0:
                    # 量化开始时间
                    quantized_start = (current_time // grid_ticks) * grid_ticks
                    note_start_times[msg.note] = (quantized_start, msg.velocity)

                    # 计算需要调整的时间
                    time_adjustment = quantized_start - current_time
                    new_track.append(mido.Message(
                        'note_on',
                        channel=msg.channel,
                        note=msg.note,
                        velocity=msg.velocity,
                        time=msg.time + time_adjustment
                    ))
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    if msg.note in note_start_times:
                        quantized_start, velocity = note_start_times.pop(msg.note)
                        time_adjustment = quantized_start - current_time
                        new_track.append(mido.Message(
                            'note_off',
                            channel=msg.channel,
                            note=msg.note,
                            velocity=0,
                            time=msg.time + time_adjustment
                        ))
                    else:
                        new_track.append(msg)
                else:
                    new_track.append(msg)

                i += 1

            # 重新计算时间，确保连续
            last_time = 0
            for msg in new_track:
                delta = msg.time
                msg.time = delta - last_time
                last_time = delta

            # 再次处理，确保时间正确
            new_track2 = []
            running_time = 0
            for msg in new_track:
                new_track2.append(mido.Message(msg.type, time=msg.time, **msg.dict().get('extra', {}), **({k: v for k, v in msg.dict().items() if k not in ('type', 'time', 'extra')})))

            track[:] = new_track

        mid.save(output_path)
        return output_path

    except Exception as e:
        print(f"[WARN] 量化失败: {e}")
        import shutil
        shutil.copy(midi_path, output_path)
        return output_path
