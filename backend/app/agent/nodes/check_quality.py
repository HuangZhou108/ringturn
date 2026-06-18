import json
from sqlalchemy.orm import Session
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from app.services.llm_service import get_llm
from app.agent.state import AgentState
from app.agent.atomic_tools.quality import evaluate_overall_quality_tool
from ..callbacks import ThinkingCallbackHandler
from app.agent.thinking_utils import record_thought
from app.agent.utils import clean_state, extract_json_from_response
from app.agent.tool_graphs.quality_graph import get_quality_graph

@clean_state
async def check_quality_node(state: AgentState) -> dict:
    """
    节点7: 质量检查

    评估生成音频的质量
    """
    plan = state.get("plan", [])
    if "check_quality" not in plan:   
        return {}
    
    audio_path = state.get("final_audio_path")
    if not audio_path:
        raise ValueError("无法检查质量：缺少 final_audio_path")

    task_id = state["task_id"]
    profile_id = state.get("profile_id")

    # 准备子状态
    sub_state = {
        "task_id": task_id,
        "final_audio_path": audio_path,
        "max_retries": state.get("max_retries", 0),
        "step_results": state.get("step_results", {}),
    }

    graph = await get_quality_graph()
    final_state = await graph.ainvoke(sub_state)

    # 提取结果（与原来保持相同的返回结构）
    return {
        "needs_revision": final_state.get("needs_revision", False),
        "reflection": final_state.get("reflection"),
        "step_results": final_state.get("step_results", {}),
    }