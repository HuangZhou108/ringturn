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

    # 规划内容
    plan_description: str | None

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
    accompaniment_path: str | None      # 伴奏轨道路径（如 no_vocals.wav / other.wav）
    demucs_stems: str | None            # 使用的分离模式（'4' 或 None）
    # 分析结果
    analysis_result: Annotated[dict | None, merge_dicts]
    melody_data: dict | None
    midi_path: str | None

    # 旋律提取
    use_vocal_and_accompaniment: bool        # 已废弃：旋律提取已改为单一主旋律源（P0-1），不再双轨拼接
    melody_source_path: str | None           # 主旋律提取源：优先 vocals.wav，否则原音频
    harmony_source_path: str | None          # 和声上下文源：优先伴奏 stem，否则原音频
    source_for_melody: str | None            # 兼容旧 checkpoint / 自定义子图的旋律源别名
    melody_extractor: str | None             # 当前正在处理的旋律提取器
    melody_candidates: dict                  # 提取子图内的候选结果（选择后清空）
    melody_candidate_summary: dict           # 候选分数、问题与选择原因
    selected_melody_extractor: str | None    # 最终选中的提取器

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

    # 子图内部状态通道（必须在 state 中声明，否则 LangGraph 不会在节点间正确传递）
    should_separate: bool            # analysis 图：是否执行音源分离
    optional_decisions: dict         # analysis 图：是否做情绪/特效分析
    use_basic_pitch: bool            # extract 图：Basic Pitch 是否成功
    basic_pitch_failed: bool         # extract 图：Basic Pitch 是否失败
    quality_report: dict | None      # quality 图：质量评估报告

    # 反思和反馈
    feedback_history: list[dict]
    reflection: str | None
    needs_revision: bool
    correction: str | None                # 重试时的纠正动作（如 snap_to_key）
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
    resume_from_node: str | None       # 反馈起始节点

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
