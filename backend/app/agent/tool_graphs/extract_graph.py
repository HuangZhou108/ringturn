"""
旋律提取工具链图

将原有子 Agent 的流程固化到 LangGraph 中：
1. 分离人声在 analysis 已处理。
2. 使用 Basic Pitch 提取旋律（单一主旋律源，禁止双轨拼接）：
      - 若已分离且存在人声轨 → 只提取人声轨（人声即主旋律）
      - 否则 → 提取原始音频（纯音乐 / 分离失败时）
3. 若 Basic Pitch 失败或返回空，降级使用 librosa 提取
4. 在量化前稳定化单旋律，抑制短碎音、叠音和颤音误检
5. 量化音符（若有 BPM 信息）
6. 输出最终的 melody_data
"""

import os
from pathlib import Path
from typing import Any, Dict
import json

from langgraph.graph import StateGraph, END

from app.agent.state import AgentState
from app.agent.melody_source import select_melody_sources
from app.agent.atomic_tools.melody.vocal_separation import separate_vocals
from app.agent.atomic_tools.melody.extract_with_basic_pitch import extract_melody_basic_pitch
from app.agent.atomic_tools.melody.extract_with_crepe import extract_melody_crepe
from app.agent.atomic_tools.melody.extract_with_librosa import extract_melody_librosa
from app.agent.atomic_tools.melody.stabilize_notes import stabilize_melody_notes
from app.agent.atomic_tools.melody.quantize_notes import quantize_notes
from app.agent.atomic_tools.melody.merge_notes import merge_notes
from app.agent.atomic_tools.melody.snap_to_key import snap_to_key
from app.agent.atomic_tools.quality.melody_quality import evaluate_melody_quality
from app.agent.thinking_utils import record_thought
from app.agent.utils import log_tool_call
from app.agent.utils import clean_state
from app.agent.node_registry import register_node, register_condition, NODE_REGISTRY, CONDITION_REGISTRY
from app.db.session import SessionLocal
from app.models import ToolPreference

_EXTRACT_GRAPH_JSON = Path(__file__).parent / "extract_graph.json"
_extract_graph_cache = {}


def _same_audio_path(first: str | None, second: str | None) -> bool:
    """跨平台比较两个音频路径，不要求文件仍然存在。"""
    if not first or not second:
        return False
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(
        os.path.abspath(second)
    )


# ---------- 节点定义 ----------

@register_node("prepare_source")
async def node_prepare_extract_source(state: AgentState) -> Dict[str, Any]:
    """
    分别决定旋律提取源与和声上下文源。

    旋律提取只认单一主旋律源，禁止双轨拼接。
    - 若已分离且存在有效的人声轨（vocals.wav）→ 从人声提取主旋律
    - 若人声轨不可用 → 回退原始音频，保持完整时间轴
    - 伴奏 stem 只作为和声上下文，不参与本节点的旋律提取
    """
    selection = select_melody_sources(
        original_audio_path=state.get("audio_path"),
        vocals_path=state.get("vocals_path"),
        accompaniment_path=state.get("accompaniment_path"),
        demucs_separated=state.get("demucs_separated", False),
    )
    melody_source_path = selection["melody_source_path"]
    harmony_source_path = selection["harmony_source_path"]

    record_thought(
        state.get("task_id"),
        "extract_melody",
        f"旋律源: {melody_source_path}；和声源: {harmony_source_path}；策略: {selection['reason']}",
    )

    return {
        "melody_source_path": melody_source_path,
        "harmony_source_path": harmony_source_path,
        # 保留旧字段，兼容已有 checkpoint 和用户自定义的 extract graph。
        "source_for_melody": melody_source_path,
        "vocals_path": state.get("vocals_path"),
        "accompaniment_path": state.get("accompaniment_path"),
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
    使用 Basic Pitch 转录主旋律源。

    只处理单一来源（优先人声轨），不再双轨拼接。
    """
    task_id = state.get("task_id")
    source = (
        state.get("melody_source_path")
        or state.get("source_for_melody")
        or state.get("audio_path")
    )
    if not source:
        raise ValueError("未找到待提取旋律的音频源，且无可用降级路径")
    record_thought(task_id, "extract_melody", f"Basic Pitch 多音转录 {source}")
    melody_data = await log_tool_call(
        task_id=task_id,
        step_name="extract_melody",
        tool_func=extract_melody_basic_pitch,
        audio_path=source,
        tool_name="extract_melody_basic_pitch"
    )
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
    """降级：使用 librosa 提取旋律（单一主旋律源）"""
    task_id = state.get("task_id")
    source = (
        state.get("melody_source_path")
        or state.get("source_for_melody")
        or state.get("audio_path")
    )
    if not source:
        raise ValueError("未找到 librosa 降级提取所需的音频源")
    record_thought(task_id, "extract_melody", "Basic Pitch 失败，降级使用 librosa 提取旋律")
    melody_data = await log_tool_call(
        task_id=task_id,
        step_name="extract_melody",
        tool_func=extract_melody_librosa,
        audio_path=source,
        tool_name="extract_melody_librosa"
    )
    return {"melody_data": melody_data}


@register_node("filter_short")
async def node_filter_short_notes(state: AgentState) -> Dict[str, Any]:
    """量化前稳定化主旋律，避免极短误检被放大成可听见的碎音。"""
    melody_data = state.get("melody_data")
    if not melody_data or not melody_data.get("melody_notes"):
        return {"melody_data": melody_data}

    notes = melody_data["melody_notes"]
    is_vocal_source = _same_audio_path(
        state.get("melody_source_path") or state.get("source_for_melody"),
        state.get("vocals_path"),
    )
    # 人声中的辅音、滑音和颤音更容易触发短误检；原始混音降级路径保持
    # 较保守的阈值，避免误删纯器乐中的快速经过音。
    min_duration = 0.1 if is_vocal_source else 0.05
    stabilized = await log_tool_call(
        task_id=state.get("task_id"),
        step_name="extract_melody",
        tool_func=stabilize_melody_notes,
        melody_notes=notes,
        min_duration=min_duration,
        onset_tolerance=0.04 if is_vocal_source else 0.025,
        merge_gap=0.1 if is_vocal_source else 0.05,
        blip_duration=0.18 if is_vocal_source else 0.12,
        tool_name="stabilize_melody_notes"
    )
    record_thought(
        state.get("task_id"),
        "extract_melody",
        f"旋律稳定化: {len(notes)} → {len(stabilized)} 个音符"
        f"（{'人声' if is_vocal_source else '通用'}参数）",
    )
    melody_data["melody_notes"] = stabilized
    return {"melody_data": melody_data}


@register_node("quantize")
async def node_quantize_notes(state: AgentState) -> Dict[str, Any]:
    """量化音符，对齐到节拍网格（需要 BPM）"""
    melody_data = state.get("melody_data")
    if not melody_data or not melody_data.get("melody_notes"):
        return {"melody_data": melody_data}

    # 尝试获取 BPM：优先从 analysis_result 中取，否则用默认值 120
    analysis = state.get("analysis_result", {})
    if not isinstance(analysis, dict):
        analysis = {}
    bpm = analysis.get("tempo_beats", {}).get("bpm") or 120
    # 网格大小：16分音符 = 0.25 拍
    grid = 0.25
    quantized_notes = await log_tool_call(
        task_id=state.get("task_id"),
        step_name="extract_melody",
        tool_func=quantize_notes,
        melody_notes=melody_data["melody_notes"],
        grid=grid,
        bpm=bpm,
        tool_name="quantize_notes"
    )
    melody_data["melody_notes"] = quantized_notes
    return {"melody_data": melody_data}


@register_node("merge")
async def node_merge_notes(state: AgentState) -> Dict[str, Any]:
    """合并碎片化的相邻同音高音符，提升旋律连贯性"""
    melody_data = state.get("melody_data")
    if not melody_data or not melody_data.get("melody_notes"):
        return {"melody_data": melody_data}

    notes = melody_data["melody_notes"]
    merged = await log_tool_call(
        task_id=state.get("task_id"),
        step_name="extract_melody",
        tool_func=merge_notes,
        melody_notes=notes,
        merge_gap=0.05,
        tool_name="merge_notes"
    )
    melody_data["melody_notes"] = merged
    return {"melody_data": melody_data}


@register_node("snap")
async def node_snap_to_key(state: AgentState) -> Dict[str, Any]:
    """调性校正：修复八度误判 + snap 到调内音阶"""
    melody_data = state.get("melody_data")
    if not melody_data or not melody_data.get("melody_notes"):
        return {"melody_data": melody_data}

    harmony = (state.get("analysis_result") or {}).get("harmony") or {}
    key_midi = harmony.get("key_midi")
    mode = harmony.get("mode", "major")
    if key_midi is None:
        # 无调性信息则跳过
        return {"melody_data": melody_data}

    notes = melody_data["melody_notes"]
    snapped = await log_tool_call(
        task_id=state.get("task_id"),
        step_name="extract_melody",
        tool_func=snap_to_key,
        melody_notes=notes,
        key_midi=key_midi,
        mode=mode,
        tool_name="snap_to_key"
    )
    melody_data["melody_notes"] = snapped
    return {"melody_data": melody_data}


@register_node("ensure_midi")
async def node_ensure_midi_path(state: AgentState) -> Dict[str, Any]:
    """执行旋律可用性门禁，并确保 melody_data 包含有效 midi_path。"""
    melody_data = state.get("melody_data")
    if not melody_data:
        raise ValueError("melody_data 为空，无法生成 MIDI 路径")

    analysis = state.get("analysis_result") or {}
    metadata = (analysis.get("metadata") or {}) if isinstance(analysis, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    quality_report = evaluate_melody_quality(
        melody_data.get("melody_notes"),
        audio_duration=metadata.get("duration"),
    )
    melody_data["melody_quality_report"] = quality_report
    record_thought(
        state.get("task_id"),
        "extract_melody",
        f"旋律质量得分: {quality_report['score']}，"
        f"通过: {quality_report['passed']}，可继续: {quality_report['usable']}，"
        f"问题: {quality_report['issue_codes']}",
    )
    if not quality_report["usable"]:
        messages = [issue["message"] for issue in quality_report["issues"]]
        raise RuntimeError(f"旋律质量门禁未通过: {'；'.join(messages)}")

    if melody_data.get("midi_path") and Path(melody_data["midi_path"]).exists():
        return {"melody_data": melody_data}  # 已有有效路径，仍需持久化质量报告

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

async def build_extract_graph(config: dict = None):
    """从 JSON 文件动态构建提取旋律子图"""
    import json
    if config is None:
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


async def get_extract_graph(profile_id: int = None):
    cache_key = profile_id if profile_id is not None else "default"
    if cache_key in _extract_graph_cache:
        return _extract_graph_cache[cache_key]
    
    custom_config = None
    if profile_id is not None:
        db = SessionLocal()
        try:
            pref = db.query(ToolPreference).filter(ToolPreference.profile_id == profile_id).first()
            if pref and pref.extract_graph_config:
                custom_config = json.loads(pref.extract_graph_config)
        finally:
            db.close()
    
    graph = await build_extract_graph(config=custom_config)
    _extract_graph_cache[cache_key] = graph
    return graph
