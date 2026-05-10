# app/agent/atomic_tools/arrangement/quantize_midi.py
import mido
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def quantize_midi(midi_path: str, grid: float = 0.25, output_path: str | None = None) -> str:
    """
    对 MIDI 文件中的音符进行量化（对齐到网格）。

    Args:
        midi_path: 输入 MIDI
        grid: 网格（拍），如 0.25 = 16分音符
        output_path: 输出路径

    Returns:
        str: 输出路径
    """
    if output_path is None:
        output_path = midi_path.replace(".mid", "_quantized.mid")

    mid = mido.MidiFile(midi_path)
    ticks_per_beat = mid.ticks_per_beat
    grid_ticks = int(ticks_per_beat * grid)

    # 对每个音轨独立处理
    for track in mid.tracks:
        # 第一步：将绝对时间算出来
        abs_time = 0
        events = []  # (abs_time, msg)
        for msg in track:
            abs_time += msg.time
            events.append((abs_time, msg))

        # 第二步：收集所有 note_on 和 note_off 的绝对时间，并量化
        # 使用字典记录每个音符的起始绝对时间（量化前）
        note_abs_times = {}  # note -> start_abs

        new_events = []  # 存储量化后的事件 (new_abs_time, msg)
        for abs_t, msg in events:
            if msg.type == 'note_on' and msg.velocity > 0:
                # 量化起始时间
                quantized_start = (abs_t // grid_ticks) * grid_ticks
                note_abs_times[msg.note] = quantized_start
                # 复制消息并设置新的绝对时间（稍后会重新计算 delta）
                new_msg = msg.copy()
                new_events.append((quantized_start, new_msg))
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                if msg.note in note_abs_times:
                    start_abs = note_abs_times.pop(msg.note)
                    # 保持原始持续时间，即 END = START + (原始结束 - 原始开始)
                    # 原始持续时间 = abs_t - original_start
                    # 我们需要知道原始开始时间，所以需要在 note_on 时记录原始绝对时间
                    # 这里简化：保持 offset 不变，但使用量化后的 start 加上原始 duration
                    # 为了获取原始 duration，我们需要在 note_on 时存下原始开始时间
                    # 更简单的做法：再遍历一次，用字典存储原始开始时间
                    pass
                # 暂时先不处理，采用更安全的方法：单独重构
            else:
                # 非音符消息保持原样，绝对时间不变
                new_events.append((abs_t, msg))

        # 由于上述方法复杂，我们换一种更可靠的方式：
        # 重写整个量化逻辑，确保每个音符的起始和结束都被量化，并且时间顺序正确。
        # 彻底重写方法：使用 pretty_midi 或自己重建 track。

    # 更简洁且不易出错的实现：使用 pretty_midi 进行量化，避免手动操作 delta 时间。
    # 但为了不引入新依赖，我们采用完全重建 MIDI 文件的方式。

    # -------------------- 完全重建版本 --------------------
    from collections import defaultdict
    import copy

    # 重新加载 MIDI 文件，使用绝对时间重建
    mid_new = mido.MidiFile(ticks_per_beat=mid.ticks_per_beat)
    for track_idx, old_track in enumerate(mid.tracks):
        # 计算每个消息的绝对时间
        abs_time = 0
        events = []
        for msg in old_track:
            abs_time += msg.time
            events.append((abs_time, msg))

        # 分离音符事件和非音符事件
        note_on_map = {}  # (note, channel) -> (abs_start, msg)
        non_note_events = []

        for abs_t, msg in events:
            if msg.type == 'note_on' and msg.velocity > 0:
                key = (msg.note, msg.channel)
                note_on_map[key] = (abs_t, msg)
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                key = (msg.note, msg.channel)
                if key in note_on_map:
                    start_abs, start_msg = note_on_map.pop(key)
                    # 量化起始和结束
                    quant_start = (start_abs // grid_ticks) * grid_ticks
                    quant_end = (abs_t // grid_ticks) * grid_ticks
                    if quant_end <= quant_start:
                        quant_end = quant_start + grid_ticks  # 至少一个网格长度
                    # 创建量化后的音符事件
                    new_on = start_msg.copy(time=0)
                    new_off = msg.copy(time=0)
                    non_note_events.append((quant_start, new_on))
                    non_note_events.append((quant_end, new_off))
                else:
                    # 孤立 note_off，保留原样但量化时间
                    non_note_events.append((abs_t, msg))
            else:
                non_note_events.append((abs_t, msg))

        # 将剩余未配对的 note_on 也加入（量化起始）
        for (note, ch), (abs_t, msg) in note_on_map.items():
            quant_start = (abs_t // grid_ticks) * grid_ticks
            non_note_events.append((quant_start, msg))

        # 合并所有事件，按绝对时间排序
        non_note_events.sort(key=lambda x: x[0])

        # 重建音轨，计算 delta 时间
        new_track = mido.MidiTrack()
        last_abs = 0
        for abs_t, msg in non_note_events:
            delta = abs_t - last_abs
            # 确保 delta 非负（理论上绝对时间递增，但浮点误差可能导致负数）
            if delta < 0:
                delta = 0
            new_msg = msg.copy(time=delta)
            new_track.append(new_msg)
            last_abs = abs_t

        # 如果原音轨有元消息（如 tempo, track_name），这些已经在 non_note_events 中包含了
        # 但注意：set_tempo 等元消息的绝对时间可能也因量化而移动，可能导致速度变化点偏移，但通常影响不大。
        mid_new.tracks.append(new_track)

    mid_new.save(output_path)
    return output_path


class QuantizeMidiInput(BaseModel):
    midi_path: str = Field(description="输入 MIDI 文件路径")
    grid: float = Field(default=0.25, description="量化网格（拍），如 0.25 = 16分音符")
    output_path: str | None = Field(default=None, description="输出路径（可选）")


quantize_midi_tool = StructuredTool.from_function(
    coroutine=quantize_midi,
    name="quantize_midi",
    description="量化 MIDI 文件中的音符，使其对齐到指定的节拍网格。",
    args_schema=QuantizeMidiInput,
)