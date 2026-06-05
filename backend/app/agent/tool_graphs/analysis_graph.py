# backend/app/agent/tool_graphs/analysis_graph.py
import numpy as np
import asyncio
from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis import (
    get_metadata_tool,
    detect_tempo_beats_tool,
    detect_sections_tool,
    analyze_harmony_tool,
    detect_instruments_tool,
    detect_vocal_tool,
    analyze_loudness_tool,
    analyze_spectral_tool,
    extract_melody_contour_tool,
    detect_tempo_variation_tool,
    infer_mood_style_tool,
    detect_special_effects_tool,
    analyze_yamnet_tool,
)
from app.services.llm_service import llm_service
from .base import wrap_tool, wrap_tool_with_params
import json
from app.agent.thinking_utils import record_thought

# ------------------------------------------------------------
# 1. 包装节点
# ------------------------------------------------------------
node_metadata = wrap_tool(get_metadata_tool.coroutine, "metadata")
node_tempo = wrap_tool(detect_tempo_beats_tool.coroutine, "tempo_beats")
# node_sections = wrap_tool(detect_sections_tool.coroutine, "sections")
node_harmony = wrap_tool(analyze_harmony_tool.coroutine, "harmony")
node_instruments = wrap_tool(detect_instruments_tool.coroutine, "instruments")
node_vocal = wrap_tool(detect_vocal_tool.coroutine, "vocal")
node_loudness = wrap_tool(analyze_loudness_tool.coroutine, "loudness")
node_spectral = wrap_tool(analyze_spectral_tool.coroutine, "spectral")

# 改进的 sections 节点（不使用原来的包装，因为参数不同）
async def node_sections(state: AgentState) -> dict:
    audio_path = state["audio_path"]
    result = await detect_sections_tool.coroutine(audio_path=audio_path)
    if "analysis_result" not in state:
        state["analysis_result"] = {}
    state["analysis_result"]["sections"] = result
    return {"analysis_result": state["analysis_result"]}

# ---------- YAMNet 节点 ----------
async def node_yamnet(state: AgentState) -> dict:
    audio_path = state.get("audio_path")
    if not audio_path:
        raise ValueError("state 中缺少 audio_path")
    
    # 可选的参数配置，可以从 state 或配置中读取
    result = await analyze_yamnet_tool.coroutine(
        audio_path=audio_path,
        top_k=10,
        instrument_threshold=0.3
    )
    
    if "analysis_result" not in state:
        state["analysis_result"] = {}
    state["analysis_result"]["yamnet"] = result
    return {"analysis_result": state["analysis_result"]}

# 需要额外参数的节点
def get_bpm_from_state(state: AgentState):
    return state.get("analysis_result", {}).get("tempo_beats", {}).get("bpm", 120)

def get_sections_from_state(state: AgentState):
    return state.get("analysis_result", {}).get("sections", {}).get("sections", [])

node_melody = wrap_tool_with_params(
    extract_melody_contour_tool.coroutine,
    "melody_contour",
    param_extractors={"bpm": get_bpm_from_state, "sections": get_sections_from_state}
)

node_tempo_var = wrap_tool_with_params(
    detect_tempo_variation_tool.coroutine,
    "tempo_variation",
    param_extractors={"bpm": get_bpm_from_state}
)

# ------------------------------------------------------------
# 2. LLM 决策节点
# ------------------------------------------------------------
async def decide_optional_node(state: AgentState) -> dict:
    user_request = state.get("user_request", "")
    analysis = state.get("analysis_result", {})
    instruments = analysis.get("instruments", {}).get("instruments", [])
    has_vocal = analysis.get("vocal", {}).get("has_vocal", False)
    prompt = f"""用户需求：{user_request}
已检测乐器：{instruments}
是否有人声：{has_vocal}
请判断是否需要以下两项分析（回答 JSON）：
- should_infer_mood: 是否需要推断情绪、风格？通常需要，除非用户明确不需要。
- should_detect_effects: 是否需要检测混响、延迟等效果？仅在用户提到"保留原有效果"或风格特殊时。
输出格式：{{"should_infer_mood": bool, "should_detect_effects": bool}}"""
    try:
        resp = await llm_service.chat([{"role": "user", "content": prompt}], temperature=0.2)
        decisions = json.loads(resp)
    except:
        decisions = {"should_infer_mood": True, "should_detect_effects": False}
    return {"optional_decisions": decisions}

def route_optional(state: AgentState) -> str:
    decisions = state.get("optional_decisions", {})
    mood = decisions.get("should_infer_mood", False)
    effects = decisions.get("should_detect_effects", False)
    if mood and effects:
        return "both"
    elif mood:
        return "mood_only"
    elif effects:
        return "effects_only"
    else:
        return "none"

# 可选工具节点
async def node_infer_mood(state: AgentState) -> dict:
    audio_path = state["audio_path"]
    task_id = state.get("task_id")
    user_request = state.get("user_request", "")
    # 收集已有特征作为 features
    analysis = state.get("analysis_result", {})
    features = {
        "instruments": analysis.get("instruments", {}).get("instruments"),
        "has_vocal": analysis.get("vocal", {}).get("has_vocal"),
        "bpm": analysis.get("tempo_beats", {}).get("bpm"),
        "key": analysis.get("harmony", {}).get("key")
    }

    if task_id:
        record_thought(task_id, "analysis", "开始推断情绪和风格...")
    try:
        result = await infer_mood_style_tool.func(audio_path=audio_path, user_request=user_request, features=features)
        if task_id:
            record_thought(task_id, "analysis", f"推断结果: {result}")
    except Exception as e:
        if task_id:
            record_thought(task_id, "analysis", f"推断失败: {e}")
        result = {}
    if "analysis_result" not in state:
        state["analysis_result"] = {}
    state["analysis_result"]["mood_style"] = result
    return {"analysis_result": state["analysis_result"]}

# 待增加到思考过程
async def node_detect_effects(state: AgentState) -> dict:
    audio_path = state["audio_path"]
    result = await detect_special_effects_tool.func(audio_path=audio_path)
    if "analysis_result" not in state:
        state["analysis_result"] = {}
    state["analysis_result"]["special_effects"] = result
    return {"analysis_result": state["analysis_result"]}

# 合并节点
async def node_merge(state: AgentState) -> dict:
    # 可以添加默认值填充逻辑
    analysis = state.get("analysis_result", {})
    # 保证关键字段存在
    analysis.setdefault("metadata", {})
    analysis.setdefault("tempo_beats", {})
    analysis.setdefault("tempo_variation", {})
    analysis.setdefault("loudness", {})
    analysis.setdefault("spectral", {})
    analysis.setdefault("sections", {})
    analysis.setdefault("yamnet", {})
    return {"analysis_result": analysis}

# ------------------------------------------------------------
# 3. 构建图
# ------------------------------------------------------------
async def build_analysis_graph() -> StateGraph:
    # (调试输出)检查工具正确性
    # print("[DEBUG] Checking tools:")
    # tools_to_check = [
    #     ("get_metadata_tool", get_metadata_tool),
    #     ("detect_tempo_beats_tool", detect_tempo_beats_tool),
    #     ("detect_sections_tool", detect_sections_tool),
    #     ("analyze_harmony_tool", analyze_harmony_tool),
    #     ("detect_instruments_tool", detect_instruments_tool),
    #     ("detect_vocal_tool", detect_vocal_tool),
    #     ("analyze_loudness_tool", analyze_loudness_tool),
    #     ("analyze_spectral_tool", analyze_spectral_tool),
    #     ("extract_melody_contour_tool", extract_melody_contour_tool),
    #     ("detect_tempo_variation_tool", detect_tempo_variation_tool),
    #     ("infer_mood_style_tool", infer_mood_style_tool),
    #     ("detect_special_effects_tool", detect_special_effects_tool),
    # ]
    # for name, tool in tools_to_check:
    #     print(f"  {name}: {tool} (func: {getattr(tool, 'func', 'NO_FUNC')})")
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("metadata", node_metadata)
    workflow.add_node("yamnet", node_yamnet)
    workflow.add_node("tempo", node_tempo)
    workflow.add_node("tempo_var", node_tempo_var)
    workflow.add_node("loudness", node_loudness)
    workflow.add_node("spectral", node_spectral)
    workflow.add_node("sections", node_sections)
    workflow.add_node("merge", node_merge)

    # 设置入口
    workflow.set_entry_point("metadata")
    workflow.add_edge("metadata", "yamnet")

    # yamnet 之后并行执行其他所有分析
    for node in ["tempo", "tempo_var", "loudness", "spectral", "sections"]:
        workflow.add_edge("yamnet", node)

    # 所有并行节点汇聚到 merge
    for node in ["tempo", "tempo_var", "loudness", "spectral", "sections"]:
        workflow.add_edge(node, "merge")
    workflow.add_edge("merge", END)

    return workflow.compile()

_analysis_graph = None

async def get_analysis_graph():
    global _analysis_graph
    if _analysis_graph is None:
        _analysis_graph = await build_analysis_graph()
    return _analysis_graph