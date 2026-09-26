from pathlib import Path
from sqlalchemy.orm import Session
from app.agent.state import AgentState
from app.core.config import get_settings
from app.agent.atomic_tools.midi.create_from_notes import create_midi_from_notes
from app.agent.utils import clean_state
from app.agent.utils import log_tool_call
import mido
import shutil
settings = get_settings()

@clean_state
async def generate_midi_node(state: AgentState) -> dict:
    """
    节点4: 生成MIDI

    根据旋律和分析结果生成原始MIDI文件

    由于步骤固定，不再调用大模型。
    """
    plan = state.get("plan", [])
    if "generate_midi" not in plan:   
        return {}
    
    melody_data = state["melody_data"]
    analysis_result = state["analysis_result"]
    task_id = state["task_id"]
    # 创建任务专属目录
    task_dir = Path(settings.RINGTONES_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(task_dir / "generate_midi_original.mid")

    # BPM 取自分析结果（tempo_beats.bpm），而非顶层 bpm（后者不存在）
    if isinstance(analysis_result, dict):
        bpm = (analysis_result.get("tempo_beats") or {}).get("bpm") or 120
    else:
        bpm = 120

    notes = melody_data.get("melody_notes", [])

    if notes:
        # 始终从（经过 filter_short / quantize / merge 处理后的）melody_notes 重新生成 MIDI，
        # 并应用 legato 连奏。直接复制 Basic Pitch 的原始 MIDI 会让后处理失效（碎片化）。
        await log_tool_call(
            task_id=task_id,
            step_name="generate_midi",
            tool_func=create_midi_from_notes,
            notes=notes,
            bpm=bpm,
            output_path=output_path,
            legato_overlap=0.03,
            legato_max_gap=0.08,
            sustain=1.0,
            loop_to_duration=float(state.get("duration", 30)),
            tool_name="create_midi_from_notes"
        )
    else:
        # 无音符时降级：复用已有 MIDI（若有）
        existing_midi = melody_data.get("midi_path")
        if existing_midi and Path(existing_midi).exists():
            shutil.copy(existing_midi, output_path)
        else:
            raise RuntimeError("旋律提取未产生任何音符，且无可用 MIDI")
    
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
    
    return {"midi_path": output_path}