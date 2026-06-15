# app/agent/atomic_tools/arrangement/change_instrument.py
import os
import mido
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

# GM 乐器映射（完整版，共128个）
GM_MAP = {
    # Piano
    "Acoustic Grand Piano": 0, "Bright Acoustic Piano": 1,
    "Electric Grand Piano": 2, "Honky-tonk Piano": 3,
    "Electric Piano 1": 4, "Electric Piano 2": 5,
    "Harpsichord": 6, "Clavinet": 7,
    # Chromatic Percussion
    "Celesta": 8, "Glockenspiel": 9,
    "Music Box": 10, "Vibraphone": 11,
    "Marimba": 12, "Xylophone": 13,
    "Tubular Bells": 14, "Dulcimer": 15,
    # Organ
    "Drawbar Organ": 16, "Percussive Organ": 17,
    "Rock Organ": 18, "Church Organ": 19,
    "Reed Organ": 20, "Accordion": 21,
    "Harmonica": 22, "Tango Accordion": 23,
    # Guitar
    "Acoustic Guitar (nylon)": 24, "Acoustic Guitar (steel)": 25,
    "Electric Guitar (jazz)": 26, "Electric Guitar (clean)": 27,
    "Electric Guitar (muted)": 28, "Overdriven Guitar": 29,
    "Distortion Guitar": 30, "Guitar Harmonics": 31,
    # Bass
    "Acoustic Bass": 32, "Electric Bass (finger)": 33,
    "Electric Bass (pick)": 34, "Fretless Bass": 35,
    "Slap Bass 1": 36, "Slap Bass 2": 37,
    "Synth Bass 1": 38, "Synth Bass 2": 39,
    # Strings
    "Violin": 40, "Viola": 41,
    "Cello": 42, "Contrabass": 43,
    "Tremolo Strings": 44, "Pizzicato Strings": 45,
    "Orchestral Harp": 46, "Timpani": 47,
    # Ensemble
    "String Ensemble 1": 48, "String Ensemble 2": 49,
    "Synth Strings 1": 50, "Synth Strings 2": 51,
    "Choir Aahs": 52, "Voice Oohs": 53,
    "Synth Voice": 54, "Orchestra Hit": 55,
    # Brass
    "Trumpet": 56, "Trombone": 57,
    "Tuba": 58, "Muted Trumpet": 59,
    "French Horn": 60, "Brass Section": 61,
    "Synth Brass 1": 62, "Synth Brass 2": 63,
    # Reed
    "Soprano Sax": 64, "Alto Sax": 65,
    "Tenor Sax": 66, "Baritone Sax": 67,
    "Oboe": 68, "English Horn": 69,
    "Bassoon": 70, "Clarinet": 71,
    # Pipe
    "Piccolo": 72, "Flute": 73,
    "Recorder": 74, "Pan Flute": 75,
    "Blown Bottle": 76, "Shakuhachi": 77,
    "Whistle": 78, "Ocarina": 79,
    # Synth Lead
    "Lead 1 (square)": 80, "Lead 2 (sawtooth)": 81,
    "Lead 3 (calliope)": 82, "Lead 4 (chiff)": 83,
    "Lead 5 (charang)": 84, "Lead 6 (voice)": 85,
    "Lead 7 (fifths)": 86, "Lead 8 (bass + lead)": 87,
    # Synth Pad
    "Pad 1 (new age)": 88, "Pad 2 (warm)": 89,
    "Pad 3 (polysynth)": 90, "Pad 4 (choir)": 91,
    "Pad 5 (bowed)": 92, "Pad 6 (metallic)": 93,
    "Pad 7 (halo)": 94, "Pad 8 (sweep)": 95,
    # Synth Effects
    "FX 1 (rain)": 96, "FX 2 (soundtrack)": 97,
    "FX 3 (crystal)": 98, "FX 4 (atmosphere)": 99,
    "FX 5 (brightness)": 100, "FX 6 (goblins)": 101,
    "FX 7 (echoes)": 102, "FX 8 (sci-fi)": 103,
    # Ethnic
    "Sitar": 104, "Banjo": 105,
    "Shamisen": 106, "Koto": 107,
    "Kalimba": 108, "Bagpipe": 109,
    "Fiddle": 110, "Shanai": 111,
    # Percussive
    "Tinkle Bell": 112, "Agogo": 113,
    "Steel Drums": 114, "Woodblock": 115,
    "Taiko Drum": 116, "Melodic Tom": 117,
    "Synth Drum": 118, "Reverse Cymbal": 119,
    # Sound Effects
    "Guitar Fret Noise": 120, "Breath Noise": 121,
    "Seashore": 122, "Bird Tweet": 123,
    "Telephone Ring": 124, "Helicopter": 125,
    "Applause": 126, "Gunshot": 127,
}

def _get_instrument_number(name: str) -> int:
    """将乐器名称转换为GM程序编号，支持精确匹配和模糊匹配"""
    name_lower = name.lower()
    
    # 精确匹配
    for key, value in GM_MAP.items():
        if key.lower() == name_lower:
            return value
    
    # 模糊匹配（用于兼容旧数据或简化名称）
    for key, value in GM_MAP.items():
        if key.lower() in name_lower or name_lower in key.lower():
            return value
    
    return 0  # 默认钢琴

async def change_instrument(midi_path: str, target_instrument: str, output_path: str | None = None) -> str:
    """
    将 MIDI 文件中的所有音轨乐器更换为目标 GM 乐器。

    Args:
        midi_path: 输入 MIDI 路径
        target_instrument: 乐器名称（如 "piano", "violin"）
        output_path: 输出路径

    Returns:
        str: 输出路径
    """
    if not os.path.isfile(midi_path):
        raise ValueError(f"输入 MIDI 文件不存在: {midi_path}")
    if output_path is None:
        output_path = midi_path.replace(".mid", "_instr.mid")
    mid = mido.MidiFile(midi_path)
    program = _get_instrument_number(target_instrument)
    
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'program_change':
                msg.program = program
    # 如果没有 program_change，在第一个非元消息前插入
    has_program = any(msg.type == 'program_change' for track in mid.tracks for msg in track)
    if not has_program and mid.tracks:
        track = mid.tracks[0]
        new_track = []
        inserted = False
        for msg in track:
            if not inserted and msg.type not in ('track_name', 'time_signature', 'set_tempo'):
                new_track.append(mido.Message('program_change', program=program, time=0))
                inserted = True
            new_track.append(msg)
        if not inserted:
            new_track.insert(0, mido.Message('program_change', program=program, time=0))
        mid.tracks[0] = new_track
    mid.save(output_path)
    if not os.path.isfile(output_path):
        raise RuntimeError(f"改编后的 MIDI 未成功保存至 {output_path}")
    return output_path

class ChangeInstrumentInput(BaseModel):
    midi_path: str = Field(..., description="输入 MIDI 文件的完整绝对路径，必须是可读文件")
    target_instrument: str = Field(description="目标乐器名称，如 piano, violin, guitar 等")
    output_path: str = Field(..., description="输出 MIDI 文件的完整路径，必须由系统指定，不得编造")

change_instrument_tool = StructuredTool.from_function(
    coroutine=change_instrument,
    name="change_instrument",
    description=(
        "将 MIDI 文件中所有音轨的乐器更换为目标 GM 乐器。"
        "必须提供 output_path，且必须使用系统给定的输出路径。"
    ),
    args_schema=ChangeInstrumentInput,
)