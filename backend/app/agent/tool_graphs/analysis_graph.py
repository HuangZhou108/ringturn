# backend/app/agent/tool_graphs/analysis_graph.py
import json
from pathlib import Path
from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.node_registry import register_node, register_condition, NODE_REGISTRY, CONDITION_REGISTRY
from app.agent.tool_graphs.nodes.analysis import metadata_node, tempo_node, tempo_var_node, loudness_node, spectral_node, sections_node, msaf_node, clap_classify_node, decide_separation_node, separate_demucs_node, fork_node, optional_decision_node, infer_mood_node, detect_effects_node, merge_node, conditions
from app.db.session import SessionLocal
from app.models import ToolPreference

_ANALYSIS_GRAPH_JSON = Path(__file__).parent / "analysis_graph.json"
_analysis_graph_cache = {}  # cache_key -> graph

async def build_analysis_graph(config: dict = None):
    """根据配置字典构建图"""
    if config is None:
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


async def get_analysis_graph(profile_id: int = None):
    """获取指定 profile 的 analysis 子图，若 profile_id 为 None 或没有自定义配置，返回默认图"""
    cache_key = profile_id if profile_id is not None else "default"
    
    if cache_key in _analysis_graph_cache:
        return _analysis_graph_cache[cache_key]
    
    custom_config = None
    if profile_id is not None:
        db = SessionLocal()
        try:
            pref = db.query(ToolPreference).filter(ToolPreference.profile_id == profile_id).first()
            if pref and pref.analysis_graph_config:
                custom_config = json.loads(pref.analysis_graph_config)
        finally:
            db.close()
    
    graph = await build_analysis_graph(config=custom_config)
    _analysis_graph_cache[cache_key] = graph
    return graph