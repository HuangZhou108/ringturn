# app/agent/atomic_tools/melody/extract_with_basic_pitch.py
from pathlib import Path
import mido
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def extract_melody_basic_pitch(audio_path: str, output_midi_path: str | None = None) -> dict:
    """
    使用 Spotify Basic Pitch 提取旋律音符。

    Args:
        audio_path: 音频文件路径
        output_midi_path: 可选，输出的 MIDI 路径

    Returns:
        dict: 包含 melody_notes (list), confidence (float), midi_path (str)

    使用场景：
        - 从人声或乐器单轨提取主旋律
    """
    from basic_pitch.inference import predict
    # 你可以自行调整一下3个参数以获得最佳效果，3个参数效果分别为：提高过滤弱音符，提升音高检测确信度，过滤所有长度小于minimum_note_length的音符
    model_output, midi_data, note_events = predict(
        audio_path=str(audio_path),
        onset_threshold=0.5,
        frame_threshold=0.4,
        minimum_note_length=50,
    )
    melody_notes = []
    for start, end, pitch, velocity, _ in note_events:
        melody_notes.append({
            "pitch": int(pitch),
            "start": float(start),
            "end": float(end),
            "velocity": int(velocity * 127) if velocity else 80,
            "confidence": float(velocity) if velocity else 0.8,
        })
    if output_midi_path is None:
        output_midi_path = str(Path(audio_path).parent / f"{Path(audio_path).stem}_melody.mid")
    Path(output_midi_path).parent.mkdir(parents=True, exist_ok=True)
    midi_data.write(output_midi_path)
    
    print(f"[DEBUG Basic Pitch] 提取完成，音符数: {len(melody_notes)}，midi_path: {output_midi_path}")
    print(f"[DEBUG Basic Pitch] 前5个音符: {melody_notes[:5]}")
    return {
        "melody_notes": melody_notes,
        "confidence": float(model_output.get("average_note_confidence", 0.8)) if model_output else 0.8,
        "midi_path": output_midi_path,
    }

class ExtractMelodyBasicPitchInput(BaseModel):
    audio_path: str = Field(description="音频文件的绝对路径")
    output_midi_path: str | None = Field(default=None, description="可选的输出 MIDI 路径")

extract_melody_basic_pitch_tool = StructuredTool.from_function(
    coroutine=extract_melody_basic_pitch,
    name="extract_melody_basic_pitch",
    description="使用 Spotify Basic Pitch 从音频中提取主旋律，返回音符列表和生成的 MIDI 文件路径。精度优于 librosa 方法。",
    args_schema=ExtractMelodyBasicPitchInput,
)