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
    
    updates = {
        "analysis_result": result_state.get("analysis_result", {})
    }

    # 传递分离相关的顶层字段（若存在）
    for key in ["demucs_separated", "vocals_path", "accompaniment_path", "demucs_stems", "audio_path"]:
        if key in result_state:
            updates[key] = result_state[key]

    return updates