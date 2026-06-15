from app.agent.node_registry import register_node
from app.agent.state import AgentState

@register_node("merge")
async def node_merge(state: AgentState) -> dict:
    analysis = state.get("analysis_result", {})
    # 保证关键字段存在
    analysis.setdefault("metadata", {})
    analysis.setdefault("tempo_beats", {})
    analysis.setdefault("tempo_variation", {})
    analysis.setdefault("loudness", {})
    analysis.setdefault("spectral", {})
    analysis.setdefault("sections", {})
    analysis.setdefault("msaf_sections", {})
    return {"analysis_result": analysis}