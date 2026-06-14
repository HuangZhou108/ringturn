from app.agent.node_registry import register_node
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis import infer_mood_style_tool
from app.agent.thinking_utils import record_thought

@register_node("infer_mood")
async def node_infer_mood(state: AgentState) -> dict:
    audio_path = state.get("audio_path")
    task_id = state.get("task_id")
    user_request = state.get("user_request", "")
    analysis = state.get("analysis_result", {})
    features = {
        "instruments": analysis.get("instruments", {}).get("instruments"),
        "has_vocal": analysis.get("vocal_presence"),
        "bpm": analysis.get("tempo_beats", {}).get("bpm"),
        "key": analysis.get("harmony", {}).get("key")
    }
    try:
        result = await infer_mood_style_tool.func(audio_path=audio_path, user_request=user_request, features=features)
        if task_id:
            record_thought(task_id, "analysis", f"mood_style: {result}")
    except Exception as e:
        if task_id:
            record_thought(task_id, "analysis", f"infer_mood failed: {e}")
        result = {}
    analysis = state.get("analysis_result", {})
    analysis["mood_style"] = result
    return {"analysis_result": analysis}