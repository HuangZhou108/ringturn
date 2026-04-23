from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.models import Task
from app.schemas import TaskListResponse, TaskListItem, PaginationParams

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/{user_id}/tasks", response_model=TaskListResponse)
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
    # 查询用户
    user = db.query(Task).filter(Task.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 构建查询
    query = db.query(Task).filter(Task.user_id == user_id)

    if status:
        query = query.filter(Task.status == status)

    # 分页
    total = query.count()
    tasks = query.order_by(Task.created_at.desc()) \
        .offset((page - 1) * page_size) \
        .limit(page_size) \
        .all()

    task_items = [
        TaskListItem(
            task_id=t.id,
            user_request=t.user_request,
            status=t.status.value,
            final_audio_url=t.final_audio_url,
            audio_duration=t.audio_duration,
            created_at=t.created_at,
        )
        for t in tasks
    ]

    return TaskListResponse(
        total=total,
        page=page,
        page_size=page_size,
        tasks=task_items,
    )
