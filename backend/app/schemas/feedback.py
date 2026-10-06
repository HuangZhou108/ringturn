from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, Literal

class FeedbackCreate(BaseModel):
    """创建反馈请求"""
    feedback: str = Field(..., alias="feedback", description="用户反馈内容")
    parent_task_id: str | None = None  # 兼容旧客户端；路径参数是权威任务 ID
    params: Optional[Dict[str, Any]] = Field(default=None, description="要覆盖的铃声参数")

    class Config:
        populate_by_name = True

class FeedbackCreateResponse(BaseModel):
    """创建反馈响应（创建子任务）"""
    task_id: str
    parent_task_id: str
    status: str

class FeedbackResponse(BaseModel):
    """反馈详情响应"""
    id: int
    task_id: str
    content: str
    created_at: datetime

class FeedbackListResponse(BaseModel):
    """反馈列表响应"""
    total: int
    feedbacks: list[FeedbackResponse]


class HumanInterventionCreate(BaseModel):
    """暂停任务并请求人工输入。"""
    question: str = Field(..., min_length=1, max_length=1000)
    resume_from_node: Literal[
        "fetch_source",
        "analyze_structure",
        "extract_melody",
        "generate_midi",
        "arrange",
        "render",
        "check_quality",
    ] = "arrange"


class HumanInterventionAnswer(BaseModel):
    """回答一个待处理的人工介入请求。"""
    response: str = Field(..., min_length=1, max_length=4000)
    params: Optional[Dict[str, Any]] = None


class HumanInterventionResponse(BaseModel):
    intervention_id: str
    task_id: str
    status: str
    question: str
    response: str | None = None
    resume_from_node: str | None = None
    created_at: datetime
    responded_at: datetime | None = None
