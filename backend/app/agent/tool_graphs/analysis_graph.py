# backend/app/agent/tool_graphs/analysis_graph.py
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
node_sections = wrap_tool(detect_sections_tool.coroutine, "sections")
node_harmony = wrap_tool(analyze_harmony_tool.coroutine, "harmony")
node_instruments = wrap_tool(detect_instruments_tool.coroutine, "instruments")
node_vocal = wrap_tool(detect_vocal_tool.coroutine, "vocal")
node_loudness = wrap_tool(analyze_loudness_tool.coroutine, "loudness")
node_spectral = wrap_tool(analyze_spectral_tool.coroutine, "spectral")

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
    if analysis.get("tempo_beats") is None:
        analysis["tempo_beats"] = {"bpm": 120, "beat_times": [], "downbeat_times": [], "time_signature": "4/4"}
    # 其他...
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
    workflow.add_node("tempo", node_tempo)
    workflow.add_node("sections", node_sections)
    workflow.add_node("harmony", node_harmony)
    workflow.add_node("instruments", node_instruments)
    workflow.add_node("vocal", node_vocal)
    workflow.add_node("loudness", node_loudness)
    workflow.add_node("spectral", node_spectral)
    workflow.add_node("melody", node_melody)
    workflow.add_node("tempo_var", node_tempo_var)
    workflow.add_node("decide_optional", decide_optional_node)
    workflow.add_node("infer_mood", node_infer_mood)
    workflow.add_node("detect_effects", node_detect_effects)
    workflow.add_node("merge", node_merge)

    # 设置入口
    workflow.set_entry_point("metadata")

    # 阶段1 -> 阶段2（并行节点）
    parallel_nodes = ["tempo", "sections", "harmony", "instruments", "vocal", "loudness", "spectral"]
    for node in parallel_nodes:
        workflow.add_edge("metadata", node)

    # 阶段2 -> 阶段3（部分依赖）
    workflow.add_edge("tempo", "melody")
    workflow.add_edge("sections", "melody")
    workflow.add_edge("tempo", "tempo_var")
    # 确保所有阶段2的节点都完成才能进入 decide_optional（需要收集所有输出）
    # 方法：为每个阶段2节点添加边到 decide_optional
    for node in parallel_nodes:
        workflow.add_edge(node, "decide_optional")
    workflow.add_edge("melody", "decide_optional")
    workflow.add_edge("tempo_var", "decide_optional")

    # 条件边
    workflow.add_conditional_edges(
        "decide_optional",
        route_optional,
        {
            "both": "infer_mood",   # 会同时执行两个，需要并行处理
            "mood_only": "infer_mood",
            "effects_only": "detect_effects",
            "none": "merge",
        }
    )

    # 处理 both 情况：infer_mood 和 detect_effects 并行，然后都指向 merge
    # 需要添加并行路由：可以使用一个虚拟节点或直接添加两条边
    # 这里简单处理：在 both 时，先执行 infer_mood，再执行 detect_effects，最后 merge
    # 更好的实现是使用 LangGraph 的 Send API，但为了简化，我们顺序执行（按需可改进）
    # 修改条件边：如果 both，则先到 infer_mood，然后 infer_mood 之后再到 detect_effects，再到 merge
    # 更清晰：在 both 分支上，添加一个中间节点 parallel_gate
    # 我将在下面添加一个 parallel_gate 节点来处理并行
    # 重新设计：添加一个节点 "parallel_gate"，当 both 时，调用该节点，内部并行执行两个工具
    # 但由于 LangGraph 原生支持多边，可以这样：
    # workflow.add_edge("infer_mood", "detect_effects")
    # workflow.add_edge("detect_effects", "merge")
    # 这样顺序执行，也可以接受。
    # 为简单，我选择顺序执行 both: 先 mood 后 effects。
    # 但为了更高效，可使用 asyncio.gather 在节点内部。见下：

    # 覆盖 both 分支的处理：添加一个自定义节点
    # 待增加到思考过程
    async def parallel_optional_node(state: AgentState) -> dict:
        # 并行执行两个工具
        audio_path = state["audio_path"]
        user_request = state.get("user_request", "")
        analysis = state.get("analysis_result", {})
        features = {
            "instruments": analysis.get("instruments", {}).get("instruments"),
            "has_vocal": analysis.get("vocal", {}).get("has_vocal"),
            "bpm": analysis.get("tempo_beats", {}).get("bpm"),
            "key": analysis.get("harmony", {}).get("key")
        }
        mood_task = infer_mood_style_tool.func(audio_path=audio_path, user_request=user_request, features=features)
        effects_task = detect_special_effects_tool.func(audio_path=audio_path)
        mood_res, effects_res = await asyncio.gather(mood_task, effects_task, return_exceptions=True)
        if "analysis_result" not in state:
            state["analysis_result"] = {}
        if not isinstance(mood_res, Exception):
            state["analysis_result"]["mood_style"] = mood_res
        if not isinstance(effects_res, Exception):
            state["analysis_result"]["special_effects"] = effects_res
        return {"analysis_result": state["analysis_result"]}

    workflow.add_node("parallel_optional", parallel_optional_node)

    # 修改条件边
    def route_optional_v2(state: AgentState) -> str:
        decisions = state.get("optional_decisions", {})
        mood = decisions.get("should_infer_mood", False)
        effects = decisions.get("should_detect_effects", False)
        if mood and effects:
            return "parallel"
        elif mood:
            return "mood"
        elif effects:
            return "effects"
        else:
            return "none"

    workflow.add_conditional_edges(
        "decide_optional",
        route_optional_v2,
        {
            "parallel": "parallel_optional",
            "mood": "infer_mood",
            "effects": "detect_effects",
            "none": "merge",
        }
    )
    workflow.add_edge("parallel_optional", "merge")
    workflow.add_edge("infer_mood", "merge")
    workflow.add_edge("detect_effects", "merge")

    # 设置结束
    workflow.add_edge("merge", END)

    return workflow.compile()

_analysis_graph = None

async def get_analysis_graph():
    global _analysis_graph
    if _analysis_graph is None:
        _analysis_graph = await build_analysis_graph()
    return _analysis_graph