from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import asyncio
from functools import partial

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

    def _query_tasks_sync():
        # 查询用户是否存在
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None

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

        return {
            "user": user,
            "total": total,
            "tasks": tasks,
        }

    # 在线程池中执行查询，避免阻塞事件循环
    result = await asyncio.get_event_loop().run_in_executor(
        None, _query_tasks_sync
    )

    if result is None:
        return {
            "code": 400,
            "data": None,
            "message": "用户不存在。"
        }

    task_items = [
        {
            "task_id": t.id,
            "user_request": t.user_request,
            "status": t.status.value,
            "final_audio_url": t.final_audio_url,
            "audio_duration": t.audio_duration,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in result["tasks"]
    ]

    return {
        "code": 200,
        "data": {
            "total": result["total"],
            "page": page,
            "page_size": page_size,
            "tasks": task_items,
        },
        "message": "获取任务列表成功。",
    }
