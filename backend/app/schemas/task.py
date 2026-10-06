import json
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

# 子步骤定义
SUBTASKS = [
    "fetch_source",       # 获取音频源
    "analyze_structure",  # 分析音乐结构
    "extract_melody",     # 提取主旋律
    "generate_midi",      # 生成 MIDI
    "arrange",            # 乐器改编
    "render",             # 渲染音频
    "check_quality",      # 质量检查
]

class TaskCreate(BaseModel):
    """创建任务请求"""
    user_request: str = Field(..., description="用户的自然语言描述")
    source_type: Literal["upload", "search"] = "upload"
    source_value: str | None = None
    # 关联的会话ID（可选，用于历史会话功能）
    conversation_id: str | None = Field(None, description="关联的会话ID")
    # 铃声参数
    # 动态参数，包含 instrument、duration、tempo、filename 等
    params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="用户自定义参数键值对")

class TaskCreateResponse(BaseModel):
    """创建任务响应"""
    task_id: str
    status: str
    created_at: datetime

class TaskDetailResponse(BaseModel):
    """任务详情响应"""
    task_id: str
    user_request: str
    status: str
    source_type: str | None = None
    source_value: str | None = None
    final_audio_url: str | None = None
    audio_duration: float | None = None
    plan: list[str] | None = None
    created_at: datetime
    updated_at: datetime

class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str
    current_subtask: str | None = None
    subtask_progress: float = 0.0
    message: str | None = None
    thinking_process: list[dict] | None = None  # 思考过程
    trace_event_count: int = 0
    latest_trace_event: dict | None = None
    execution_error: dict | None = None
    intervention_id: str | None = None
    intervention_question: str | None = None

class TaskResultResponse(BaseModel):
    """任务结果响应"""
    audio_url: str | None = None
    duration: float | None = None
    format: str = "mp3"

class TaskCancelResponse(BaseModel):
    """任务取消响应"""
    task_id: str
    previous_status: str
    current_status: str

class TaskListItem(BaseModel):
    """任务列表项"""
    task_id: str
    user_request: str
    status: str
    final_audio_url: str | None = None
    audio_duration: float | None = None
    created_at: datetime

class TaskListResponse(BaseModel):
    """任务列表响应"""
    total: int
    page: int
    page_size: int
    tasks: list[TaskListItem]
