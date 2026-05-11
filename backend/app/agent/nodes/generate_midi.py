from pathlib import Path
from sqlalchemy.orm import Session
from app.agent.state import AgentState
from app.core.config import get_settings
from app.agent.atomic_tools.midi.create_from_notes import create_midi_from_notes
import mido
settings = get_settings()

async def generate_midi_node(state: AgentState, db: Session, tools) -> None:
    """
    节点4: 生成MIDI

    根据旋律和分析结果生成原始MIDI文件

    由于步骤固定，不再调用大模型。
    """
    melody_data = state["melody_data"]
    analysis_result = state["analysis_result"]
    task_id = state["task_id"]
    # 创建任务专属目录
    task_dir = Path(settings.RINGTONES_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(task_dir / "generate_midi_original.mid")

    # 直接调用工具函数，避免LLM token限制导致失败
    from app.agent.atomic_tools.midi.create_from_notes import create_midi_from_notes
    await create_midi_from_notes(
        notes=melody_data.get("melody_notes", []),
        bpm=analysis_result.get("bpm", 120),
        output_path=output_path
    )
    
    # 验证文件是否生成成功
    output_path_obj = Path(output_path)
    if not output_path_obj.exists():
        raise RuntimeError("MIDI 文件生成失败：文件不存在")
    if output_path_obj.stat().st_size == 0:
        raise RuntimeError("MIDI 文件生成失败：文件为空")
    try:
        mido.MidiFile(output_path)
    except Exception as e:
        raise RuntimeError(f"MIDI 文件无效: {e}")
    
    state["midi_path"] = output_path