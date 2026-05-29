"""
反思节点

根据质量评估结果决定是否需要重试
"""

from app.agent.state import AgentState
from app.services.llm_service import llm_service
from app.agent.thinking_utils import record_thought
from app.agent.utils import clean_state

@clean_state
async def reflect_node(state: AgentState) -> dict:
    """
    反思节点：判断质量是否达标，是否需要重新改编

    修改 state 中的 needs_revision 和 retry_count
    """
    quality = state.get("step_results", {}).get("quality_check", {})
    user_request = state.get("user_request", "")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 0)

    # 调用 LLM 进行反思
    try:
        reflection = await llm_service.reflect_on_quality(quality, user_request)
        needs_revision = reflection.get("needs_revision", False)
        reason = reflection.get("reason", "")
        suggestions = reflection.get("suggestions", [])
    except Exception as e:
        # 降级：默认通过
        record_thought(state["task_id"], "reflect", f"LLM 反思失败: {e}，默认通过")
        needs_revision = False
        reason = ""
        suggestions = []

    # 如果用户设置了 max_retries=0，强制不重试
    if max_retries == 0:
        needs_revision = False

    new_retry_count = retry_count + 1 if needs_revision else 0
    reflection_data = {"reason": reason, "suggestions": suggestions}
    
    if needs_revision:
        record_thought(
            state["task_id"],
            "reflect",
            f"质量不达标，将进行第 {state['retry_count']} 次重试。原因: {reason}",
        )
    else:
        record_thought(state["task_id"], "reflect", "质量检查通过，无需重试")

    return {
        "needs_revision": needs_revision,
        "reflection": reflection_data,
        "retry_count": new_retry_count,
    }