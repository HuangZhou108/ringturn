"""
文件上传接口
"""
import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from datetime import datetime

from app.schemas.upload import UploadResponse, UploadMetadata
from app.services.file_service import file_service
from app.core.config import get_settings

router = APIRouter(prefix="/upload", tags=["upload"])
settings = get_settings()

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}


@router.post("", response_model=UploadResponse)
async def upload_audio(
    file: UploadFile = File(...),
    metadata: UploadMetadata | None = None,
):
    """
    上传音频文件

    支持格式: mp3, wav, flac, m4a, ogg
    最大文件大小: 50MB
    """
    # 验证文件格式
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件名")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的音频格式: {ext}，支持: {list(ALLOWED_EXTENSIONS)}"
        )

    # 验证文件大小
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to start

    max_size = settings.MAX_AUDIO_SIZE_MB * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大，最大支持 {settings.MAX_AUDIO_SIZE_MB}MB"
        )

    # 保存文件
    try:
        file_id, file_path = file_service.save_upload_file(file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 获取音频时长（可选）
    duration = None
    try:
        import librosa
        duration = librosa.get_duration(path=file_path)
    except Exception:
        pass  # 获取时长失败不影响上传

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        file_size=round(file_size / (1024 * 1024), 2),
        format=ext.lstrip("."),
        duration=duration,
        created_at=datetime.utcnow(),
    )
