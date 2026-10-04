import json
from pathlib import Path
from sqlalchemy.orm import Session
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.llm_service import get_llm
from app.agent.state import AgentState
from app.core.config import get_settings
from app.agent.atomic_tools.arrangement import (
    change_instrument_tool, change_tempo_tool, quantize_midi_tool
)
from app.agent.utils import clean_state
from app.services.llm_service import llm_service
from app.agent.thinking_utils import record_thought
import mido
from app.agent.tool_graphs.arrange_graph import get_arrange_graph
settings = get_settings()


async def _apply_gap_accompaniment(state: AgentState, arranged_path: str) -> str:
    """只在长旋律休止中添加低力度伴奏；失败时保留原编曲结果。"""
    from app.agent.atomic_tools.arrangement.gap_accompaniment import plan_gap_accompaniment
    from app.agent.atomic_tools.arrangement.harmonize_midi import harmonize_midi

    try:
        analysis = state.get("analysis_result") or {}
        if not isinstance(analysis, dict):
            raise TypeError("analysis_result 不是字典")
        harmony = analysis.get("harmony") or {}
        melody_data = state.get("melody_data") or {}
        if not isinstance(harmony, dict) or not isinstance(melody_data, dict):
            raise TypeError("旋律或和声状态格式无效")
        plan = plan_gap_accompaniment(
            melody_notes=melody_data.get("melody_notes") or [],
            chords=harmony.get("chords") or [],
            key_midi=harmony.get("key_midi"),
            mode=harmony.get("mode", "major"),
            target_duration=state.get("duration"),
        )
    except Exception as e:
        record_thought(state["task_id"], "arrange", f"长休止伴奏规划失败，安全跳过: {e}")
        return arranged_path

    if not plan["segments"]:
        record_thought(
            state["task_id"],
            "arrange",
            f"跳过长休止伴奏：{plan['reason']}（长休止 {plan['gap_count']} 段）",
        )
        return arranged_path

    try:
        detected_bpm = (analysis.get("tempo_beats") or {}).get("bpm") or 120
        harmonized_path = str(Path(arranged_path).with_name("arrange_gap_harmonized.mid"))
        await harmonize_midi(
            midi_path=arranged_path,
            chords=plan["segments"],
            output_path=harmonized_path,
            bpm=float(detected_bpm),
            bass_velocity=42,
            pad_velocity=28,
        )
        mido.MidiFile(harmonized_path)
        record_thought(
            state["task_id"],
            "arrange",
            f"已为 {len(plan['segments'])} 个长休止添加低力度伴奏（策略: {plan['reason']}）",
        )
        return harmonized_path
    except Exception as e:
        record_thought(state["task_id"], "arrange", f"长休止伴奏失败，保留原编曲结果: {e}")
        return arranged_path

@clean_state
async def arrange_node(state: AgentState) -> dict:
    """
    节点5: 乐器改编

    根据用户需求更换乐器、调整风格
    """
    plan = state.get("plan", [])
    if "arrange" not in plan:   
        return {}
    midi_path = state["midi_path"]
    if not midi_path:
        melody_data = state.get("melody_data")
        if isinstance(melody_data, dict):
            midi_path = melody_data.get("midi_path")
    if not midi_path or not Path(midi_path).exists():
        raise ValueError(f"[Arrange] MIDI 文件不存在: {midi_path}")

    # 纠正性重试：若 reflect 指出质量问题，对旋律重新做调性校正并重建 MIDI
    correction = state.get("correction")
    if correction and state.get("melody_data"):
        try:
            from app.agent.atomic_tools.melody.snap_to_key import snap_to_key
            from app.agent.atomic_tools.midi.create_from_notes import create_midi_from_notes
            melody_notes = state["melody_data"].get("melody_notes", [])
            harmony = (state.get("analysis_result") or {}).get("harmony") or {}
            detected_bpm = ((state.get("analysis_result") or {}).get("tempo_beats") or {}).get("bpm") or 120
            corrected = await snap_to_key(
                melody_notes,
                key_midi=harmony.get("key_midi"),
                mode=harmony.get("mode", "major"),
                snap_threshold=1.0,   # 重试时启用调性 snap（默认是关闭的）
            )
            task_dir = Path(settings.RINGTONES_DIR) / state["task_id"]
            task_dir.mkdir(parents=True, exist_ok=True)
            corrected_midi = str(task_dir / "corrected_melody.mid")
            await create_midi_from_notes(
                corrected,
                bpm=float(detected_bpm),
                output_path=corrected_midi,
                legato_overlap=0.03,
                legato_max_gap=0.08,
            )
            midi_path = corrected_midi
            record_thought(state["task_id"], "arrange", f"纠正性重试：已对旋律重新调性校正并重建 MIDI（{correction}）")
        except Exception as e:
            record_thought(state["task_id"], "arrange", f"纠正性重试失败(忽略): {e}")

    # ---- 自主改编（function calling）：LLM 自主决定工具序列，失败则回退确定性 arrange ----
    try:
        from app.agent.nodes.autonomous_arrange import autonomous_arrange_node
        auto_result = await autonomous_arrange_node(state)
        auto_path = auto_result.get("arranged_midi_path")
        if auto_path and Path(auto_path).exists():
            try:
                mido.MidiFile(auto_path)
                record_thought(state["task_id"], "arrange", "采用自主改编（function calling）结果")
                auto_path = await _apply_gap_accompaniment(state, auto_path)
                return {"arranged_midi_path": auto_path}
            except Exception as e:
                record_thought(state["task_id"], "arrange", f"自主改编结果无效，回退确定性: {e}")
    except Exception as e:
        record_thought(state["task_id"], "arrange", f"自主改编异常，回退确定性: {e}")

    profile_id = state.get("profile_id")
    # 准备工具链图需要的状态（原样传递）
    sub_state = {
        "task_id": state["task_id"],
        "midi_path": midi_path,
        "instrument": state.get("instrument"),
        "tempo": state.get("tempo"),
    }

    # ---- 开始改编说明 ----
    instrument = state.get("instrument", "未指定")
    tempo = state.get("tempo", "未指定")
    user_request = state.get("user_request", "")
    start_msg = f"开始根据您的需求进行改编："
    record_thought(state["task_id"], "arrange", start_msg)

    graph = await get_arrange_graph(profile_id=profile_id)
    try:
        final_state = await graph.ainvoke(sub_state)
    except Exception as e:
        record_thought(state["task_id"], "arrange", f"arrange_graph 执行失败: {e}")
        raise RuntimeError(f"乐器改编子图失败: {e}") from e

    arranged_path = final_state.get("arranged_midi_path")
    if not arranged_path or not Path(arranged_path).exists():
        raise RuntimeError("改编失败：未生成有效的 MIDI 文件")

    # 验证 MIDI 有效性
    try:
        mido.MidiFile(arranged_path)
    except Exception as e:
        raise RuntimeError(f"改编后的 MIDI 无效: {e}")

    # ---- LLM 决策的移调（若 analysis 阶段给出了 transpose_semitones）----
    transpose = (state.get("arrangement_params") or {}).get("transpose_semitones", 0)
    if transpose:
        try:
            from app.agent.atomic_tools.arrangement.transpose_pitch import transpose_pitch
            transposed_path = str(Path(arranged_path).with_name("arrange_transposed.mid"))
            await transpose_pitch(
                midi_path=arranged_path,
                output_path=transposed_path,
                semitones=int(transpose),
            )
            arranged_path = transposed_path
            record_thought(state["task_id"], "arrange", f"已按 LLM 决策移调 {int(transpose)} 半音")
        except Exception as e:
            record_thought(state["task_id"], "arrange", f"移调失败(忽略): {e}")

    # ---- 长休止伴奏：仅填补人声句间的显著空档，不覆盖持续旋律 ----
    arranged_path = await _apply_gap_accompaniment(state, arranged_path)

    # ---- 改编结束说明 ----
    # 收集实际发生的改编
    changes = []
    if state.get("instrument"):
        changes.append(f"乐器设置为 {state['instrument']}")
    if state.get("tempo"):
        changes.append(f"速度调整为 {state['tempo']} BPM")
    change_text = "；".join(changes) if changes else "未进行明显修改"

    plan_desc = state.get("plan_description", "")
    user_req = state.get("user_request", "")[:100]

    prompt = f"""用户请求：{user_req}...
规划描述：{plan_desc}...
已完成的改编：{change_text}。
请用自然语言总结我们进行了哪些改编，以及这些改编与用户任务（铃声改编）的关系。只输出总结，不超过80字。"""
    try:
        summary = await llm_service.chat([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=120)
    except Exception:
        summary = f"已完成改编：{change_text}，这些调整将用于生成符合用户需求的铃声音频。"
    record_thought(state["task_id"], "arrange", summary)

    return {"arranged_midi_path": arranged_path}
