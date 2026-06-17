from app.agent.node_registry import register_node
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis import get_metadata_tool
from app.agent.thinking_utils import record_thought
from app.agent.utils import log_tool_call

@register_node("metadata")
async def node_metadata(state: AgentState) -> dict:
    audio_path = state.get("audio_path")
    task_id = state.get("task_id")
    if not audio_path:
        raise ValueError("state 中缺少 audio_path")
    if "analysis_result" not in state or state["analysis_result"] is None:
        state["analysis_result"] = {}
    try:
        result = await log_tool_call(
            task_id=task_id,
            step_name="analysis",
            tool_func=get_metadata_tool.coroutine,
            audio_path=audio_path,
            tool_name="get_metadata"
        )
        # if task_id:
        #     record_thought(task_id, "analysis", f"metadata: {str(result)[:200]}")
    except Exception as e:
        if task_id:
            record_thought(task_id, "analysis", f"metadata failed: {e}")
        result = None
    state["analysis_result"]["metadata"] = result
    return {"analysis_result": state["analysis_result"]}