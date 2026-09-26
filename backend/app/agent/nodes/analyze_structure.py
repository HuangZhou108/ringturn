# backend/app/agent/nodes/analyze_structure.py
from app.agent.state import AgentState
from app.agent.tool_graphs.analysis_graph import get_analysis_graph
from app.agent.utils import clean_state
from app.services.llm_service import llm_service
from app.agent.thinking_utils import record_thought

@clean_state
async def analyze_structure_node(state: AgentState) -> dict:
    """
    节点2: 分析音乐结构

    使用预定义的工具链图执行分析，并将结果存入 analysis_result。
    """
    plan = state.get("plan", [])
    if "analyze_structure" not in plan:   
        return {}
    
    profile_id = state.get("profile_id")
    graph = await get_analysis_graph(profile_id=profile_id)
    result_state = await graph.ainvoke(state)
    
    updates = {
        "analysis_result": result_state.get("analysis_result", {})
    }

    # 传递分离相关的顶层字段（若存在）
    for key in ["demucs_separated", "vocals_path", "accompaniment_path", "demucs_stems", "audio_path"]:
        if key in result_state:
            updates[key] = result_state[key]

    # ---- 生成分析总结 ----
    analysis_result = updates.get("analysis_result", {})
    # 收集实际执行的分析模块（非空顶层键）
    executed_modules = [k for k, v in analysis_result.items() if v is not None]
    # 友好名称映射（根据你的 analysis_graph 节点定义）
    module_names = {
        "metadata": "音频元信息",
        "tempo_beats": "节拍和BPM",
        "tempo_variation": "速度变化",
        "loudness": "响度分析",
        "spectral": "频谱分析",
        "sections": "段落结构",
        "msaf_sections": "音乐结构(MSAF)",
        "mood_style": "情绪风格",
        "special_effects": "特殊效果",
        "vocal_presence": "人声检测",
        "piano_presence": "钢琴检测",
        "guitar_presence": "吉他检测",
    }
    tool_names = [module_names.get(k, k) for k in executed_modules if k in module_names]
    if tool_names:
        tool_list = "、".join(tool_names)
        user_req = state.get("user_request", "")[:100]
        plan_desc = state.get("plan_description", "")[:100]
        prompt = f"""用户请求：{user_req}...
规划描述：{plan_desc}...
我们已执行了以下分析模块：{tool_list}。
请用自然语言总结我们调用了哪些分析工具，了解到了哪些方面的信息，以及这些信息对后续改编任务的意义（例如帮助确定合适的乐器、速度、风格等）。只输出总结，不超过100字。"""
        try:
            summary = await llm_service.chat([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=150)
            record_thought(state["task_id"], "analysis", summary)
        except Exception:
            # 降级模板
            default_summary = f"已对音频进行了{tool_list}等方面的分析，这些信息将有助于后续的旋律提取和改编。"
            record_thought(state["task_id"], "analysis", default_summary)

    # ---- LLM 改编决策：结合分析结果 + 用户需求，决定乐器/速度/移调 ----
    try:
        compact = {
            "bpm": (analysis_result.get("tempo_beats") or {}).get("bpm"),
            "has_vocal": analysis_result.get("vocal_presence"),
            "has_piano": analysis_result.get("piano_presence"),
            "has_guitar": analysis_result.get("guitar_presence"),
            "mood_style": analysis_result.get("mood_style"),
        }
        current = {
            "instrument": state.get("instrument", "Acoustic Piano"),
            "tempo": state.get("tempo", 120),
        }
        arrangement = await llm_service.plan_arrangement(
            state.get("user_request", ""),
            compact,
            current,
        )
        record_thought(state["task_id"], "analysis", f"LLM 改编决策: {arrangement}")
    except Exception as e:
        record_thought(state["task_id"], "analysis", f"LLM 改编决策失败，沿用用户参数: {e}")
        arrangement = {}

    if arrangement:
        updates["arrangement_params"] = arrangement
        if arrangement.get("instrument"):
            updates["instrument"] = arrangement["instrument"]
        if arrangement.get("tempo"):
            updates["tempo"] = arrangement["tempo"]

    return updates