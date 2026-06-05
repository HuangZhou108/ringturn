"""
乐器改编工具链图

固定顺序：
1. change_instrument  -> 中间 MIDI
2. change_tempo       -> 最终 MIDI（若用户指定了 tempo）
3. 若未指定 tempo，则直接将中间文件重命名为最终文件
"""

from pathlib import Path
from typing import Dict, Any
from langgraph.graph import StateGraph, END

from app.agent.state import AgentState
from app.agent.atomic_tools.arrangement.change_instrument import change_instrument
from app.agent.atomic_tools.arrangement.change_tempo import change_tempo
from app.agent.thinking_utils import record_thought
from app.agent.utils import clean_state
from app.core.config import get_settings

settings = get_settings()


# ---------- 节点定义 ----------

async def node_change_instrument(state: AgentState) -> Dict[str, Any]:
    """将乐器更换为目标乐器，输出临时 MIDI 文件"""
    midi_path = state["midi_path"]
    if not midi_path or not Path(midi_path).exists():
        raise ValueError(f"MIDI 文件不存在: {midi_path}")
    
    target_instrument = state.get("instrument", "piano")
    task_id = state["task_id"]
    task_dir = Path(settings.RINGTONES_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    temp_path = str(task_dir / "arrange_instr.mid")

    record_thought(task_id, "arrange", f"更换乐器为 {target_instrument}，输入 MIDI: {midi_path}")
    try:
        await change_instrument(midi_path, target_instrument, temp_path)
        record_thought(task_id, "arrange", f"乐器更换完成，临时文件: {temp_path}")
    except Exception as e:
        record_thought(task_id, "arrange", f"change_instrument 失败: {e}")
        raise RuntimeError(f"乐器改编失败: {e}") from e

    return {"arrange_temp_path": temp_path}


async def node_change_tempo(state: AgentState) -> Dict[str, Any]:
    """调整速度（若用户指定了 tempo）"""
    temp_path = state.get("arrange_temp_path")
    if temp_path is None:
        raise KeyError("arrange_temp_path not found in state. Ensure change_instrument node executed successfully.")
    new_bpm = state.get("tempo")
    task_id = state["task_id"]
    task_dir = Path(settings.RINGTONES_DIR) / task_id
    final_path = str(task_dir / "arrange_arranged.mid")

    if not new_bpm:
        # 未提供 tempo，直接重命名临时文件为最终文件
        Path(temp_path).rename(final_path)
        record_thought(task_id, "arrange", "未指定 tempo，跳过速度调整")
        return {"arranged_midi_path": final_path}

    record_thought(task_id, "arrange", f"调整速度至 {new_bpm} BPM...")
    await change_tempo(temp_path, new_bpm, final_path)
    record_thought(task_id, "arrange", f"速度调整完成，最终 MIDI: {final_path}")

    return {"arranged_midi_path": final_path}


async def node_finalize(state: AgentState) -> Dict[str, Any]:
    """当没有 tempo 节点时，直接将临时文件作为最终文件"""
    temp_path = state.get("arrange_temp_path")
    if temp_path is None:
        raise KeyError("arrange_temp_path not found in state. Ensure change_instrument node executed successfully.")
    task_id = state["task_id"]
    task_dir = Path(settings.RINGTONES_DIR) / task_id
    final_path = str(task_dir / "arrange_arranged.mid")

    if not Path(final_path).exists():
        Path(temp_path).rename(final_path)
        record_thought(task_id, "arrange", f"未进行速度调整，最终 MIDI: {final_path}")

    return {"arranged_midi_path": final_path}


# ---------- 路由条件 ----------

def should_change_tempo(state: AgentState) -> str:
    """判断是否需要执行速度调整节点"""
    if state.get("tempo"):
        return "change_tempo"
    else:
        return "finalize"


# ---------- 构建图 ----------

async def build_arrange_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("change_instrument", node_change_instrument)
    workflow.add_node("change_tempo", node_change_tempo)
    workflow.add_node("finalize", node_finalize)

    workflow.set_entry_point("change_instrument")
    workflow.add_conditional_edges(
        "change_instrument",
        should_change_tempo,
        {
            "change_tempo": "change_tempo",
            "finalize": "finalize",
        }
    )
    workflow.add_edge("change_tempo", END)
    workflow.add_edge("finalize", END)

    return workflow.compile()


_arrange_graph = None


async def get_arrange_graph():
    global _arrange_graph
    if _arrange_graph is None:
        _arrange_graph = await build_arrange_graph()
    return _arrange_graph