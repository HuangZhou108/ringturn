"""
节点注册表：统一管理所有可动态构建的节点函数
"""

from typing import Dict, Callable, Awaitable, Any
from app.agent.state import AgentState

# 类型别名
NodeFunc = Callable[[AgentState], Awaitable[dict]]

# 注册表
NODE_REGISTRY: Dict[str, NodeFunc] = {}

def register_node(node_id: str):
    """装饰器：注册节点函数"""
    def decorator(func: NodeFunc) -> NodeFunc:
        NODE_REGISTRY[node_id] = func
        return func
    return decorator

# 条件路由函数注册表（用于 conditional_edges）
CONDITION_REGISTRY: Dict[str, Callable[[AgentState], str]] = {}

def register_condition(cond_id: str):
    def decorator(func):
        CONDITION_REGISTRY[cond_id] = func
        return func
    return decorator