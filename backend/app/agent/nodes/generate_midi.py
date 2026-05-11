from pathlib import Path
from sqlalchemy.orm import Session
from app.agent.state import AgentState
from app.core.config import get_settings
from app.agent.atomic_tools.midi.create_from_notes import create_midi_from_notes
import mido
import shutil
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
    # 检查旋律提取是否已生成 MIDI
    existing_midi = melody_data.get("midi_path")
    if existing_midi and Path(existing_midi).exists():
        # 直接复制或移动已有的 MIDI 到目标路径
        shutil.copy(existing_midi, output_path)
    else:
        # 降级：重新生成
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