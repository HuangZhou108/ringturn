# backend/app/agent/tool_graphs/base.py
from typing import Callable, Awaitable, Any, Dict
from langgraph.graph import StateGraph
from app.agent.state import AgentState
from app.agent.thinking_utils import record_thought
import traceback

def wrap_tool(tool_func: Callable, output_key: str):
    """
    将原子工具函数包装为 LangGraph 节点。
    节点从 state 中读取 audio_path，调用工具，将结果存入 state['analysis_result'][output_key]。
    """
    async def node(state: AgentState) -> Dict[str, Any]:
        audio_path = state.get("audio_path")
        task_id = state.get("task_id")
        if not audio_path:
            raise ValueError("state 中缺少 audio_path")
        if "analysis_result" not in state or state["analysis_result"] is None:
            state["analysis_result"] = {}

        # 记录开始
        if task_id:
            record_thought(task_id, f"analysis", f"开始分析: {output_key}")
        
        try:
            result = await tool_func(audio_path=audio_path)
            # 记录成功结果（可选，避免日志过多可只记录简短信息）
            if task_id and result is not None:
                # 对于较大的结果，只记录摘要
                summary = str(result)[:200] if isinstance(result, (dict, list)) else str(result)[:200]
                record_thought(task_id, f"analysis", f"完成: {summary}")
        except Exception as e:
            if task_id:
                record_thought(task_id, f"analysis", f"失败: {str(e)}")
            print(f"Tool '{output_key}' failed: {e}")
            result = None

        # 初始化 analysis_result
        state["analysis_result"][output_key] = result
        return {"analysis_result": state["analysis_result"]}
    return node

def wrap_tool_with_params(tool_func: Callable, output_key: str, param_extractors: Dict[str, Callable]):
    """
    对于需要额外参数的节点，param_extractors 从 state 中提取参数。
    """
    async def node(state: AgentState) -> Dict[str, Any]:
        audio_path = state.get("audio_path")
        task_id = state.get("task_id")
        if not audio_path:
            raise ValueError("state 中缺少 audio_path")
        # 确保 analysis_result 存在且为字典
        if "analysis_result" not in state or state["analysis_result"] is None:
            state["analysis_result"] = {}
        
        if task_id:
            record_thought(task_id, f"analysis", f"开始分析: {output_key}")

        kwargs = {"audio_path": audio_path}
        for param_name, extractor in param_extractors.items():
            kwargs[param_name] = extractor(state)

        try:
            result = await tool_func(**kwargs)
            if task_id and result is not None:
                summary = str(result)[:200]
                record_thought(task_id, f"analysis", f"完成: {summary}")
        except Exception as e:
            if task_id:
                record_thought(task_id, f"analysis", f"失败: {str(e)}")
            print(f"Tool '{output_key}' failed: {e}")
            result = None
        state["analysis_result"][output_key] = result
        return {"analysis_result": state["analysis_result"]}
    return node