"""
思考过程记录工具函数
避免循环导入
"""

from datetime import datetime
from app.db.session import SessionLocal
from app.models import Task as TaskModel


def record_thought(task_id: str, step: str, content: str) -> None:
    """
    线程安全的思考过程记录，可在任何异步上下文中调用
    """
    db = SessionLocal()
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if task:
            steps = list(task.thinking_process or [])
            steps.append({
                "step": step,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            })
            task.thinking_process = steps
            db.commit()
            db.refresh(task)
    except Exception as e:
        print(f"[ERROR] record_thought: {e}")
    finally:
        db.close()