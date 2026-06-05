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
    midi_path = state["midi_path"]
    if not midi_path or not Path(midi_path).exists():
        raise ValueError(f"MIDI 文件不存在: {midi_path}")
    
    # 准备工具链图需要的状态（原样传递）
    sub_state = {
        "task_id": state["task_id"],
        "midi_path": midi_path,
        "instrument": state.get("instrument"),
        "tempo": state.get("tempo"),
    }

    graph = await get_arrange_graph()
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

    return {"arranged_midi_path": arranged_path}