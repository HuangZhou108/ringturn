from pydantic import BaseModel, Field
from datetime import datetime

class FeedbackCreate(BaseModel):
    """创建反馈请求"""
    feedback: str = Field(..., alias="feedback", description="用户反馈内容")

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
