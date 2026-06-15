from app.agent.node_registry import register_node
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis import classify_vocal_presence, classify_piano_presence, classify_guitar_presence
from app.agent.thinking_utils import record_thought

@register_node("clap_classify")
async def node_clap_classify(state: AgentState) -> dict:
    audio_path = state.get("audio_path")
    task_id = state.get("task_id")
    if not audio_path:
        raise ValueError("state 中缺少 audio_path")
    try:
        vocal_res = await classify_vocal_presence(audio_path)
        piano_res = await classify_piano_presence(audio_path)
        guitar_res = await classify_guitar_presence(audio_path)
        has_vocal = "singing" in vocal_res["predicted_label"].lower()
        has_piano = "prominent" in piano_res["predicted_label"].lower()
        has_guitar = "prominent" in guitar_res["predicted_label"].lower()
        if task_id:
            record_thought(task_id, "analysis", f"CLAP: vocal={has_vocal}, piano={has_piano}, guitar={has_guitar}")
    except Exception as e:
        if task_id:
            record_thought(task_id, "analysis", f"CLAP classification failed: {e}")
        has_vocal = has_piano = has_guitar = False
    analysis = state.get("analysis_result", {})
    analysis["vocal_presence"] = has_vocal
    analysis["piano_presence"] = has_piano
    analysis["guitar_presence"] = has_guitar
    return {"analysis_result": analysis}