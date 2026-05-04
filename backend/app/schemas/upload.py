from pydantic import BaseModel
from datetime import datetime

class UploadResponse(BaseModel):
    """文件上传响应"""
    file_id: str
    filename: str
    file_size: float  # MB
    format: str
    duration: float | None = None  # 秒
    created_at: datetime

class UploadMetadata(BaseModel):
    """上传元数据（可选）"""
    title: str | None = None
    artist: str | None = None
    album: str | None = None
