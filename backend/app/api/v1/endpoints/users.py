from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.models import Task, User
from app.schemas import TaskListResponse, TaskListItem

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/{user_id}/tasks")
async def get_user_tasks(
    user_id: int,
    page: int = 1,
    page_size: int = 10,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    获取用户历史任务列表
    """
    # 查询用户是否存在
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {
            "code": 400,
            "data": None,
            "message": "用户不存在。"
        }

    # 构建查询
    query = db.query(Task).filter(Task.user_id == user_id)

    if status:
        query = query.filter(Task.status == status)

    # 分页
    total = query.count()
    tasks = query.order_by(Task.created_at.desc()) \
        .offset((page - 1) * page_size) \
        .limit(min(page_size, 50)) \
        .all()

    task_items = [
        {
            "task_id": t.id,
            "user_request": t.user_request,
            "status": t.status.value,
            "final_audio_url": t.final_audio_url,
            "audio_duration": t.audio_duration,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]

    return {
        "code": 200,
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "tasks": task_items,
        },
        "message": "获取任务列表成功。",
    }
