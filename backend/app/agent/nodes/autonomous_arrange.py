"""
自主改编节点：真正的 function calling（ReAct）

让 LLM 自主决定调用哪些编曲工具、按什么顺序，而不是走固定工具链。
这是"确定性编排 + 自主决策"混合架构中的「自主决策层」。
失败/无结果时返回 {}，由 arrange_node 回退到确定性 arrange_graph。
"""
import re
from pathlib import Path

from langgraph.prebuilt import create_react_agent

from app.agent.state import AgentState
from app.agent.atomic_tools.arrangement import (
    change_instrument_tool,
    change_tempo_tool,
    transpose_pitch_tool,
    quantize_midi_tool,
    add_delay_echo_tool,
)
from app.agent.atomic_tools.knowledge.search_knowledge import search_knowledge_tool
from app.services.llm_service import get_llm
from app.agent.thinking_utils import record_thought
from app.agent.callbacks import ToolTraceCallbackHandler
from app.agent.utils import clean_state
from app.core.config import get_settings

settings = get_settings()


@clean_state
async def autonomous_arrange_node(state: AgentState) -> dict:
    """
    LLM 用 function calling 自主改编 MIDI。

    返回 {"arranged_midi_path": str} 或 {}（失败，交给确定性 arrange）。
    """
    midi_path = state.get("midi_path")
    task_id = state["task_id"]
    if not midi_path or not Path(midi_path).exists():
        return {}

    task_dir = Path(settings.RINGTONES_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    analysis = state.get("analysis_result") or {}
    bpm = (analysis.get("tempo_beats") or {}).get("bpm")
    mood = (analysis.get("mood_style") or {}).get("mood")
    key = (analysis.get("harmony") or {}).get("key")

    prompt = (
        f"你是音乐改编 Agent，用工具自主完成铃声改编。\n"
        f"输入 MIDI：{midi_path}\n"
        f"任务目录：{task_dir}\n"
        f"用户需求：{state.get('user_request', '')}\n"
        f"音频分析：BPM={bpm}，情绪={mood}，调性={key}\n\n"
        f"规则：\n"
        f"0. 在决定乐器/速度/移调前，先调用 search_knowledge 工具（用用户需求里的情绪词作为 query）检索编曲知识，参考知识库做决策。\n"
        f"1. 自主决定调用哪些工具、按什么顺序（换乐器/变速/移调/量化/加回声）。\n"
        f"2. 每个工具的返回路径作为下一步的输入 midi_path。\n"
        f"3. 工具要求 output_path 时，用 {task_dir} 下的新文件名（如 {task_dir}/s1.mid）。\n"
        f"4. 完成后，单独输出最终 MIDI 的绝对路径（只输出路径）。"
    )

    llm = get_llm()
    tools = [
        search_knowledge_tool,
        change_instrument_tool,
        change_tempo_tool,
        transpose_pitch_tool,
        quantize_midi_tool,
        add_delay_echo_tool,
    ]

    record_thought(task_id, "arrange", "自主改编：LLM 用 function calling 决定工具序列")
    try:
        agent = create_react_agent(llm, tools)
        trace_callback = ToolTraceCallbackHandler(task_id, "arrange")
        result = await agent.ainvoke(
            {"messages": [("user", prompt)]},
            config={"recursion_limit": 30, "callbacks": [trace_callback]},
        )
        text = str(result["messages"][-1].content) if result.get("messages") else ""
        record_thought(task_id, "arrange", f"自主改编完成，LLM 输出: {text[:200]}")

        # 解析最终 MIDI 路径（优先 LLM 明确给出的绝对路径）
        m = re.search(r"([A-Za-z]:[\\/][^\s'\"]+\.mid|[\w\-./\\]+\.mid)", text)
        if m and Path(m.group(1)).exists():
            return {"arranged_midi_path": m.group(1)}

        # 兜底：任务目录下最新生成的 mid（排除输入文件本身）
        input_name = Path(midi_path).name
        candidates = sorted(
            [p for p in task_dir.glob("*.mid") if p.name != input_name],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return {"arranged_midi_path": str(candidates[0])}
        return {}
    except Exception as e:
        record_thought(task_id, "arrange", f"自主改编失败(回退确定性 arrange): {e}")
        return {}
