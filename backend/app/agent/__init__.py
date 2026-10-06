"""Agent 模块的轻量公共入口。

对象按需导入，避免仅使用 trace/resilience 等基础模块时加载完整音频栈。
"""

from importlib import import_module

__all__ = [
    "AgentState",
    "TaskStep",
    "get_step_index",
    "get_step_message",
    "tool_gateway",
    "NODE_HANDLERS",
    "AgentExecutor",
    "get_agent_graph",
]

_EXPORT_MODULES = {
    "AgentState": "app.agent.state",
    "TaskStep": "app.agent.state",
    "get_step_index": "app.agent.state",
    "get_step_message": "app.agent.state",
    "tool_gateway": "app.agent.tools",
    "NODE_HANDLERS": "app.agent.nodes",
    "AgentExecutor": "app.agent.agent_executor",
    "get_agent_graph": "app.agent.graph",
}


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
