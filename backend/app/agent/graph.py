"""
LangGraph工作流定义

定义Agent的完整状态流转图，支持检查点和条件重试
"""

import asyncio
import aiosqlite
from pathlib import Path
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.agent.state import AgentState
from app.agent.nodes import (
    fetch_source_node,
    analyze_structure_node,
    extract_melody_node,
    generate_midi_node,
    arrange_node,
    render_node,
    check_quality_node,
)
from app.agent.nodes.reflect import reflect_node
from app.core.config import get_settings

settings = get_settings()

# 节点名称常量
NODE_FETCH = "fetch_source"
NODE_ANALYZE = "analyze_structure"
NODE_EXTRACT = "extract_melody"
NODE_GEN_MIDI = "generate_midi"
NODE_ARRANGE = "arrange"
NODE_RENDER = "render"
NODE_CHECK = "check_quality"
NODE_REFLECT = "reflect"

_agent_graph = None
_graph_lock = asyncio.Lock()


async def build_agent_graph():
    """异步构建并编译LangGraph状态图"""
    workflow = StateGraph(AgentState)

    # 注册节点（所有节点已修改为只接收 state 参数）
    workflow.add_node(NODE_FETCH, fetch_source_node)
    workflow.add_node(NODE_ANALYZE, analyze_structure_node)
    workflow.add_node(NODE_EXTRACT, extract_melody_node)
    workflow.add_node(NODE_GEN_MIDI, generate_midi_node)
    workflow.add_node(NODE_ARRANGE, arrange_node)
    workflow.add_node(NODE_RENDER, render_node)
    workflow.add_node(NODE_CHECK, check_quality_node)
    workflow.add_node(NODE_REFLECT, reflect_node)

    # 固定边（顺序执行）
    workflow.add_edge(NODE_FETCH, NODE_ANALYZE)
    workflow.add_edge(NODE_ANALYZE, NODE_EXTRACT)
    workflow.add_edge(NODE_EXTRACT, NODE_GEN_MIDI)
    workflow.add_edge(NODE_GEN_MIDI, NODE_ARRANGE)
    workflow.add_edge(NODE_ARRANGE, NODE_RENDER)
    workflow.add_edge(NODE_RENDER, NODE_CHECK)
    workflow.add_edge(NODE_CHECK, NODE_REFLECT)

    # 条件边：根据反思结果决定是否重试
    def should_retry(state: AgentState) -> str:
        if not state.get("needs_revision", False):
            return END
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 0)
        if retry_count >= max_retries:
            return END
        return NODE_ARRANGE

    workflow.add_conditional_edges(
        NODE_REFLECT,
        should_retry,
        {
            NODE_ARRANGE: NODE_ARRANGE,
            END: END,
        },
    )

    workflow.set_entry_point(NODE_FETCH)

    # 异步检查点
    db_path = settings.CHECKPOINT_DB_URL.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # conn = await aiosqlite.connect(db_path)
    # checkpointer = AsyncSqliteSaver(conn)

    graph = workflow.compile(checkpointer=None)
    return graph


async def get_agent_graph():
    """异步获取全局图实例（线程安全）"""
    global _agent_graph
    if _agent_graph is None:
        async with _graph_lock:
            if _agent_graph is None:
                _agent_graph = await build_agent_graph()
    return _agent_graph