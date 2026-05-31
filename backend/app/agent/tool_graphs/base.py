from typing import Any, Dict, Callable, Awaitable, List
from langgraph.graph import StateGraph, END
from app.agent.state import AgentState

class ToolGraphBuilder:
    """工具链图构建器基类，定义子类需要实现的接口"""
    
    @classmethod
    def build(cls) -> StateGraph:
        """返回 StateGraph 实例（尚未编译）"""
        raise NotImplementedError
    
    @classmethod
    async def execute(cls, state: AgentState) -> Dict[str, Any]:
        """编译并执行图，返回状态增量"""
        graph = cls.build()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(state)
        # 提取增量（相比输入 state 的变化）
        delta = {k: v for k, v in final_state.items() if k not in state or state[k] != v}
        return delta