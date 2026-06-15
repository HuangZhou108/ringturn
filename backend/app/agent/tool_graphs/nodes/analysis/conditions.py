from app.agent.node_registry import register_condition
from app.agent.state import AgentState

@register_condition("analysis_route_separation")
def route_separation(state: AgentState) -> str:
    return "separate" if state.get("should_separate") else "no_separate"

@register_condition("analysis_after_separation")
def after_separation_route(state: AgentState) -> str:
    return "fork"

@register_condition("analysis_route_optional")
def route_optional(state: AgentState) -> str:
    decisions = state.get("optional_decisions", {})
    mood = decisions.get("should_infer_mood", False)
    effects = decisions.get("should_detect_effects", False)
    if mood and effects:
        return "both"
    elif mood:
        return "mood_only"
    elif effects:
        return "effects_only"
    else:
        return "none"