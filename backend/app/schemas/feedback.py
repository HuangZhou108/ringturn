from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any

class FeedbackCreate(BaseModel):
    """创建反馈请求"""
    feedback: str = Field(..., alias="feedback", description="用户反馈内容")
    parent_task_id: str  # 要针对哪个任务反馈
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
