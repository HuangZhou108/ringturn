"""
Agent节点处理逻辑

每个节点负责一个执行步骤的具体实现
"""

import os
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session

from app.agent.state import AgentState, TaskStep
from app.services.file_service import file_service
from app.agent.tools import tool_gateway
from app.core.config import get_settings

settings = get_settings()

async def fetch_source_node(state: AgentState, db: Session, tools) -> None:
    """
    节点1: 获取音频源

    根据source_type获取音频文件
    """
    source_type = state.get("source_type", "upload")
    source_value = state.get("source_value")

    if source_type == "upload":
        # 获取上传文件
        if not source_value:
            raise ValueError("上传类型需要提供source_value（文件ID）")

        file_path = file_service.get_upload_path(source_value)
        if not file_path:
            raise ValueError(f"文件不存在: {source_value}")

        state["audio_path"] = str(file_path)

    elif source_type == "search":
        # TODO: 实现搜索功能
        raise NotImplementedError("search类型暂未实现")

    else:
        raise ValueError(f"不支持的source_type: {source_type}")

async def analyze_structure_node(state: AgentState, db: Session, tools) -> None:
    """
    节点2: 分析音乐结构

    调用分析API提取BPM、调性、段落等
    """
    audio_path = state.get("audio_path")
    if not audio_path:
        raise ValueError("音频路径未设置")

    analysis = await tools.analyze_audio_structure(audio_path)
    state["analysis_result"] = analysis

async def extract_melody_node(state: AgentState, db: Session, tools) -> None:
    """
    节点3: 提取主旋律

    提取音频中的主旋律数据
    """
    audio_path = state.get("audio_path")
    if not audio_path:
        raise ValueError("音频路径未设置")

    melody = await tools.extract_melody(audio_path)
    state["melody_data"] = melody

async def generate_midi_node(state: AgentState, db: Session, tools) -> None:
    """
    节点4: 生成MIDI

    根据旋律和分析结果生成原始MIDI文件
    """
    melody = state.get("melody_data")
    analysis = state.get("analysis_result")

    if not melody or not analysis:
        raise ValueError("缺少旋律数据或分析结果")

    task_id = state["task_id"]
    midi_path = Path(settings.RINGTONES_DIR) / f"{task_id}_original.mid"

    await tools.generate_midi(melody, analysis, str(midi_path))
    state["midi_path"] = str(midi_path)

async def arrange_node(state: AgentState, db: Session, tools) -> None:
    """
    节点5: 乐器改编

    根据用户需求更换乐器、调整风格
    """
    # 解析用户需求（TODO: 使用LLM）
    user_request = state.get("user_request", "")

    # 简单的关键词解析（后续用LLM替代）
    target_instruments = []
    if "钢琴" in user_request or "piano" in user_request.lower():
        target_instruments.append("piano")
    if "吉他" in user_request or "guitar" in user_request.lower():
        target_instruments.append("guitar")
    if "弦乐" in user_request or "string" in user_request.lower():
        target_instruments.append("strings")

    if not target_instruments:
        target_instruments = ["piano"]  # 默认钢琴

    midi_path = state.get("midi_path")
    if not midi_path:
        raise ValueError("MIDI路径未设置")

    task_id = state["task_id"]
    arranged_midi_path = Path(settings.RINGTONES_DIR) / f"{task_id}_arranged.mid"

    await tools.arrange_instrument(
        midi_path,
        target_instruments,
        style=user_request,
        output_path=str(arranged_midi_path),
    )
    state["arranged_midi_path"] = str(arranged_midi_path)
    state["arrangement_params"] = {
        "instruments": target_instruments,
        "style": user_request,
    }

async def render_node(state: AgentState, db: Session, tools) -> None:
    """
    节点6: 渲染音频

    将改编后的MIDI渲染为音频文件
    """
    midi_path = state.get("arranged_midi_path") or state.get("midi_path")
    if not midi_path:
        raise ValueError("MIDI路径未设置")

    task_id = state["task_id"]
    output_path = Path(settings.RINGTONES_DIR) / f"{task_id}.mp3"

    # 乐器配置（使用配置文件中的音色库）
    instruments = {
        "default": settings.SOUNDFONT_PATH,
    }

    await tools.render_audio(
        midi_path,
        instruments,
        str(output_path),
        duration=settings.DEFAULT_RINGTONE_DURATION,
    )

    # 智能截取（可选）
    final_path, duration = await tools.smart_clip(
        str(output_path),
        target_duration=settings.DEFAULT_RINGTONE_DURATION,
    )

    state["final_audio_path"] = final_path
    state["audio_duration"] = duration

    # 生成URL
    state["final_audio_url"] = f"/static/ringtones/{task_id}.mp3"

async def check_quality_node(state: AgentState, db: Session, tools) -> None:
    """
    节点7: 质量检查

    评估生成音频的质量
    """
    audio_path = state.get("final_audio_path")
    if not audio_path:
        raise ValueError("最终音频路径未设置")

    quality = await tools.check_quality(audio_path)

    if not quality.get("passed", False):
        # TODO: 触发反思和重试机制
        state["reflection"] = "质量不达标，需要优化"
        state["needs_revision"] = True

    state["step_results"]["quality_check"] = quality

# 节点处理器映射（使用字符串键，与TaskStep枚举的value一致）
NODE_HANDLERS = {
    TaskStep.FETCH_SOURCE.value: fetch_source_node,
    TaskStep.ANALYZE_STRUCTURE.value: analyze_structure_node,
    TaskStep.EXTRACT_MELODY.value: extract_melody_node,
    TaskStep.GENERATE_MIDI.value: generate_midi_node,
    TaskStep.ARRANGE.value: arrange_node,
    TaskStep.RENDER.value: render_node,
    TaskStep.CHECK_QUALITY.value: check_quality_node,
}
