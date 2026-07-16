import json
from pathlib import Path
from sqlalchemy.orm import Session
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.llm_service import get_llm
from app.agent.state import AgentState
from app.core.config import get_settings
from app.agent.atomic_tools.arrangement import (
    change_instrument_tool, change_tempo_tool, quantize_midi_tool
)
from app.agent.utils import clean_state
from app.services.llm_service import llm_service
from app.agent.thinking_utils import record_thought
import mido
from app.agent.tool_graphs.arrange_graph import get_arrange_graph
settings = get_settings()

@clean_state
async def arrange_node(state: AgentState) -> dict:
    """
    节点5: 乐器改编

    根据用户需求更换乐器、调整风格
    """
    plan = state.get("plan", [])
    if "arrange" not in plan:   
        return {}
    midi_path = state["midi_path"]
    if not midi_path:
        melody_data = state.get("melody_data")
        if isinstance(melody_data, dict):
            midi_path = melody_data.get("midi_path")
    if not midi_path or not Path(midi_path).exists():
        raise ValueError(f"[Arrange] MIDI 文件不存在: {midi_path}")
    
    profile_id = state.get("profile_id")
    # 准备工具链图需要的状态（原样传递）
    sub_state = {
        "task_id": state["task_id"],
        "midi_path": midi_path,
        "instrument": state.get("instrument"),
        "tempo": state.get("tempo"),
    }

    # ---- 开始改编说明 ----
    instrument = state.get("instrument", "未指定")
    tempo = state.get("tempo", "未指定")
    user_request = state.get("user_request", "")
    start_msg = f"开始根据您的需求进行改编："
    record_thought(state["task_id"], "arrange", start_msg)

    graph = await get_arrange_graph(profile_id=profile_id)
    try:
        final_state = await graph.ainvoke(sub_state)
    except Exception as e:
        record_thought(state["task_id"], "arrange", f"arrange_graph 执行失败: {e}")
        raise RuntimeError(f"乐器改编子图失败: {e}") from e

    arranged_path = final_state.get("arranged_midi_path")
    if not arranged_path or not Path(arranged_path).exists():
        raise RuntimeError("改编失败：未生成有效的 MIDI 文件")

    # 验证 MIDI 有效性
    try:
        mido.MidiFile(arranged_path)
    except Exception as e:
        raise RuntimeError(f"改编后的 MIDI 无效: {e}")
    
    # ---- 改编结束说明 ----
    # 收集实际发生的改编
    changes = []
    if state.get("instrument"):
        changes.append(f"乐器设置为 {state['instrument']}")
    if state.get("tempo"):
        changes.append(f"速度调整为 {state['tempo']} BPM")
    change_text = "；".join(changes) if changes else "未进行明显修改"

    plan_desc = state.get("plan_description", "")
    user_req = state.get("user_request", "")[:100]

    prompt = f"""用户请求：{user_req}...
规划描述：{plan_desc}...
已完成的改编：{change_text}。
请用自然语言总结我们进行了哪些改编，以及这些改编与用户任务（铃声改编）的关系。只输出总结，不超过80字。"""
    try:
        summary = await llm_service.chat([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=120)
    except Exception:
        summary = f"已完成改编：{change_text}，这些调整将用于生成符合用户需求的铃声音频。"
    record_thought(state["task_id"], "arrange", summary)

    return {"arranged_midi_path": arranged_path}