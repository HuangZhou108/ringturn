# nodes/extract_melody.py
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
    
    user_request = state.get("user_request", "")

    record_thought(task_id, "extract_melody", f"开始提取旋律：")

    # 构建临时 state 副本，避免污染原状态
    sub_state = {
        **state,
        "task_id": task_id,
        "audio_path": audio_path,
    }

    graph = await get_extract_graph(profile_id=profile_id)
    final_state = await graph.ainvoke(sub_state)

    melody_data = final_state.get("melody_data")
    if not melody_data:
        # 降级保险：直接调用 Basic Pitch
        from app.agent.atomic_tools.melody.extract_with_basic_pitch import extract_melody_basic_pitch
        melody_data = await extract_melody_basic_pitch(audio_path)
        record_thought(task_id, "extract_melody", "降级：直接调用 Basic Pitch 成功")

    # 确保 melody_data 包含 midi_path（即使未生成也放一个占位）
    if not melody_data.get("midi_path"):
        melody_data["midi_path"] = audio_path.replace(".mp3", "_melody.mid").replace(".wav", "_melody.mid")
        Path(melody_data["midi_path"]).parent.mkdir(parents=True, exist_ok=True)

    record_thought(task_id, "extract_melody", f"旋律提取完成，音符数: {len(melody_data.get('melody_notes', []))}")
    return {"melody_data": melody_data}