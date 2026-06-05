"""
旋律提取工具链图

将原有子 Agent 的流程固化到 LangGraph 中：
1. 分离人声（可选，但原逻辑要求必须分离）
2. 使用 Basic Pitch 提取旋律
3. 若 Basic Pitch 失败或返回空，降级使用 librosa 提取
4. 过滤短音符
5. 量化音符（若有 BPM 信息）
6. 输出最终的 melody_data
"""

import os
from pathlib import Path
from typing import Any, Dict

from langgraph.graph import StateGraph, END

from app.agent.state import AgentState
from app.agent.atomic_tools.melody.vocal_separation import separate_vocals
from app.agent.atomic_tools.melody.extract_with_basic_pitch import extract_melody_basic_pitch
from app.agent.atomic_tools.melody.extract_with_librosa import extract_melody_librosa
from app.agent.atomic_tools.melody.filter_short_notes import filter_short_notes
from app.agent.atomic_tools.melody.quantize_notes import quantize_notes
from app.agent.thinking_utils import record_thought
from app.agent.utils import clean_state


# ---------- 节点定义 ----------

async def node_separate_vocals(state: AgentState) -> Dict[str, Any]:
    """分离人声，得到 vocals 文件路径，存入 state['vocals_path']"""
    audio_path = state.get("audio_path")
    task_id = state.get("task_id")
    if not audio_path:
        raise ValueError("state 中缺少 audio_path")

    record_thought(task_id, "extract_melody", "开始分离人声...")
    try:
        vocals_path = await separate_vocals(audio_path)
        record_thought(task_id, "extract_melody", f"人声分离成功，路径: {vocals_path}")
        return {"vocals_path": vocals_path}
    except Exception as e:
        record_thought(task_id, "extract_melody", f"人声分离失败: {e}，将使用原始音频")
        # 降级：使用原始音频
        return {"vocals_path": audio_path}


async def node_basic_pitch(state: AgentState) -> Dict[str, Any]:
    """使用 Basic Pitch 提取旋律，结果存入 state['melody_data']"""
    audio_path = state.get("vocals_path") or state.get("audio_path")
    task_id = state.get("task_id")
    if not audio_path:
        raise ValueError("无法获取音频路径")

    record_thought(task_id, "extract_melody", "开始 Basic Pitch 提取旋律...")
    try:
        melody_data = await extract_melody_basic_pitch(audio_path)
        record_thought(task_id, "extract_melody", f"Basic Pitch 提取完成，音符数: {len(melody_data.get('melody_notes', []))}")
        # print(f"[DEBUG basic_pitch] returning melody_data keys: {melody_data.keys() if melody_data else None}")
        return {"melody_data": melody_data}
    except Exception as e:
        record_thought(task_id, "extract_melody", f"Basic Pitch 失败: {e}")
        return {"melody_data": None, "basic_pitch_failed": True}


async def node_check_basic_pitch_result(state: AgentState) -> Dict[str, Any]:
    """检查 Basic Pitch 结果是否有效，若无效则标记需要降级"""
    melody_data = state.get("melody_data")
    # print(f"[DEBUG check_result] melody_data type: {type(melody_data)}, value: {melody_data}")
    if melody_data and melody_data.get("melody_notes") and len(melody_data["melody_notes"]) > 0:
        # print(f"[DEBUG check_result] melody_notes length: {len(melody_data.get('melody_notes', []))}")
        return {"use_basic_pitch": True}
    else:
        return {"use_basic_pitch": False, "basic_pitch_failed": True}


async def node_librosa_fallback(state: AgentState) -> Dict[str, Any]:
    """降级：使用 librosa 提取旋律"""
    audio_path = state.get("vocals_path") or state.get("audio_path")
    task_id = state.get("task_id")
    record_thought(task_id, "extract_melody", "Basic Pitch 无效，降级使用 librosa 提取...")
    melody_data = await extract_melody_librosa(audio_path)
    record_thought(task_id, "extract_melody", f"librosa 提取完成，音符数: {len(melody_data.get('melody_notes', []))}")
    return {"melody_data": melody_data}


async def node_filter_short_notes(state: AgentState) -> Dict[str, Any]:
    """过滤时长过短的音符（默认 <0.05 秒）"""
    melody_data = state.get("melody_data")
    if not melody_data or not melody_data.get("melody_notes"):
        return {"melody_data": melody_data}

    notes = melody_data["melody_notes"]
    filtered = await filter_short_notes(notes, min_duration=0.05)
    melody_data["melody_notes"] = filtered
    task_id = state.get("task_id")
    record_thought(task_id, "extract_melody", f"过滤短音符后剩余: {len(filtered)}")
    return {"melody_data": melody_data}


async def node_quantize_notes(state: AgentState) -> Dict[str, Any]:
    """量化音符，对齐到节拍网格（需要 BPM）"""
    melody_data = state.get("melody_data")
    if not melody_data or not melody_data.get("melody_notes"):
        return {"melody_data": melody_data}

    # 尝试获取 BPM：优先从 analysis_result 中取，否则用默认值 120
    analysis = state.get("analysis_result", {})
    bpm = analysis.get("tempo_beats", {}).get("bpm") or 120
    # 网格大小：16分音符 = 0.25 拍
    grid = 0.25
    quantized_notes = await quantize_notes(melody_data["melody_notes"], grid=grid, bpm=bpm)
    melody_data["melody_notes"] = quantized_notes
    task_id = state.get("task_id")
    record_thought(task_id, "extract_melody", f"量化完成，网格 {grid} 拍，BPM={bpm}")
    return {"melody_data": melody_data}


async def node_ensure_midi_path(state: AgentState) -> Dict[str, Any]:
    """确保 melody_data 中包含有效的 midi_path，若缺失则根据音符重建"""
    melody_data = state.get("melody_data")
    if not melody_data:
        raise ValueError("melody_data 为空，无法生成 MIDI 路径")

    if melody_data.get("midi_path") and Path(melody_data["midi_path"]).exists():
        return {}  # 已有有效路径

    # 尝试从音频路径推断或创建默认 MIDI 路径
    audio_path = state.get("audio_path")
    if audio_path:
        default_midi = str(Path(audio_path).with_suffix(".mid")).replace(".mid", "_melody.mid")
        melody_data["midi_path"] = default_midi
        # 如果有音符列表，实际创建 MIDI 文件交给 generate_midi 节点，这里只占位
        # 但为了兼容性，我们尝试写入一个空 MIDI（generate_midi 会后续覆盖）
        Path(default_midi).parent.mkdir(parents=True, exist_ok=True)
        if not Path(default_midi).exists():
            Path(default_midi).touch()
    else:
        melody_data["midi_path"] = ""

    return {"melody_data": melody_data}


# ---------- 构建图 ----------

async def build_extract_graph():
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("separate_vocals", node_separate_vocals)
    workflow.add_node("basic_pitch", node_basic_pitch)
    workflow.add_node("check_result", node_check_basic_pitch_result)
    workflow.add_node("librosa_fallback", node_librosa_fallback)
    workflow.add_node("filter_short", node_filter_short_notes)
    workflow.add_node("quantize", node_quantize_notes)
    workflow.add_node("ensure_midi", node_ensure_midi_path)

    # 设置入口
    workflow.set_entry_point("separate_vocals")
    workflow.add_edge("separate_vocals", "basic_pitch")
    workflow.add_edge("basic_pitch", "check_result")

    # 条件分支
    def route_after_check(state: AgentState) -> str:
        melody_data = state.get("melody_data")
        if melody_data and melody_data.get("melody_notes") and len(melody_data["melody_notes"]) > 0:
            print("[DEBUG route_after_check] Using Basic Pitch result, going to filter_short")
            return "filter_short"
        else:
            print("[DEBUG route_after_check] Basic Pitch failed or empty, fallback to librosa")
            return "librosa_fallback"

    workflow.add_conditional_edges(
        "check_result",
        route_after_check,
        {
            "filter_short": "filter_short",
            "librosa_fallback": "librosa_fallback",
        }
    )

    workflow.add_edge("librosa_fallback", "filter_short")
    workflow.add_edge("filter_short", "quantize")
    workflow.add_edge("quantize", "ensure_midi")
    workflow.add_edge("ensure_midi", END)

    return workflow.compile()


_extract_graph = None


async def get_extract_graph():
    global _extract_graph
    if _extract_graph is None:
        _extract_graph = await build_extract_graph()
    return _extract_graph