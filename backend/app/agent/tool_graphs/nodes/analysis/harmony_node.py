from app.agent.node_registry import register_node
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis.harmony import analyze_harmony
from app.agent.thinking_utils import record_thought


@register_node("harmony")
async def node_harmony(state: AgentState) -> dict:
    """检测调性与和弦根音，存入 analysis_result['harmony']，供调性校正与和声编曲使用。"""
    audio_path = state.get("audio_path")
    task_id = state.get("task_id")
    if not audio_path:
        raise ValueError("state 中缺少 audio_path")
    if "analysis_result" not in state or state["analysis_result"] is None:
        state["analysis_result"] = {}

    try:
        result = await analyze_harmony(audio_path=audio_path)
    except Exception as e:
        if task_id:
            record_thought(task_id, "analysis", f"harmony failed: {e}")
        result = None

    state["analysis_result"]["harmony"] = result
    return {"analysis_result": state["analysis_result"]}
