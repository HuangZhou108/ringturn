from app.agent.node_registry import register_node
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis import detect_sections_tool
from app.agent.thinking_utils import record_thought

@register_node("sections")
async def node_sections(state: AgentState) -> dict:
    audio_path = state.get("audio_path")
    task_id = state.get("task_id")
    if not audio_path:
        raise ValueError("state 中缺少 audio_path")
    if "analysis_result" not in state or state["analysis_result"] is None:
        state["analysis_result"] = {}
    try:
        result = await detect_sections_tool.coroutine(audio_path=audio_path)
        if task_id:
            record_thought(task_id, "analysis", f"sections: {str(result)[:200]}")
    except Exception as e:
        if task_id:
            record_thought(task_id, "analysis", f"sections failed: {e}")
        result = None
    state["analysis_result"]["sections"] = result
    return {"analysis_result": state["analysis_result"]}