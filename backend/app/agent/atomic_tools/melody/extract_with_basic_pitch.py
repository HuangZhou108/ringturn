# app/agent/atomic_tools/melody/extract_with_basic_pitch.py
from pathlib import Path
import mido

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
    model_output, midi_data, note_events = predict(
        audio_path=str(audio_path),
        onset_threshold=0.5,
        frame_threshold=0.3,
        minimum_note_length=127.7,
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
    
    return {
        "melody_notes": melody_notes,
        "confidence": float(model_output.get("average_note_confidence", 0.8)) if model_output else 0.8,
        "midi_path": output_midi_path,
    }