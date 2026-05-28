from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid

from app.db.session import get_db
from app.models import Task, TaskStatus, Feedback
from app.schemas import (
    FeedbackCreate,
    FeedbackCreateResponse,
    FeedbackResponse,
    FeedbackListResponse,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/{task_id}/feedback", response_model=FeedbackCreateResponse)
async def submit_feedback(
    task_id: str,
    feedback: FeedbackCreate,
    db: Session = Depends(get_db),
):
    """
    提交反馈（创建子任务优化）

    根据用户的反馈意见，创建一个新的子任务进行优化
    """
    # 1. 验证父任务存在
    parent_task = db.query(Task).filter(Task.id == task_id).first()
    if not parent_task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    # 2. 将反馈保存到数据库
    feedback_record = Feedback(
        task_id=task_id,
        content=feedback.content,
    )
    db.add(feedback_record)

    # 3. 创建子任务（用于优化）
    new_task_id = str(uuid.uuid4())

    # 构建用户请求：原请求 + 反馈
    new_user_request = (
        f"[优化] {parent_task.user_request}\n"
        f"用户反馈: {feedback.content}"
    )

    child_task = Task(
        id=new_task_id,
        profile_id=parent_task.profile_id,
        parent_task_id=task_id,
        user_request=new_user_request,
        source_type=parent_task.source_type,
        source_value=parent_task.source_value,
        status=TaskStatus.pending,
    )
    db.add(child_task)
    db.commit()

    # 异步执行子任务优化
    from app.api.v1.endpoints.tasks import run_agent_task
    # 注意：BackgroundTasks需要在调用时传入，这里简化处理
    # 子任务将在下次查询时自动执行或由调度器触发

    return FeedbackCreateResponse(
        task_id=new_task_id,
        parent_task_id=task_id,
        status=child_task.status.value,
    )

@router.get("/{task_id}/feedbacks", response_model=FeedbackListResponse)
async def get_task_feedbacks(
    task_id: str,
    db: Session = Depends(get_db),
):
    """
    获取任务的反馈历史
    """
    # 验证任务存在
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    feedbacks = db.query(Feedback).filter(
        Feedback.task_id == task_id
    ).order_by(Feedback.created_at.desc()).all()

    feedback_items = [
        FeedbackResponse(
            id=f.id,
            task_id=f.task_id,
            content=f.content,
            created_at=f.created_at,
        )
        for f in feedbacks
    ]

    return FeedbackListResponse(
        total=len(feedback_items),
        feedbacks=feedback_items,
    )
