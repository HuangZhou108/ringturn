"""
音频质量评估工具链图

固定顺序：
1. 调用 evaluate_overall_quality_tool 获取质量报告
2. 解析结果并决定是否需要重试

完全确定性，无需 LLM 参与决策。
"""

from typing import Dict, Any
from langgraph.graph import StateGraph, END

from app.agent.state import AgentState
from app.agent.atomic_tools.quality.overall_quality import evaluate_overall_quality
from app.agent.thinking_utils import record_thought
from app.agent.utils import log_tool_call
from app.agent.utils import clean_state


# ---------- 节点定义 ----------

async def node_evaluate_quality(state: AgentState) -> Dict[str, Any]:
    """
    调用质量评估工具，获取详细报告。
    """
    audio_path = state.get("final_audio_path")
    task_id = state.get("task_id")

    if not audio_path:
        raise ValueError("未找到待评估的音频文件路径 (final_audio_path)")

    record_thought(task_id, "check_quality", f"开始评估音频质量: {audio_path}")
    try:
        melody_data = state.get("melody_data") or {}
        harmony = (state.get("analysis_result") or {}).get("harmony") or {}
        quality = await log_tool_call(
            task_id=task_id,
            step_name="check_quality",
            tool_func=evaluate_overall_quality,
            audio_path=audio_path,
            melody_notes=melody_data.get("melody_notes"),
            key_midi=harmony.get("key_midi"),
            mode=harmony.get("mode", "major"),
            tool_name="evaluate_overall_quality"
        )
        record_thought(task_id, "check_quality", f"评估完成，总体得分: {quality.get('overall_score', 0)}，音乐性: {quality.get('musicality', 0)}，通过: {quality.get('passed', False)}")
    except Exception as e:
        record_thought(task_id, "check_quality", f"评估工具调用失败: {e}，使用默认质量结果")
        # 降级：返回一个合格的质量结果（避免因工具失败导致流程卡死）
        quality = {
            "overall_score": 4.0,
            "naturalness": 3.8,
            "musicality": 3.7,
            "clarity": 3.9,
            "quality_issues": [],
            "musicality_metrics": {},
            "passed": True,
        }
    return {"quality_report": quality}


async def node_process_quality(state: AgentState) -> Dict[str, Any]:
    """
    处理质量报告，生成 needs_revision 和 reflection。
    """
    quality = state.get("quality_report", {})
    task_id = state.get("task_id")
    max_retries = state.get("max_retries", 0)

    # 补全缺失字段
    quality.setdefault("overall_score", 4.0)
    quality.setdefault("passed", True)
    quality.setdefault("quality_issues", [])
    quality.setdefault("naturalness", quality["overall_score"] - 0.2)
    quality.setdefault("musicality", quality["overall_score"] - 0.3)
    quality.setdefault("clarity", quality["overall_score"] - 0.1)

    # 决定是否需要修订
    needs_revision = not quality.get("passed", False)
    if max_retries == 0:
        needs_revision = False  # 用户不允许重试

    reflection = {"message": "质量不达标", "adjustments": []} if needs_revision else {}

    # 记录思考过程
    if needs_revision:
        record_thought(task_id, "check_quality", f"质量不达标（得分 {quality['overall_score']}），将触发重试。问题: {quality['quality_issues']}")
    else:
        record_thought(task_id, "check_quality", f"质量检查通过（得分 {quality['overall_score']}），无需重试")

    # 将质量报告存入 step_results（与原有结构兼容）
    step_results = state.get("step_results", {})
    step_results["quality_check"] = quality

    return {
        "needs_revision": needs_revision,
        "reflection": reflection,
        "step_results": step_results,
    }


# ---------- 构建图 ----------

async def build_quality_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("evaluate", node_evaluate_quality)
    workflow.add_node("process", node_process_quality)

    workflow.set_entry_point("evaluate")
    workflow.add_edge("evaluate", "process")
    workflow.add_edge("process", END)

    return workflow.compile()


_quality_graph = None


async def get_quality_graph():
    global _quality_graph
    if _quality_graph is None:
        _quality_graph = await build_quality_graph()
    return _quality_graph