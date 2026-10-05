from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import uuid
import json
import asyncio

from app.db.session import get_db, SessionLocal
from app.models import Task as TaskModel, TaskStatus, Feedback, Conversation, ConversationMessage, ConversationStatus, MessageRole, Profile
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
from app.agent.observability import get_execution_trace
from app.api.v1.endpoints.profiles import get_active_profile as get_active_profile_from_db
from app.core.exceptions import (
    TaskNotFoundException,
    ProfileNotFoundException,
    TaskCannotBeCancelledException,
    AppException,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])
# 一个全局集合，保持对后台任务的引用，防止被 GC
_background_tasks = set()
_running_tasks: dict[str, AgentExecutor] = {}

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
        # 获取当前活跃的Profile
        profile = db.query(Profile).filter(Profile.is_active == 1).first()
        profile_id = profile.id if profile else None

        # 解析Profile偏好
        profile_preferences = {}
        if profile and profile.preferences_data:
            try:
                profile_preferences = json.loads(profile.preferences_data)
            except json.JSONDecodeError:
                profile_preferences = {}

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
                profile_id=profile_id,
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
            assistant_message = ConversationMessage(
                conversation_id=conversation_id,
                role=MessageRole.assistant,
                content="正在处理您的请求...",   # 占位内容
                task_id=task_id,
            )
            db.add(assistant_message)
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
            assistant_message = ConversationMessage(
                conversation_id=conversation_id,
                role=MessageRole.assistant,
                content="正在处理您的请求...",   # 占位内容
                task_id=task_id,
            )
            db.add(assistant_message)

        # 从 params 中提取已知参数，未提供则使用Profile偏好，最后使用默认值
        params = request.params or {}
        # 获取有效偏好
        from app.services.preference_service import get_effective_preference
        profile_preferences = get_effective_preference(profile_id, db) if profile_id else {}

        # 优先级：用户请求 > Profile偏好 > 默认值
        instrument = params.get("instrument", profile_preferences.get("instrument", "Acoustic Piano"))
        duration = params.get("duration", profile_preferences.get("duration", 30))
        tempo = params.get("tempo", profile_preferences.get("tempo", 120))
        filename = params.get("filename", "Untitled_Track")
        
        # 如果auto_apply开启，可以记录偏好到Profile（可选）
        auto_apply = profile_preferences.get("auto_apply", True)
        disliked_instruments = profile_preferences.get("disliked_instruments", [])
        liked_instruments = profile_preferences.get("liked_instruments", [])
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
            profile_id=profile_id,
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
    
    # 查找该任务关联的会话ID（通过第一条用户消息）
    user_message = db.query(ConversationMessage).filter(
        ConversationMessage.task_id == task_id,
        ConversationMessage.role == MessageRole.user
    ).first()
    conversation_id = user_message.conversation_id if user_message else None

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
            "conversation_id": conversation_id,
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


@router.get("/{task_id}/trace")
async def get_task_trace(
    task_id: str,
    db: Session = Depends(get_db),
):
    """获取结构化 Agent 执行轨迹（不包含模型提示词或隐藏推理）。"""
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not task:
        raise TaskNotFoundException(task_id)
    return {
        "code": 200,
        "data": {
            "task_id": task.id,
            "status": task.status.value,
            "events": get_execution_trace(task),
        },
        "message": "获取 Agent 执行轨迹成功。",
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

# @router.post("/{task_id}/feedback")
# async def submit_feedback(
#     task_id: str,
#     request: FeedbackCreate,
#     db: Session = Depends(get_db),
# ):
#     """
#     提交反馈（创建子任务优化）
#     同时将反馈追加到对应的会话中
#     """
#     parent_task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
#     if not parent_task:
#         raise TaskNotFoundException(task_id)

#     # 创建子任务
#     new_task_id = str(uuid.uuid4())
#     child_task = TaskModel(
#         id=new_task_id,
#         profile_id=parent_task.profile_id,
#         parent_task_id=task_id,
#         user_request=f"[优化] {parent_task.user_request} - 反馈: {request.feedback}",
#         status=TaskStatus.pending,
#     )
#     db.add(child_task)

#     # 同时记录反馈
#     feedback = Feedback(
#         task_id=task_id,
#         content=request.feedback,
#     )
#     db.add(feedback)

#     # 查找该任务关联的会话，并追加反馈消息
#     # 通过查找该任务创建时的用户消息来获取会话ID
#     user_message = db.query(ConversationMessage).filter(
#         ConversationMessage.task_id == task_id,
#         ConversationMessage.role == MessageRole.user
#     ).first()

#     if user_message:
#         # 添加用户反馈消息
#         feedback_msg = ConversationMessage(
#             conversation_id=user_message.conversation_id,
#             role=MessageRole.user,
#             content=f"[优化反馈] {request.feedback}",
#             task_id=new_task_id,
#         )
#         db.add(feedback_msg)

#         # 更新会话的更新时间
#         conversation = db.query(Conversation).filter(
#             Conversation.id == user_message.conversation_id
#         ).first()
#         if conversation:
#             conversation.updated_at = datetime.utcnow()

#     db.commit()

#     return {
#         "code": 200,
#         "data": {
#             "task_id": new_task_id,
#             "parent_task_id": task_id,
#             "status": child_task.status.value,
#         },
#         "message": "创建子任务成功。",
#     }

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
    
    # 查找对应的助手消息
    assistant_message = db.query(ConversationMessage).filter(
        ConversationMessage.task_id == task_id,
        ConversationMessage.role == MessageRole.assistant
    ).first()

    # 如果任务正在运行，调用 executor 的 cancel
    executor = _running_tasks.get(task_id)
    if executor:
        await executor.cancel()
    else:
        # 如果尚未开始运行或已结束但状态未更新，直接改数据库状态
        task.status = TaskStatus.cancelled
        db.commit()
        # 更新助手消息
        if assistant_message:
            assistant_message.content = "任务已取消"
            db.commit()

    return {
        "code": 200,
        "data": {
            "task_id": task.id,
            "previous_status": task.status.value,
            "current_status": TaskStatus.cancelled.value,
        },
        "message": "任务已取消。",
    }

async def run_agent_task(task_id: str):
    """
    在后台运行Agent任务

    Args:
        task_id: 任务ID
    """
    with SessionLocal(expire_on_commit=False) as db:  # SQLAlchemy 2.x 支持上下文
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            return
        task.status = TaskStatus.planning
        db.commit()

        agent_executor = AgentExecutor(task_id=task_id, db=db)
        _running_tasks[task_id] = agent_executor
        # 创建异步任务，并保存引用
        async_task = asyncio.create_task(agent_executor.execute())
        _background_tasks.add(async_task)
        try:
            result = await async_task
            # 任务执行完成后，如果是成功，则更新偏好统计
            if result and result.get("success"):
                from app.services.preference_service import update_profile_preference_stats
                # 注意：需要获取 profile_id，可以从 task 中读取
                # 由于 agent_executor 已经关闭，需要重新查询 task
                with SessionLocal() as db2:
                    task2 = db2.query(TaskModel).filter(TaskModel.id == task_id).first()
                    if task2 and task2.profile_id:
                        # 异步执行，不阻塞（使用 background_tasks 或创建新任务）
                        if result and result.get("success"):
                            asyncio.create_task(update_profile_preference_stats(task.profile_id, task_id))
        except Exception as e:
            print(f"[ERROR] Agent task {task_id} failed: {e}")
        finally:
            _background_tasks.discard(async_task)
            agent_executor.close()  # 显式关闭内部会话（如果 db 是外部传入，则不会重复关闭）
            if task_id in _running_tasks:
                del _running_tasks[task_id]
            import gc
            gc.collect()
            # 额外：强制释放 Python 的内存 arena 给操作系统（需要 ctypes）
            import ctypes
            libc = ctypes.CDLL("msvcrt.dll")  # Windows
            libc._heapmin()
