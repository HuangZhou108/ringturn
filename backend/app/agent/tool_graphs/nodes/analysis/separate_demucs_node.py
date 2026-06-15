from app.agent.node_registry import register_node
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis import separate_sources_demucs
from app.agent.thinking_utils import record_thought

@register_node("separate_demucs")
async def node_separate_demucs(state: AgentState) -> dict:
    audio_path = state.get("audio_path")
    stems = state.get("demucs_stems")
    task_id = state.get("task_id")
    if not stems:
        return {"demucs_separated": False}
    try:
        result = await separate_sources_demucs(
            audio_path=audio_path,
            stems=stems,
            model="htdemucs_ft"
        )
        vocals_path = result.get("vocals_path")
        other_path = result.get("other_path")
        if not vocals_path or not other_path:
            raise RuntimeError("Demucs 分离未生成所需轨道")
        if task_id:
            record_thought(task_id, "analysis", f"Demucs 分离成功: vocals={vocals_path}, other={other_path}")
        return {
            "demucs_separated": True,
            "vocals_path": vocals_path,
            "accompaniment_path": other_path,
            "audio_path": other_path,
            "demucs_stems": stems,
        }
    except Exception as e:
        if task_id:
            record_thought(task_id, "analysis", f"Demucs 分离失败: {e}")
        return {"demucs_separated": False}