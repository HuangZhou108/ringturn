# backend/app/agent/atomic_tools/analysis/madmom_analyze.py

"""
madmom 节奏分析原子工具

功能：
- 高精度节拍检测
- 强拍（downbeat）检测
- 输出 BPM、节拍时间点、强拍时间点
"""

from pathlib import Path
from typing import Dict, Any, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


async def analyze_rhythm_madmom(
    audio_path: str
) -> Dict[str, Any]:
    """
    使用 madmom 进行节奏分析。

    madmom 是学术界广泛使用的节拍跟踪工具，准确率远高于 librosa。

    Args:
        audio_path: 输入音频文件的绝对路径

    Returns:
        dict: 包含以下字段
            - bpm: 估算的平均 BPM
            - beat_times: 节拍时间点列表（秒）
            - downbeat_times: 强拍时间点列表（秒）
            - time_signature: 节拍号
    """
    try:
        import madmom
        from madmom.features.beats import RNNBeatProcessor, DBNBeatTrackingProcessor
        from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor
    except ImportError:
        raise RuntimeError("madmom not found. Please install with: pip install madmom")

    # 节拍检测
    beat_proc = RNNBeatProcessor()(audio_path)
    beat_tracker = DBNBeatTrackingProcessor(fps=100)
    beat_times = beat_tracker(beat_proc)

    # BPM 估算（从节拍间隔的平均值计算）
    if len(beat_times) > 1:
        intervals = [beat_times[i] - beat_times[i - 1] for i in range(1, len(beat_times))]
        avg_interval = sum(intervals) / len(intervals)
        bpm = 60.0 / avg_interval
    else:
        bpm = 120.0

    # 强拍检测
    downbeat_proc = RNNDownBeatProcessor()(audio_path)
    downbeat_tracker = DBNDownBeatTrackingProcessor(beats_per_bar=[3, 4], fps=100)
    downbeats = downbeat_tracker(downbeat_proc)

    return {
        "bpm": round(bpm, 2),
        "beat_times": [float(t) for t in beat_times],
        "downbeat_times": [float(t[0]) for t in downbeats],
        "time_signature": "4/4",  # madmom 不直接输出节拍号，可通过 downbeat 模式推断
    }


class MadmomInput(BaseModel):
    audio_path: str = Field(..., description="音频文件的绝对路径")


madmom_analyze_tool = StructuredTool.from_function(
    coroutine=analyze_rhythm_madmom,
    name="madmom_analyze",
    description=(
        "使用 madmom 进行高精度节奏分析。返回 BPM、节拍时间点、强拍时间点。"
        "精度远超 librosa，是当前节拍跟踪的最佳选择。"
    ),
    args_schema=MadmomInput,
)