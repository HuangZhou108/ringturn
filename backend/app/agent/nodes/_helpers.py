# _helpers.py
import json
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.llm_service import get_llm
from ..callbacks import ThinkingCallbackHandler

# 后续可用于统一节点执行逻辑，暂时未使用
async def run_sub_agent(
    task_id: str,
    step_name: str,
    system_prompt: str,
    user_prompt: str = "请开始执行。",
    tools: list = None,
) -> dict:
    """
    运行一个 ReAct 子 Agent，返回解析后的 JSON 结果。
    如果解析失败，返回 None。
    """
    llm = get_llm()
    callback = ThinkingCallbackHandler(task_id, step_name)
    agent = create_react_agent(llm, tools or [], checkpointer=None)
    response = await agent.ainvoke(
        {
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
        },
        config={"callbacks": [callback]}
    )
    try:
        return json.loads(response["messages"][-1].content)
    except Exception:
        return None