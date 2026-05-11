import json
from sqlalchemy.orm import Session
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from app.services.llm_service import get_llm
from app.agent.state import AgentState
from app.agent.atomic_tools.quality import evaluate_overall_quality_tool
from ..callbacks import ThinkingCallbackHandler

async def check_quality_node(state: AgentState, db: Session, tools) -> None:
    """
    节点7: 质量检查

    评估生成音频的质量
    """
    audio_path = state["final_audio_path"]
    task_id = state["task_id"]
    step_tools = [evaluate_overall_quality_tool]  # 也可以包含单个指标工具，但综合工具更高效
    system_prompt = f"""评估音频质量：{audio_path}
调用 evaluate_overall_quality_tool 获得质量报告。

**你必须严格遵守以下交互格式：**
在调用工具之前，先输出一句中文说明，格式为：“[思考] 我接下来将使用 <工具名>，因为 <原因>。”
然后调用工具。
完成工具调用后，再单独输出最终的 JSON 结果。
**绝对不要省略 `[思考]` 行！**

示例：
[思考] 我接下来将使用 evaluate_overall_quality_tool，因为需要综合评估音频的响度、频谱平衡、动态范围等指标。
（随后调用 evaluate_overall_quality_tool 工具）
最终 JSON 结果：
{{"overall_score": 4.2, "quality_issues": [], "passed": true, ...}}
"""
    llm = get_llm()
    callback = ThinkingCallbackHandler(task_id, "check_quality")
    sub_agent = create_react_agent(llm, step_tools)
    resp = await sub_agent.ainvoke(
        {"messages": [SystemMessage(content=system_prompt), HumanMessage(content="评估质量。")]},
        config={"callbacks": [callback]}
    )
    # 强制检查是否调用了工具
    messages = resp.get("messages", [])
    tool_called = any(isinstance(m, ToolMessage) for m in messages)
    if not tool_called:
        raise RuntimeError("质量检查失败：未调用评估工具，LLM 可能直接编造了结果")
    
    try:
        quality = json.loads(resp["messages"][-1].content)
    except:
        raise RuntimeError("质量检查结果解析失败")
    
    # 验证必要字段
    if "overall_score" not in quality:
        raise RuntimeError("质量检查结果缺少 overall_score")
    if not quality.get("passed", False):
        state["needs_revision"] = True
        state["reflection"] = {"message": "质量不达标", "adjustments": {}}
    state["step_results"]["quality_check"] = quality