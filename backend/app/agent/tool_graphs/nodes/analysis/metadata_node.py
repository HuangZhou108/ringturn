from app.agent.node_registry import register_node
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis import get_metadata_tool
from app.agent.thinking_utils import record_thought

@register_node("metadata")
async def node_metadata(state: AgentState) -> dict:
    audio_path = state.get("audio_path")
    task_id = state.get("task_id")
    if not audio_path:
        raise ValueError("state 中缺少 audio_path")
    if "analysis_result" not in state or state["analysis_result"] is None:
        state["analysis_result"] = {}
    try:
        result = await get_metadata_tool.coroutine(audio_path=audio_path)
        if task_id:
            record_thought(task_id, "analysis", f"metadata: {str(result)[:200]}")
    except Exception as e:
        if task_id:
            record_thought(task_id, "analysis", f"metadata failed: {e}")
        result = None
    state["analysis_result"]["metadata"] = result
    return {"analysis_result": state["analysis_result"]}