from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class ProfileCreate(BaseModel):
    """创建 Profile 请求"""
    name: str = Field(..., description="Profile 名称")


class ProfileUpdate(BaseModel):
    """更新 Profile 请求"""
    name: Optional[str] = Field(None, description="Profile 名称")
    preferences_data: Optional[str] = Field(None, description="偏好配置的 JSON 字符串")


class ProfileResponse(BaseModel):
    """Profile 响应"""
    profile_id: int
    name: str
    is_active: bool
    preferences_data: Optional[str] = None
    created_at: Optional[datetime] = None


class ProfileListResponse(BaseModel):
    """Profile 列表响应"""
    profile_id: int
    name: str
    is_active: bool
    created_at: Optional[datetime] = None


class PreferencesImport(BaseModel):
    """导入偏好配置请求"""
    preferences: Dict[str, Any] = Field(..., description="偏好配置对象")


class PreferencesExport(BaseModel):
    """导出偏好配置响应"""
    profile_name: str
    preferences: Dict[str, Any]
    exported_at: datetime


class PreferencesApply(BaseModel):
    """应用偏好到任务的请求"""
    default_instrument: Optional[str] = Field(None, description="默认乐器")
    default_duration: Optional[int] = Field(None, description="默认时长")
    default_tempo: Optional[int] = Field(None, description="默认 BPM")
    disliked_instruments: Optional[list[str]] = Field(None, description="不喜欢的乐器")
    liked_instruments: Optional[list[str]] = Field(None, description="喜欢的乐器")
    auto_apply: Optional[bool] = Field(True, description="是否自动应用")
