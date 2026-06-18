from app.agent.node_registry import register_node
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis import detect_tempo_variation_tool
from app.agent.thinking_utils import record_thought
from app.agent.utils import log_tool_call

@register_node("tempo_var")
async def node_tempo_var(state: AgentState) -> dict:
    audio_path = state.get("audio_path")
    task_id = state.get("task_id")
    if not audio_path:
        raise ValueError("state 中缺少 audio_path")
    if "analysis_result" not in state or state["analysis_result"] is None:
        state["analysis_result"] = {}
    bpm = state.get("analysis_result", {}).get("tempo_beats", {}).get("bpm", 120)
    try:
        result = await log_tool_call(
            task_id=task_id,
            step_name="analysis",
            tool_func=detect_tempo_variation_tool.coroutine,
            audio_path=audio_path,
            bpm=bpm,
            tool_name="detect_tempo_variation"
        )
        # if task_id:
        #     record_thought(task_id, "analysis", f"tempo_variation: {str(result)[:200]}")
    except Exception as e:
        if task_id:
            record_thought(task_id, "analysis", f"tempo_variation failed: {e}")
        result = None
    state["analysis_result"]["tempo_variation"] = result
    return {"analysis_result": state["analysis_result"]}