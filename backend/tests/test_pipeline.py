"""
测试音频->MIDI->音频流程

Usage:
    python tests/test_pipeline.py <audio_file>
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.tools import tool_gateway


async def test_pipeline(audio_path: str):
    """测试完整流程"""
    print(f"\n{'='*50}")
    print(f"测试音频: {audio_path}")
    print(f"{'='*50}\n")

    if not os.path.exists(audio_path):
        print(f"[ERROR] 文件不存在: {audio_path}")
        return

    # 确保输出目录
    output_dir = Path(__file__).parent.parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    # 1. 提取旋律 (Basic Pitch)
    print("[1/3] 提取旋律 (Basic Pitch)...")
    try:
        melody_result = await tool_gateway.extract_melody(audio_path)
        print(f"    旋律音符数: {len(melody_result.get('melody_notes', []))}")
        print(f"    置信度: {melody_result.get('confidence', 0):.2f}")
        if melody_result.get("midi_path"):
            print(f"    生成的MIDI: {melody_result['midi_path']}")
    except Exception as e:
        print(f"    [ERROR] {e}")
        melody_result = {"melody_notes": [], "confidence": 0}

    # 2. 生成MIDI
    print("\n[2/3] 生成MIDI...")
    midi_path = str(output_dir / "test_output.mid")
    analysis_result = {"bpm": 120}
    try:
        midi_result = await tool_gateway.generate_midi(
            melody_data=melody_result,
            analysis_result=analysis_result,
            output_path=midi_path
        )
        print(f"    MIDI路径: {midi_result}")
        if os.path.exists(midi_result):
            print(f"    MIDI大小: {os.path.getsize(midi_result)} bytes")
    except Exception as e:
        print(f"    [ERROR] {e}")
        midi_result = None

    # 3. 渲染音频 (FluidSynth)
    print("\n[3/3] 渲染音频 (FluidSynth)...")
    if midi_result and os.path.exists(midi_result):
        audio_output = str(output_dir / "test_output.wav")
        try:
            final_audio = await tool_gateway.render_audio(
                midi_path=midi_result,
                instruments={},
                output_path=audio_output,
                duration=30.0
            )
            print(f"    音频路径: {final_audio}")
            if os.path.exists(final_audio):
                print(f"    音频大小: {os.path.getsize(final_audio)} bytes")
            else:
                print("    [WARN] 音频文件未生成")
        except Exception as e:
            print(f"    [ERROR] {e}")
    else:
        print("    [SKIP] MIDI文件不存在，跳过渲染")

    print(f"\n{'='*50}")
    print(f"测试完成! 输出目录: {output_dir}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        # 创建一个测试音频文件路径（如果有的话）
        print("请提供音频文件路径，例如:")
        print("    python tests/test_pipeline.py ./test_audio.mp3")
    else:
        asyncio.run(test_pipeline(sys.argv[1]))
