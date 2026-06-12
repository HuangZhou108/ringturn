from typing import TypedDict, List, Any, Annotated
from langgraph.graph.message import add_messages
from datetime import datetime
from enum import Enum

def merge_dicts(left: dict, right: dict) -> dict:
    """后者胜出的归约器，用于合并多个并行节点的更新。"""
    if left is None:
        left = {}
    if right is None:
        right = {}
    merged = left.copy()
    merged.update(right)
    return merged

class TaskStep(str, Enum):
    """子步骤枚举"""
    FETCH_SOURCE = "fetch_source"
    ANALYZE_STRUCTURE = "analyze_structure"
    EXTRACT_MELODY = "extract_melody"
    GENERATE_MIDI = "generate_midi"
    ARRANGE = "arrange"
    RENDER = "render"
    CHECK_QUALITY = "check_quality"

class AgentState(TypedDict, total=False):
    """
    Agent状态定义

    LangGraph使用这个TypedDict来管理Agent的内部状态
    """
    # 基础信息
    task_id: str
    user_request: str
    profile_id: int

    # 音频源
    source_type: str
    source_value: str
    file_id: str | None  # 上传文件的ID
    audio_path: str | None

    # 铃声参数
    instrument: str
    duration: int
    tempo: int
    filename: str

    # Demucs 分离结果（由 analysis 节点填充）
    demucs_separated: bool              # 是否执行了分离
    vocals_path: str | None             # 人声轨道路径（如果有分离）
    accompaniment_path: str | None      # 伴奏轨道路径（other.wav，如果有分离）
    demucs_stems: str | None            # 使用的分离模式（'4' 或 None）
    # 分析结果
    analysis_result: Annotated[dict | None, merge_dicts]
    melody_data: dict | None
    midi_path: str | None

    # 改编参数
    arrange_temp_path: str | None
    arrangement_params: dict | None
    arranged_midi_path: str | None

    # 最终输出
    final_audio_path: str | None
    final_audio_url: str | None
    audio_duration: float | None

    # 进度跟踪
    current_step: TaskStep | None
    current_step_index: int
    plan: list[str]
    step_results: dict

    # 反思和反馈
    feedback_history: list[dict]
    reflection: str | None
    needs_revision: bool
    user_approve_retry: bool   # 用户是否允许重试，默认 False
    max_retries: int  # 最大重试次数（用户可配置，默认0）

    # 错误处理
    error: str | None
    retry_count: int

    # 元数据
    created_at: datetime
    updated_at: datetime

    # LangGraph
    thread_id: str                     # LangGraph 线程 ID
    human_feedback: str | None         # 用户反馈内容
    waiting_for_feedback: bool         # 是否等待用户输入

def get_step_index(step: TaskStep) -> int:
    """获取步骤索引"""
    steps = list(TaskStep)
    return steps.index(step) if step in steps else -1

def get_step_message(step: TaskStep) -> str:
    """获取步骤描述"""
    messages = {
        TaskStep.FETCH_SOURCE: "正在获取音频源...",
        TaskStep.ANALYZE_STRUCTURE: "正在分析音乐结构...",
        TaskStep.EXTRACT_MELODY: "正在提取主旋律...",
        TaskStep.GENERATE_MIDI: "正在生成MIDI...",
        TaskStep.ARRANGE: "正在改编乐器...",
        TaskStep.RENDER: "正在渲染音频...",
        TaskStep.CHECK_QUALITY: "正在质量检查...",
    }
    return messages.get(step, "处理中...")
