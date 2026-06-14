# backend/app/agent/tool_graphs/analysis_graph.py
import json
from pathlib import Path
from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.node_registry import register_node, register_condition, NODE_REGISTRY, CONDITION_REGISTRY
from app.agent.tool_graphs.nodes.analysis import metadata_node, tempo_node, tempo_var_node, loudness_node, spectral_node, sections_node, msaf_node, clap_classify_node, decide_separation_node, separate_demucs_node, fork_node, optional_decision_node, infer_mood_node, detect_effects_node, merge_node, conditions

_ANALYSIS_GRAPH_JSON = Path(__file__).parent / "analysis_graph.json"

async def build_analysis_graph():
    with open(_ANALYSIS_GRAPH_JSON, "r", encoding="utf-8") as f:
        config = json.load(f)
    workflow = StateGraph(AgentState)
    # 添加节点
    for node_def in config.get("nodes", []):
        node_id = node_def["id"]
        func = NODE_REGISTRY.get(node_id)
        if not func:
            raise ValueError(f"Node '{node_id}' not registered")
        workflow.add_node(node_id, func)
    # 添加普通边
    for edge in config.get("edges", []):
        workflow.add_edge(edge["from"], edge["to"])
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
    # 添加默认边
    for edge in config.get("default_edges", []):
        workflow.add_edge(edge["from"], edge["to"])
    workflow.set_entry_point(config["entry"])
    if config.get("exit"):
        workflow.add_edge(config["exit"], END)
    return workflow.compile()

_analysis_graph = None

async def get_analysis_graph():
    global _analysis_graph
    if _analysis_graph is None:
        _analysis_graph = await build_analysis_graph()
    return _analysis_graph