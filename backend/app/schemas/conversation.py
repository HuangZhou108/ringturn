from pydantic import BaseModel, Field
from typing import Literal, Optional, List
from datetime import datetime


class ConversationCreate(BaseModel):
    """创建会话请求"""
    title: Optional[str] = Field(None, description="会话标题，不提供则自动截取首条消息")
    user_request: str = Field(..., description="首次用户请求")


class ConversationCreateResponse(BaseModel):
    """创建会话响应"""
    conversation_id: str
    title: str
    status: str
    created_at: datetime


class ConversationListItem(BaseModel):
    """会话列表项"""
    conversation_id: str
    title: Optional[str] = None
    status: str
    message_count: int
    last_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """会话列表响应"""
    total: int
    page: int
    page_size: int
    conversations: List[ConversationListItem]


class MessageItem(BaseModel):
    """消息项"""
    id: int
    role: str
    content: str
    task_id: Optional[str] = None
    created_at: datetime


class ConversationDetailResponse(BaseModel):
    """会话详情响应"""
    conversation_id: str
    title: Optional[str] = None
    status: str
    messages: List[MessageItem]
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    """添加消息请求"""
    role: Literal["user", "assistant"]
    content: str
    task_id: Optional[str] = None


class MessageCreateResponse(BaseModel):
    """添加消息响应"""
    message_id: int
    conversation_id: str
    role: str
    content: str
    task_id: Optional[str] = None
    created_at: datetime


class ConversationUpdate(BaseModel):
    """更新会话请求"""
    title: str = Field(..., description="新的会话标题")


class ConversationUpdateResponse(BaseModel):
    """更新会话响应"""
    conversation_id: str
    title: str


class ConversationCompleteResponse(BaseModel):
    """标记会话完成响应"""
    conversation_id: str
    status: str
