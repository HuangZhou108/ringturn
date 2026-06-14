import json
from app.agent.node_registry import register_node
from app.agent.state import AgentState
from app.services.llm_service import llm_service

@register_node("optional_decision")
async def node_optional_decision(state: AgentState) -> dict:
    user_request = state.get("user_request", "")
    analysis = state.get("analysis_result", {})
    instruments = analysis.get("instruments", {}).get("instruments", [])
    has_vocal = analysis.get("vocal_presence", False)
    prompt = f"""用户需求：{user_request}
已检测乐器：{instruments}
是否有人声：{has_vocal}
请判断是否需要以下两项分析（回答 JSON）：
- should_infer_mood: 是否需要推断情绪、风格？通常需要，除非用户明确不需要。
- should_detect_effects: 是否需要检测混响、延迟等效果？仅在用户提到"保留原有效果"或风格特殊时。
输出格式：{{"should_infer_mood": bool, "should_detect_effects": bool}}"""
    try:
        resp = await llm_service.chat([{"role": "user", "content": prompt}], temperature=0.2)
        decisions = json.loads(resp)
    except:
        decisions = {"should_infer_mood": True, "should_detect_effects": False}
    return {"optional_decisions": decisions}