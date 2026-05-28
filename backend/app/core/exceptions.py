from fastapi import HTTPException, status

class AppException(HTTPException):
    """应用基础异常"""
    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)

class TaskNotFoundException(AppException):
    """任务不存在"""
    def __init__(self, task_id: str = None):
        detail = f"任务不存在: {task_id}" if task_id else "任务不存在"
        super().__init__(status_code=404, detail=detail)

class ProfileNotFoundException(AppException):
    """档案不存在"""
    def __init__(self, profile_id: int = None):
        detail = f"档案不存在: {profile_id}" if profile_id else "档案不存在"
        super().__init__(status_code=404, detail=detail)

class TaskNotCompletedException(AppException):
    """任务未完成"""
    def __init__(self, task_id: str = None):
        detail = f"任务未完成: {task_id}" if task_id else "任务未完成"
        super().__init__(status_code=400, detail=detail)

class TaskCannotBeCancelledException(AppException):
    """任务无法取消（已完成/已失败）"""
    def __init__(self, task_id: str = None):
        detail = f"任务已完成或已失败，无法取消: {task_id}" if task_id else "任务已完成或已失败，无法取消"
        super().__init__(status_code=400, detail=detail)

class InvalidAudioFormatException(AppException):
    """不支持的音频格式"""
    def __init__(self, format: str = None):
        detail = f"不支持的音频格式: {format}" if format else "不支持的音频格式"
        super().__init__(status_code=400, detail=detail)

class AudioFileTooLargeException(AppException):
    """音频文件过大"""
    def __init__(self, size_mb: float = None):
        detail = f"音频文件过大: {size_mb}MB" if size_mb else "音频文件过大"
        super().__init__(status_code=400, detail=detail)

class AgentExecutionException(AppException):
    """Agent执行异常"""
    def __init__(self, message: str = "Agent执行失败"):
        super().__init__(status_code=500, detail=message)
