from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import uuid
import json

from app.db.session import get_db, SessionLocal
from app.models import Task as TaskModel, TaskStatus, User, Feedback, Conversation, ConversationMessage, ConversationStatus, MessageRole
from app.schemas import (
    TaskCreate,
    TaskCreateResponse,
    TaskDetailResponse,
    TaskStatusResponse,
    TaskResultResponse,
    TaskCancelResponse,
    TaskListItem,
    TaskListResponse,
    SUBTASKS,
    FeedbackCreate,
)
from app.services.file_service import file_service
from app.agent.agent_executor import AgentExecutor
from app.core.exceptions import (
    TaskNotFoundException,
    UserNotFoundException,
    TaskCannotBeCancelledException,
    AppException,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])

def get_or_create_default_user(db: Session) -> User:
    """获取或创建默认用户"""
    user = db.query(User).filter(User.username == "default").first()
    if not user:
        user = User(id=1, username="default")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

@router.post("")
async def create_task(
    request: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    创建任务（开始生成铃声）

    异步触发Agent执行，立即返回task_id
    同时创建或关联会话（历史会话功能）
    """
    try:
        # 获取或创建默认用户
        user = get_or_create_default_user(db)
        user_id = user.id

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 处理会话关联
        conversation_id = request.conversation_id
        if not conversation_id:
            # 如果没有提供会话ID，创建新会话
            conversation_id = str(uuid.uuid4())
            title = request.user_request[:50] + "..." if len(request.user_request) > 50 else request.user_request
            conversation = Conversation(
                id=conversation_id,
                user_id=user_id,
                title=title,
                status=ConversationStatus.active,
            )
            db.add(conversation)

            # 创建第一条用户消息
            first_message = ConversationMessage(
                conversation_id=conversation_id,
                role=MessageRole.user,
                content=request.user_request,
                task_id=task_id,
            )
            db.add(first_message)
        else:
            # 验证会话存在
            conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conversation:
                return {
                    "code": 400,
                    "data": {},
                    "message": f"会话 {conversation_id} 不存在",
                }

            # 添加用户消息到会话
            user_message = ConversationMessage(
                conversation_id=conversation_id,
                role=MessageRole.user,
                content=request.user_request,
                task_id=task_id,
            )
            db.add(user_message)

        # 从 params 中提取已知参数，未提供则使用默认值
        params = request.params or {}
        instrument = params.get("instrument", "Acoustic Piano")
        duration = params.get("duration", 30)
        tempo = params.get("tempo", 120)
        filename = params.get("filename", "Untitled_Track")
        ringtone_params = {
            "instrument": instrument,
            "duration": duration,
            "tempo": tempo,
            "filename": filename,
        }
        # 如果将来有额外参数，一并保留
        for k, v in params.items():
            if k not in ringtone_params:
                ringtone_params[k] = v

        # 创建任务记录
        task = TaskModel(
            id=task_id,
            user_id=user_id,
            user_request=request.user_request,
            source_type=request.source_type,
            source_value=request.source_value,  # 文件ID或链接（字符串）
            ringtone_params=ringtone_params,   # 铃声参数（JSON）
            status=TaskStatus.pending,
        )
        db.add(task)
        db.commit()

        # 异步触发Agent执行
        background_tasks.add_task(run_agent_task, task_id)

        return {
            "code": 200,
            "data": {
                "task_id": task_id,
                "conversation_id": conversation_id,
                "status": task.status.value,
                "created_at": task.created_at.isoformat() if task.created_at else None,
            },
            "message": "任务创建成功。",
        }
    except Exception as e:
        return {
            "code": 400,
            "data": {},
            "message": f"任务创建失败: {str(e)}",
        }

@router.get("/{task_id}")
async def get_task(
    task_id: str,
    db: Session = Depends(get_db),
):
    """获取任务详情"""
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        raise TaskNotFoundException(task_id)

    return {
        "code": 200,
        "data": {
            "task_id": task.id,
            "user_request": task.user_request,
            "status": task.status.value,
            "source_type": task.source_type,
            "source_value": task.source_value,
            "final_audio_url": task.final_audio_url,
            "audio_duration": task.audio_duration,
            "plan": task.plan,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        },
        "message": "获取任务详情成功。",
    }

@router.get("/{task_id}/status")
async def get_task_status(
    task_id: str,
    db: Session = Depends(get_db),
):
    """获取任务状态（包括进度信息）"""
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        raise TaskNotFoundException(task_id)

    # 根据状态生成友好的消息
    status_messages = {
        "pending": "任务等待处理...",
        "planning": "正在制定执行计划...",
        "executing": f"正在执行: {task.current_subtask or '处理中'}",
        "waiting_input": "等待用户输入...",
        "completed": "任务已完成",
        "failed": f"任务失败: {task.error_message or '未知错误'}",
        "cancelled": "任务已取消",
    }

    message = status_messages.get(task.status.value, f"状态: {task.status.value}")

    return {
        "code": 200,
        "data": {
            "task_id": task.id,
            "status": task.status.value,
            "current_subtask": task.current_subtask,
            "subtask_progress": task.subtask_progress or 0.0,
            "message": message,
            "thinking_process": task.thinking_process or [],
        },
        "message": message,
    }

@router.get("/{task_id}/result")
async def get_task_result(
    task_id: str,
    db: Session = Depends(get_db),
):
    """获取任务生成结果"""
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        raise TaskNotFoundException(task_id)

    if task.status != TaskStatus.completed:
        return {
            "code": 200,
            "data": None,
            "message": "任务未完成。",
        }

    return {
        "code": 200,
        "data": {
            "audio_url": task.final_audio_url,
            "duration": task.audio_duration,
            "format": "mp3",
            "thinking_process": task.thinking_process or [],
        },
        "message": "获取任务结果成功。",
    }

@router.post("/{task_id}/feedback")
async def submit_feedback(
    task_id: str,
    request: FeedbackCreate,
    db: Session = Depends(get_db),
):
    """
    提交反馈（创建子任务优化）
    同时将反馈追加到对应的会话中
    """
    parent_task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not parent_task:
        raise TaskNotFoundException(task_id)

    # 创建子任务
    new_task_id = str(uuid.uuid4())
    child_task = TaskModel(
        id=new_task_id,
        user_id=parent_task.user_id,
        parent_task_id=task_id,
        user_request=f"[优化] {parent_task.user_request} - 反馈: {request.feedback}",
        status=TaskStatus.pending,
    )
    db.add(child_task)

    # 同时记录反馈
    feedback = Feedback(
        task_id=task_id,
        content=request.feedback,
    )
    db.add(feedback)

    # 查找该任务关联的会话，并追加反馈消息
    # 通过查找该任务创建时的用户消息来获取会话ID
    user_message = db.query(ConversationMessage).filter(
        ConversationMessage.task_id == task_id,
        ConversationMessage.role == MessageRole.user
    ).first()

    if user_message:
        # 添加用户反馈消息
        feedback_msg = ConversationMessage(
            conversation_id=user_message.conversation_id,
            role=MessageRole.user,
            content=f"[优化反馈] {request.feedback}",
            task_id=new_task_id,
        )
        db.add(feedback_msg)

        # 更新会话的更新时间
        conversation = db.query(Conversation).filter(
            Conversation.id == user_message.conversation_id
        ).first()
        if conversation:
            conversation.updated_at = datetime.utcnow()

    db.commit()

    return {
        "code": 200,
        "data": {
            "task_id": new_task_id,
            "parent_task_id": task_id,
            "status": child_task.status.value,
        },
        "message": "创建子任务成功。",
    }

@router.delete("/{task_id}")
async def cancel_task(
    task_id: str,
    db: Session = Depends(get_db),
):
    """取消任务"""
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        raise TaskNotFoundException(task_id)

    if task.status in [TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled]:
        return {
            "code": 400,
            "data": None,
            "message": "任务已完成，无法取消。",
        }

    previous_status = task.status.value
    task.status = TaskStatus.cancelled
    db.commit()

    return {
        "code": 200,
        "data": {
            "task_id": task.id,
            "previous_status": previous_status,
            "current_status": task.status.value,
        },
        "message": "任务已取消。",
    }

async def run_agent_task(task_id: str):
    """
    在后台运行Agent任务（使用独立线程，避免阻塞）

    Args:
        task_id: 任务ID
    """
    import threading
    
    def run_in_thread():
        db = SessionLocal(expire_on_commit=False)
        try:
            # 更新状态为planning
            task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
            if not task:
                print(f"[ERROR] Task {task_id} not found")
                return
            task.status = TaskStatus.planning
            db.commit()

            # 初始化Agent执行器
            agent_executor = AgentExecutor(task_id=task_id, db=db)

            # 创建新的事件循环给这个线程用
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # 执行任务
                result = loop.run_until_complete(agent_executor.execute())
            finally:
                loop.close()

            # 更新任务状态为completed
            task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
            if task:
                task.status = TaskStatus.completed
                task.final_audio_url = result["audio_url"]
                task.audio_duration = result["duration"]
                task.current_subtask = None
                task.subtask_progress = 1.0
                db.commit()
                print(f"[SUCCESS] Task {task_id} completed")

        except Exception as e:
            print(f"[ERROR] Task {task_id} failed: {e}")
            import traceback
            traceback.print_exc()
            # 更新任务状态为failed
            task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
            if task:
                task.status = TaskStatus.failed
                task.error_message = str(e)
                db.commit()
        finally:
            db.close()
    
    # 在独立线程中运行，完全不阻塞主应用
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
