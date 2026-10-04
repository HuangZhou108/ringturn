# nodes/extract_melody.py
import asyncio
from pathlib import Path
from app.agent.state import AgentState
from app.agent.tool_graphs.extract_graph import get_extract_graph
from app.agent.utils import clean_state
from app.agent.thinking_utils import record_thought

@clean_state
async def extract_melody_node(state: AgentState) -> dict:
    """
    节点3: 提取主旋律

    提取音频中的主旋律数据
    """
    plan = state.get("plan", [])
    if "extract_melody" not in plan:   
        return {}
    
    audio_path = state["audio_path"]
    task_id = state["task_id"]
    profile_id = state.get("profile_id") 
    
    record_thought(task_id, "extract_melody", f"开始提取旋律：")

    # 如果 analysis 未执行（analysis_result 为 None），则主动进行 Demucs 分离
    if state.get("analysis_result") is None:
        record_thought(task_id, "extract_melody", "发现analysis 未执行demucs，主动进行 Demucs 音源分离")
        try:
            from app.agent.atomic_tools.analysis.demucs_separate import separate_sources_demucs
            result = await asyncio.to_thread(
                separate_sources_demucs,
                audio_path=audio_path,
                stems="vocals",
                model="htdemucs"
            )
            state["demucs_separated"] = True
            state["vocals_path"] = result.get("vocals_path")
            state["accompaniment_path"] = result.get("accompaniment_path")
            record_thought(task_id, "extract_melody", f"Demucs 分离成功，人声路径: {state['vocals_path']}")
        except Exception as e:
            record_thought(task_id, "extract_melody", f"Demucs 分离失败: {e}，将使用原始音频")
            # 失败时不设置 demucs_separated，保持 False

    # 构建临时 state 副本，避免污染原状态
    sub_state = {
        **state,
        "task_id": task_id,
        "audio_path": audio_path,
    }

    graph = await get_extract_graph(profile_id=profile_id)
    final_state = await graph.ainvoke(sub_state)

    melody_data = final_state.get("melody_data")
    melody_source_path = (
        final_state.get("melody_source_path")
        or final_state.get("source_for_melody")
        or audio_path
    )
    harmony_source_path = final_state.get("harmony_source_path") or audio_path
    if not melody_data:
        # 降级保险：直接调用 Basic Pitch
        from app.agent.atomic_tools.melody.extract_with_basic_pitch import extract_melody_basic_pitch
        melody_data = await extract_melody_basic_pitch(melody_source_path)
        record_thought(task_id, "extract_melody", f"降级：使用旋律源 {melody_source_path} 直接调用 Basic Pitch 成功")

    # 确保 melody_data 包含 midi_path（即使未生成也放一个占位）
    if not melody_data.get("midi_path"):
        melody_data["midi_path"] = audio_path.replace(".mp3", "_melody.mid").replace(".wav", "_melody.mid")
        Path(melody_data["midi_path"]).parent.mkdir(parents=True, exist_ok=True)
    print(f"[DEBUG] extract_melody_node returning melody_data with keys: {melody_data.keys() if melody_data else None}")
    record_thought(task_id, "extract_melody", f"旋律提取完成，音符数: {len(melody_data.get('melody_notes', []))}")
    return {
        "melody_data": melody_data,
        "melody_source_path": melody_source_path,
        "harmony_source_path": harmony_source_path,
        "melody_extractor": final_state.get("melody_extractor"),
        "selected_melody_extractor": final_state.get("selected_melody_extractor"),
        "melody_candidate_summary": final_state.get("melody_candidate_summary") or {},
        # 保留旧字段，兼容已有 checkpoint 和用户自定义的 extract graph。
        "source_for_melody": melody_source_path,
    }
