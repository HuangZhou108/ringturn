from app.agent.node_registry import register_node
from app.agent.state import AgentState

@register_node("decide_separation")
async def node_decide_separation(state: AgentState) -> dict:
    has_vocal = state.get("analysis_result", {}).get("vocal_presence", False)
    print(f"[DEBUG] decide_separation: has_vocal={has_vocal}")
    if has_vocal:
        return {"should_separate": True, "demucs_stems": "4"}
    else:
        return {"should_separate": False, "demucs_stems": None}