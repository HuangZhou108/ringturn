"""
旋律提取工具链图

将原有子 Agent 的流程固化到 LangGraph 中：
1. 分离人声在analysis已处理。
2. 使用 Basic Pitch 提取旋律
   根据用户指定的 duration（目标铃声时长）判断是否需要双轨提取：
      - 如果 duration > 30 秒，则同时提取人声轨道和伴奏轨道的旋律，合并后作为 melody_data
      - 否则只提取人声轨道（如果存在）或原始音频
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
from app.agent.node_registry import register_node, register_condition, NODE_REGISTRY, CONDITION_REGISTRY
_EXTRACT_GRAPH_JSON = Path(__file__).parent / "extract_graph.json"

# ---------- 节点定义 ----------

@register_node("prepare_source")
async def node_prepare_extract_source(state: AgentState) -> Dict[str, Any]:
    """
    根据分离标志和用户目标时长决定提取源和策略。
    """
    demucs_separated = state.get("demucs_separated", False)
    vocals_path = state.get("vocals_path")
    accompaniment_path = state.get("accompaniment_path")
    original_audio_path = state.get("audio_path")
    # 用户指定的目标时长（秒），默认为 30
    target_duration = state.get("duration", 30)

    print(f"[DEBUG] state keys: {state.keys()}")
    print(f"[DEBUG] audio_path={state.get('audio_path')}, vocals_path={state.get('vocals_path')}, accompaniment_path={state.get('accompaniment_path')}, demucs_separated={state.get('demucs_separated')}")

    # 初始默认：使用原始音频
    source_for_melody = original_audio_path
    use_vocal_and_accompaniment = False

    if demucs_separated and vocals_path and accompaniment_path:
        # 根据目标时长判断是否需要双轨提取
        if target_duration > 30:
            use_vocal_and_accompaniment = True
        else:
            # 只提取人声轨道
            source_for_melody = vocals_path

    print(f"[DEBUG] source_for_melody = {source_for_melody}")
    print(f"[DEBUG] use_vocal_and_accompaniment = {use_vocal_and_accompaniment}")

    return {
        "source_for_melody": source_for_melody,
        "use_vocal_and_accompaniment": use_vocal_and_accompaniment,
        "vocals_path": vocals_path,
        "accompaniment_path": accompaniment_path,
    }

# 人声分离节点，已不再使用
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


@register_node("basic_pitch")
async def node_basic_pitch(state: AgentState) -> Dict[str, Any]:
    """
    使用 Basic Pitch 提取旋律。
    如果是双轨模式，分别提取人声和伴奏，然后合并音符。
    """
    task_id = state.get("task_id")
    use_both = state.get("use_vocal_and_accompaniment", False)
    print(f"[DEBUG basic_pitch] use_both = {use_both}, source_for_melody = {state.get('source_for_melody')}, vocals_path = {state.get('vocals_path')}")

    if use_both:
        vocals_path = state.get("vocals_path")
        accompaniment_path = state.get("accompaniment_path")
        record_thought(task_id, "extract_melody", "双轨模式：分别提取人声和伴奏旋律")

        # 提取人声旋律
        vocal_melody = await extract_melody_basic_pitch(vocals_path)
        # 提取伴奏旋律
        accomp_melody = await extract_melody_basic_pitch(accompaniment_path)

        # 合并音符列表
        merged_notes = vocal_melody.get("melody_notes", []) + accomp_melody.get("melody_notes", [])
        # 按开始时间排序
        merged_notes.sort(key=lambda x: x["start"])
        # 合并后的置信度取平均
        conf = (vocal_melody.get("confidence", 0.8) + accomp_melody.get("confidence", 0.8)) / 2
        # MIDI 路径：使用原始音频目录下的合并文件
        original_path = state.get("audio_path", "")
        if original_path:
            midi_path = str(Path(original_path).with_suffix("")) + "_merged.mid"
        else:
            midi_path = "merged.mid"
        Path(midi_path).parent.mkdir(parents=True, exist_ok=True)

        melody_data = {
            "melody_notes": merged_notes,
            "confidence": conf,
            "midi_path": midi_path,
        }
        return {"melody_data": melody_data}
    else:
        source = state.get("source_for_melody")
        if not source:
            # 降级1：如果有人声轨道，使用人声轨道
            source = state.get("vocals_path")
        if not source:
            # 降级2：使用当前音频路径（可能是伴奏或原始音频）
            source = state.get("audio_path")
        if not source:
            raise ValueError("未找到待提取旋律的音频源，且无可用降级路径")
        record_thought(task_id, "extract_melody", f"单轨模式：提取 {source} 的旋律")
        melody_data = await extract_melody_basic_pitch(source)
        return {"melody_data": melody_data}


@register_node("check_result")
async def node_check_basic_pitch_result(state: AgentState) -> Dict[str, Any]:
    """检查 Basic Pitch 结果是否有效，若无效则标记需要降级"""
    melody_data = state.get("melody_data")
    # print(f"[DEBUG check_result] melody_data type: {type(melody_data)}, value: {melody_data}")
    if melody_data and melody_data.get("melody_notes") and len(melody_data["melody_notes"]) > 0:
        # print(f"[DEBUG check_result] melody_notes length: {len(melody_data.get('melody_notes', []))}")
        return {"use_basic_pitch": True}
    else:
        return {"use_basic_pitch": False, "basic_pitch_failed": True}


@register_node("librosa_fallback")
async def node_librosa_fallback(state: AgentState) -> Dict[str, Any]:
    """降级：使用 librosa 提取旋律（双轨模式下降级到只提取人声）"""
    task_id = state.get("task_id")
    use_both = state.get("use_vocal_and_accompaniment", False)

    if use_both:
        vocals_path = state.get("vocals_path")
        record_thought(task_id, "extract_melody", "Basic Pitch 双轨失败，降级为仅使用 librosa 提取人声旋律")
        melody_data = await extract_melody_librosa(vocals_path)
    else:
        source = state.get("source_for_melody") or state.get("audio_path")
        record_thought(task_id, "extract_melody", "Basic Pitch 失败，降级使用 librosa 提取旋律")
        melody_data = await extract_melody_librosa(source)
    return {"melody_data": melody_data}


@register_node("filter_short")
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


@register_node("quantize")
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


@register_node("ensure_midi")
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


# 注册条件路由函数
@register_condition("extract_route_after_check")
def extract_route_after_check(state: AgentState) -> str:
    melody_data = state.get("melody_data")
    if melody_data and melody_data.get("melody_notes") and len(melody_data["melody_notes"]) > 0:
        return "filter_short"
    else:
        return "librosa_fallback"
    

# ---------- 构建图 ----------

async def build_extract_graph():
    """从 JSON 文件动态构建提取旋律子图"""
    import json
    with open(_EXTRACT_GRAPH_JSON, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    workflow = StateGraph(AgentState)
    
    # 添加节点
    for node_def in config["nodes"]:
        node_id = node_def["id"]
        func = NODE_REGISTRY.get(node_id)
        if not func:
            raise ValueError(f"Node '{node_id}' not registered in NODE_REGISTRY")
        workflow.add_node(node_id, func)
    
    # 添加普通边
    for edge in config.get("edges", []):
        workflow.add_edge(edge["from"], edge["to"])
    
    # 添加条件边
    for cond_edge in config.get("conditional_edges", []):
        cond_func = CONDITION_REGISTRY.get(cond_edge["condition"])
        if not cond_func:
            raise ValueError(f"Condition '{cond_edge['condition']}' not registered")
        workflow.add_conditional_edges(
            cond_edge["from"],
            cond_func,
            cond_edge["mapping"]
        )
    
    # 添加默认边（无条件的）
    for edge in config.get("default_edges", []):
        workflow.add_edge(edge["from"], edge["to"])
    
    workflow.set_entry_point(config["entry"])
    # 注意：exit 对应的节点需要连接到 END，但 JSON 中如果 exit 不为空，需自动添加边
    if config.get("exit"):
        workflow.add_edge(config["exit"], END)
    
    return workflow.compile()


_extract_graph = None


async def get_extract_graph():
    global _extract_graph
    if _extract_graph is None:
        _extract_graph = await build_extract_graph()
    return _extract_graph