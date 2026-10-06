"""
思考过程记录工具函数
避免循环导入
"""

from datetime import datetime
from app.db.session import SessionLocal
from app.models import Task as TaskModel


def record_thought(task_id: str, step: str, content: str, type: str = "info", status: str = None) -> None:
    """
    线程安全的思考过程记录，可在任何异步上下文中调用

    :param task_id: 任务ID
    :param step: 步骤名称
    :param content: 内容文本
    :param type: 条目类型，可选值: 'info', 'llm', 'tool_call', 'tool_result', 'error'
    :param status: 状态，可选值: 'success', 'failed', 'pending', 'retry' 等
    """
    entry = None
    db = SessionLocal()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if task:
            steps = list(task.thinking_process or [])
            entry = {
                "step": step,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
            }
            # 仅当 type 或 status 有实际值时才存入，保留旧数据兼容性
            if type:
                entry["type"] = type
            if status:
                entry["status"] = status
            steps.append(entry)
            task.thinking_process = steps
            db.commit()
            db.refresh(task)
    except Exception as e:
        print(f"[ERROR] record_thought: {e}")
    finally:
        db.close()
    if entry is not None:
        from app.services.task_events import emit_task_event

        emit_task_event(task_id, "thinking_update", {"thinking": entry})
