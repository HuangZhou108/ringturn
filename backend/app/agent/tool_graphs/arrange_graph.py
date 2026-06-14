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
from app.agent.node_registry import register_node, register_condition, NODE_REGISTRY, CONDITION_REGISTRY
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import ToolPreference

settings = get_settings()

_ARRANGE_GRAPH_JSON = Path(__file__).parent / "arrange_graph.json"
_arrange_graph_cache = {}  # cache_key -> graph


# ---------- 节点定义 ----------

@register_node("change_instrument")
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


@register_node("change_tempo")
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


@register_node("finalize")
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

@register_condition("arrange_should_change_tempo")
def arrange_should_change_tempo(state: AgentState) -> str:
    return "change_tempo" if state.get("tempo") else "finalize"

# ---------- 构建图 ----------

async def build_arrange_graph(config: dict = None):
    """从 JSON 配置文件动态构建乐器改编子图"""
    import json
    if config is None:
        with open(_ARRANGE_GRAPH_JSON, "r", encoding="utf-8") as f:
            config = json.load(f)

    workflow = StateGraph(AgentState)

    # 添加节点
    for node_def in config.get("nodes", []):
        node_id = node_def["id"]
        func = NODE_REGISTRY.get(node_id)
        if not func:
            raise ValueError(f"Node '{node_id}' not registered in NODE_REGISTRY")
        workflow.add_node(node_id, func)

    # 辅助函数：将字符串目标转换为 END 常量
    def resolve_target(target: str):
        return END if target == "END" else target

    # 添加普通边
    for edge in config.get("edges", []):
        to_node = resolve_target(edge["to"])
        workflow.add_edge(edge["from"], to_node)

    # 添加条件边
    for cond_edge in config.get("conditional_edges", []):
        cond_func = CONDITION_REGISTRY.get(cond_edge["condition"])
        if not cond_func:
            raise ValueError(f"Condition '{cond_edge['condition']}' not registered")
        workflow.add_conditional_edges(
            cond_edge["from"],
            cond_func,
            cond_edge["mapping"]
        )

    # 添加默认边（无条件的）
    for edge in config.get("default_edges", []):
        to_node = resolve_target(edge["to"])
        workflow.add_edge(edge["from"], to_node)
        
    workflow.set_entry_point(config["entry"])

    # 如果 JSON 中指定了 exit 节点（且该节点确实存在），则添加连接到 END 的边
    exit_node = config.get("exit")
    if exit_node:
        # 检查 exit_node 是否是一个真实的节点 ID
        if any(node["id"] == exit_node for node in config.get("nodes", [])):
            workflow.add_edge(exit_node, END)
        # 否则忽略（例如 exit 描述的是条件分支后的状态，不是实际节点）

    return workflow.compile()


_arrange_graph = None


async def get_arrange_graph(profile_id: int = None):
    """
    获取指定 profile 的 arrange 子图。
    若 profile_id 为 None 或没有自定义配置，返回默认图。
    """
    cache_key = profile_id if profile_id is not None else "default"

    if cache_key in _arrange_graph_cache:
        return _arrange_graph_cache[cache_key]

    custom_config = None
    if profile_id is not None:
        db = SessionLocal()
        try:
            pref = db.query(ToolPreference).filter(ToolPreference.profile_id == profile_id).first()
            if pref and pref.arrange_graph_config:
                custom_config = json.loads(pref.arrange_graph_config)
        finally:
            db.close()

    graph = await build_arrange_graph(config=custom_config)
    _arrange_graph_cache[cache_key] = graph
    return graph