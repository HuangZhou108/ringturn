from app.agent.node_registry import register_node
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis import msaf_analyze_tool
from app.agent.thinking_utils import record_thought

@register_node("msaf")
async def node_msaf(state: AgentState) -> dict:
    audio_path = state.get("audio_path")
    task_id = state.get("task_id")
    if not audio_path:
        raise ValueError("state 中缺少 audio_path")
    if "analysis_result" not in state or state["analysis_result"] is None:
        state["analysis_result"] = {}
    try:
        result = await msaf_analyze_tool.coroutine(audio_path=audio_path, algorithm="scluster")
        if task_id:
            record_thought(task_id, "analysis", f"msaf: {str(result)[:200]}")
    except Exception as e:
        if task_id:
            record_thought(task_id, "analysis", f"msaf failed: {e}")
        result = {"sections": [], "boundaries": [], "labels": []}
    state["analysis_result"]["msaf_sections"] = result
    return {"analysis_result": state["analysis_result"]}