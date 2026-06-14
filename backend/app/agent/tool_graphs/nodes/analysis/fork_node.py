from app.agent.node_registry import register_node
from app.agent.state import AgentState

@register_node("fork")
async def node_fork(state: AgentState) -> dict:
    return {}