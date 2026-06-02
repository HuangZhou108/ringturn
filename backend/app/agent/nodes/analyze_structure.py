# backend/app/agent/nodes/analyze_structure.py
from app.agent.state import AgentState
from app.agent.tool_graphs.analysis_graph import get_analysis_graph
from app.agent.utils import clean_state

@clean_state
async def analyze_structure_node(state: AgentState) -> dict:
    """
    节点2: 分析音乐结构

    使用预定义的工具链图执行分析，并将结果存入 analysis_result。
    """
    graph = await get_analysis_graph()
    result_state = await graph.ainvoke(state)
    analysis_result = result_state.get("analysis_result", {})
    return {"analysis_result": analysis_result}