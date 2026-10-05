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
from app.agent.observability import (
    finish_trace_event,
    new_trace_event,
    record_trace_event,
    traced_node,
)
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
ALL_NODES = [NODE_FETCH, NODE_ANALYZE, NODE_EXTRACT, NODE_GEN_MIDI, 
             NODE_ARRANGE, NODE_RENDER, NODE_CHECK, NODE_REFLECT]

_agent_graph = None
_graph_lock = asyncio.Lock()

# 对于反馈任务，需要动态选择从哪个节点开始
def entry_router(state: AgentState) -> str:
    """根据 state 中的 resume_from_node 决定从哪个节点开始"""
    target = state.get("resume_from_node", NODE_FETCH)
    # 确保目标节点存在于图中
    return target if target in ALL_NODES else NODE_FETCH


async def entry_router_node(state: AgentState) -> dict:
    """Record the selected resume route without changing routing semantics."""
    requested = state.get("resume_from_node", NODE_FETCH)
    target = entry_router(state)
    event = new_trace_event(kind="routing", name="entry_router")
    event = finish_trace_event(
        event,
        status="success",
        metadata={"requested": requested, "selected": target},
    )
    record_trace_event(str(state.get("task_id") or ""), event)
    return {"execution_trace": [event]}

async def build_agent_graph():
    """异步构建并编译LangGraph状态图"""
    workflow = StateGraph(AgentState)

    # 注册节点（所有节点已修改为只接收 state 参数）
    node_specs = [
        (NODE_FETCH, fetch_source_node, 0, 10),
        (NODE_ANALYZE, analyze_structure_node, 10, 30),
        (NODE_EXTRACT, extract_melody_node, 30, 50),
        (NODE_GEN_MIDI, generate_midi_node, 50, 60),
        (NODE_ARRANGE, arrange_node, 60, 75),
        (NODE_RENDER, render_node, 75, 90),
        (NODE_CHECK, check_quality_node, 90, 97),
        (NODE_REFLECT, reflect_node, 97, 100),
    ]
    for node_name, node_func, progress_start, progress_end in node_specs:
        workflow.add_node(
            node_name,
            traced_node(
                node_name,
                node_func,
                progress_start=progress_start,
                progress_end=progress_end,
            ),
        )

    # 固定边（顺序执行）
    workflow.add_edge(NODE_FETCH, NODE_ANALYZE)
    workflow.add_edge(NODE_ANALYZE, NODE_EXTRACT)
    workflow.add_edge(NODE_EXTRACT, NODE_GEN_MIDI)
    workflow.add_edge(NODE_GEN_MIDI, NODE_ARRANGE)
    workflow.add_edge(NODE_ARRANGE, NODE_RENDER)
    workflow.add_edge(NODE_RENDER, NODE_CHECK)
    workflow.add_edge(NODE_CHECK, NODE_REFLECT)

    # 添加路由入口
    workflow.set_entry_point("entry_router")
    workflow.add_node("entry_router", entry_router_node)
    workflow.add_conditional_edges("entry_router", entry_router, {node: node for node in ALL_NODES})

    # 条件边：根据反思结果决定是否重试
    def should_retry(state: AgentState) -> str:
        if not state.get("needs_revision", False):
            selected = END
            reason = "quality_passed"
        else:
            retry_count = state.get("retry_count", 0)
            max_retries = state.get("max_retries", 0)
            if retry_count > max_retries:
                selected = END
                reason = "retry_limit_reached"
            else:
                selected = NODE_ARRANGE
                reason = "quality_revision"
        event = new_trace_event(kind="routing", name="quality_retry_router")
        event = finish_trace_event(
            event,
            status="success",
            metadata={
                "selected": "end" if selected == END else selected,
                "reason": reason,
                "retry_count": state.get("retry_count", 0),
                "max_retries": state.get("max_retries", 0),
            },
        )
        record_trace_event(str(state.get("task_id") or ""), event)
        return selected

    workflow.add_conditional_edges(
        NODE_REFLECT,
        should_retry,
        {
            NODE_ARRANGE: NODE_ARRANGE,
            END: END,
        },
    )

    # workflow.set_entry_point(NODE_FETCH)

    # 异步检查点
    db_path = settings.CHECKPOINT_DB_URL.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    checkpointer = AsyncSqliteSaver(conn)

    graph = workflow.compile(checkpointer=checkpointer)
    return graph


async def get_agent_graph():
    """异步获取全局图实例（线程安全）"""
    global _agent_graph
    if _agent_graph is None:
        async with _graph_lock:
            if _agent_graph is None:
                _agent_graph = await build_agent_graph()
    return _agent_graph
