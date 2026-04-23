import os
import uuid
from fastapi import UploadFile, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from app.core.config import get_settings

settings = get_settings()

class FileService:
    """文件服务类"""

    @staticmethod
    def save_upload_file(upload_file: UploadFile) -> tuple[str, str]:
        """
        保存上传的音频文件

        Args:
            upload_file: 上传的文件对象

        Returns:
            tuple: (文件ID, 保存路径)
        """
        # 验证文件格式
        file_ext = os.path.splitext(upload_file.filename)[1].lower().lstrip('.')
        if file_ext not in settings.SUPPORTED_AUDIO_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的音频格式: {file_ext}，支持: {settings.SUPPORTED_AUDIO_FORMATS}"
            )

        # 生成唯一文件名
        file_id = str(uuid.uuid4())
        filename = f"{file_id}.{file_ext}"
        file_path = Path(settings.UPLOADS_DIR) / filename

        # 保存文件
        with open(file_path, "wb") as f:
            f.write(upload_file.file.read())

        return file_id, str(file_path)

    @staticmethod
    def get_upload_path(file_id: str) -> Path:
        """
        根据文件ID获取上传文件路径

        Args:
            file_id: 文件ID（UUID）

        Returns:
            Path: 文件路径
        """
        # 尝试不同格式
        for ext in settings.SUPPORTED_AUDIO_FORMATS:
            path = Path(settings.UPLOADS_DIR) / f"{file_id}.{ext}"
            if path.exists():
                return path
        return None

    @staticmethod
    def save_audio_file(audio_data: bytes, task_id: str, format: str = "mp3") -> str:
        """
        保存生成的铃声文件

        Args:
            audio_data: 音频数据（字节）
            task_id: 任务ID
            format: 音频格式

        Returns:
            str: 保存的文件路径（相对路径）
        """
        filename = f"{task_id}.{format}"
        file_path = Path(settings.RINGTONES_DIR) / filename

        with open(file_path, "wb") as f:
            f.write(audio_data)

        return f"/static/ringtones/{filename}"

    @staticmethod
    def get_rington_path(task_id: str) -> Path:
        """
        获取铃声文件路径

        Args:
            task_id: 任务ID

        Returns:
            Path: 文件路径
        """
        return Path(settings.RINGTONES_DIR) / f"{task_id}.mp3"

    @staticmethod
    def get_file_size(file_path: Path) -> float:
        """获取文件大小（MB）"""
        return file_path.stat().st_size / (1024 * 1024)

file_service = FileService()
