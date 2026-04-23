"""
LangGraph工作流定义

定义Agent的完整状态流转图
"""

from typing import TypedDict
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agent.state import AgentState, TaskStep
from app.core.config import get_settings

settings = get_settings()

# 定义节点名称
NODE_NAMES = {
    "planner": "planner",
    "fetch_source": "fetch_source",
    "analyze": "analyze",
    "extract_melody": "extract_melody",
    "generate_midi": "generate_midi",
    "arrange": "arrange",
    "render": "render",
    "check_quality": "check_quality",
    "reflect": "reflect",
    "human_input": "human_input",
}

async def planner_node(state: AgentState) -> AgentState:
    """
    规划节点

    将用户需求分解为执行步骤（调用LLM）
    """
    from app.services.llm_service import llm_service

    user_request = state.get("user_request", "")
    plan = await llm_service.generate_plan(user_request)

    state["plan"] = plan
    state["current_step"] = TaskStep.FETCH_SOURCE.value
    state["current_step_index"] = 0

    return state

async def fetch_source_node(state: AgentState) -> AgentState:
    """获取音频源节点"""
    from app.agent.tools import tool_gateway
    from app.agent.nodes import fetch_source_node as handler

    await handler(state, None, tool_gateway)

    state["current_step_index"] = 1
    state["current_step"] = TaskStep.ANALYZE_STRUCTURE.value
    return state

async def analyze_node(state: AgentState) -> AgentState:
    """分析节点"""
    from app.agent.tools import tool_gateway
    from app.agent.nodes import analyze_structure_node as handler

    await handler(state, None, tool_gateway)

    state["current_step_index"] = 2
    state["current_step"] = TaskStep.EXTRACT_MELODY.value
    return state

async def extract_melody_node(state: AgentState) -> AgentState:
    """提取旋律节点"""
    from app.agent.tools import tool_gateway
    from app.agent.nodes import extract_melody_node as handler

    await handler(state, None, tool_gateway)

    state["current_step_index"] = 3
    state["current_step"] = TaskStep.GENERATE_MIDI.value
    return state

async def generate_midi_node(state: AgentState) -> AgentState:
    """生成MIDI节点"""
    from app.agent.tools import tool_gateway
    from app.agent.nodes import generate_midi_node as handler

    await handler(state, None, tool_gateway)

    state["current_step_index"] = 4
    state["current_step"] = TaskStep.ARRANGE.value
    return state

async def arrange_node(state: AgentState) -> AgentState:
    """改编节点"""
    from app.agent.tools import tool_gateway
    from app.agent.nodes import arrange_node as handler

    await handler(state, None, tool_gateway)

    state["current_step_index"] = 5
    state["current_step"] = TaskStep.RENDER.value
    return state

async def render_node(state: AgentState) -> AgentState:
    """渲染节点"""
    from app.agent.tools import tool_gateway
    from app.agent.nodes import render_node as handler

    await handler(state, None, tool_gateway)

    state["current_step_index"] = 6
    state["current_step"] = TaskStep.CHECK_QUALITY.value
    return state

async def check_quality_node(state: AgentState) -> AgentState:
    """质量检查节点"""
    from app.agent.tools import tool_gateway
    from app.agent.nodes import check_quality_node as handler

    await handler(state, None, tool_gateway)

    state["current_step_index"] = 7
    return state

async def reflect_node(state: AgentState) -> AgentState:
    """反思节点"""
    from app.services.llm_service import llm_service

    quality_result = state.get("step_results", {}).get("quality_check", {})
    user_request = state.get("user_request", "")

    reflection = await llm_service.reflect_on_quality(quality_result, user_request)

    state["reflection"] = reflection
    state["needs_revision"] = reflection.get("needs_revision", False)

    return state

async def human_input_node(state: AgentState) -> AgentState:
    """
    等待用户输入节点
    """
    state["current_step"] = "waiting_feedback"
    return state

def should_revise(state: AgentState) -> bool:
    """判断是否需要修订"""
    return state.get("needs_revision", False)

# 全局图实例
_graph_instance = None

def get_agent_graph():
    """获取Agent图实例（单例）"""
    global _graph_instance
    if _graph_instance is None:
        workflow = StateGraph(AgentState)

        # 注册节点
        workflow.add_node(NODE_NAMES["planner"], planner_node)
        workflow.add_node(NODE_NAMES["fetch_source"], fetch_source_node)
        workflow.add_node(NODE_NAMES["analyze"], analyze_node)
        workflow.add_node(NODE_NAMES["extract_melody"], extract_melody_node)
        workflow.add_node(NODE_NAMES["generate_midi"], generate_midi_node)
        workflow.add_node(NODE_NAMES["arrange"], arrange_node)
        workflow.add_node(NODE_NAMES["render"], render_node)
        workflow.add_node(NODE_NAMES["check_quality"], check_quality_node)
        workflow.add_node(NODE_NAMES["reflect"], reflect_node)
        workflow.add_node(NODE_NAMES["human_input"], human_input_node)

        # 定义边
        workflow.add_edge(NODE_NAMES["planner"], NODE_NAMES["fetch_source"])
        workflow.add_edge(NODE_NAMES["fetch_source"], NODE_NAMES["analyze"])
        workflow.add_edge(NODE_NAMES["analyze"], NODE_NAMES["extract_melody"])
        workflow.add_edge(NODE_NAMES["extract_melody"], NODE_NAMES["generate_midi"])
        workflow.add_edge(NODE_NAMES["generate_midi"], NODE_NAMES["arrange"])
        workflow.add_edge(NODE_NAMES["arrange"], NODE_NAMES["render"])
        workflow.add_edge(NODE_NAMES["render"], NODE_NAMES["check_quality"])
        workflow.add_edge(NODE_NAMES["check_quality"], NODE_NAMES["reflect"])

        # 条件分支
        workflow.add_conditional_edges(
            NODE_NAMES["reflect"],
            should_revise,
            {
                True: NODE_NAMES["human_input"],
                False: END,
            },
        )

        # 用户输入后回到arrange
        workflow.add_edge(NODE_NAMES["human_input"], NODE_NAMES["arrange"])

        # 设置入口
        workflow.set_entry_point(NODE_NAMES["planner"])

        # 配置检查点存储
        checkpointer = SqliteSaver.from_conn_string(
            settings.CHECKPOINT_DB_URL
        )

        _graph_instance = workflow.compile(
            checkpointer=checkpointer,
        )

    return _graph_instance
