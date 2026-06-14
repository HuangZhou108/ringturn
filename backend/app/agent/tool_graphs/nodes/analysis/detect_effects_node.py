from app.agent.node_registry import register_node
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis import detect_special_effects_tool
from app.agent.thinking_utils import record_thought

@register_node("detect_effects")
async def node_detect_effects(state: AgentState) -> dict:
    audio_path = state.get("audio_path")
    task_id = state.get("task_id")
    try:
        result = await detect_special_effects_tool.func(audio_path=audio_path)
        if task_id:
            record_thought(task_id, "analysis", f"special_effects: {result}")
    except Exception as e:
        if task_id:
            record_thought(task_id, "analysis", f"detect_effects failed: {e}")
        result = {}
    analysis = state.get("analysis_result", {})
    analysis["special_effects"] = result
    return {"analysis_result": analysis}