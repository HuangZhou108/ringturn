"""
历史会话管理接口
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from app.db.session import get_db
from app.models import Conversation as ConversationModel, ConversationMessage as MessageModel, ConversationStatus, MessageRole, Task as TaskModel, TaskStatus
from app.schemas.conversation import (
    ConversationCreate,
    ConversationCreateResponse,
    ConversationListItem,
    ConversationListResponse,
    ConversationDetailResponse,
    MessageItem,
    MessageCreate,
    MessageCreateResponse,
    ConversationUpdate,
    ConversationUpdateResponse,
    ConversationCompleteResponse,
)
from app.core.exceptions import AppException

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationNotFoundException(AppException):
    """会话不存在异常"""
    def __init__(self, conversation_id: str):
        self.status_code = 404
        self.detail = f"会话 {conversation_id} 不存在"


class MessageNotFoundException(AppException):
    """消息不存在异常"""
    def __init__(self, message_id: int):
        self.status_code = 404
        self.detail = f"消息 {message_id} 不存在"


def get_or_create_default_user(db: Session):
    """获取或创建默认用户"""
    from app.models import User
    user = db.query(User).filter(User.username == "default").first()
    if not user:
        user = User(id=1, username="default")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.post("", response_model=dict)
async def create_conversation(
    request: ConversationCreate,
    db: Session = Depends(get_db),
):
    """
    创建新会话

    同时创建第一条用户消息
    """
    try:
        user = get_or_create_default_user(db)
        conversation_id = str(uuid.uuid4())

        title = request.title or (request.user_request[:50] + "..." if len(request.user_request) > 50 else request.user_request)

        conversation = ConversationModel(
            id=conversation_id,
            user_id=user.id,
            title=title,
            status=ConversationStatus.active,
        )
        db.add(conversation)

        first_message = MessageModel(
            conversation_id=conversation_id,
            role=MessageRole.user,
            content=request.user_request,
        )
        db.add(first_message)

        db.commit()

        return {
            "code": 200,
            "data": {
                "conversation_id": conversation_id,
                "title": title,
                "status": conversation.status.value,
                "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
            },
            "message": "会话创建成功",
        }
    except Exception as e:
        return {
            "code": 400,
            "data": {},
            "message": f"会话创建失败: {str(e)}",
        }


@router.get("", response_model=dict)
async def list_conversations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态过滤"),
    db: Session = Depends(get_db),
):
    """
    获取会话列表

    按更新时间倒序排列
    """
    user = get_or_create_default_user(db)

    query = db.query(ConversationModel).filter(ConversationModel.user_id == user.id)

    if status:
        try:
            status_enum = ConversationStatus(status)
            query = query.filter(ConversationModel.status == status_enum)
        except ValueError:
            pass

    total = query.count()

    conversations = query.order_by(ConversationModel.updated_at.desc()) \
        .offset((page - 1) * page_size) \
        .limit(page_size) \
        .all()

    result = []
    for conv in conversations:
        message_count = db.query(MessageModel).filter(
            MessageModel.conversation_id == conv.id
        ).count()

        last_message_obj = db.query(MessageModel).filter(
            MessageModel.conversation_id == conv.id
        ).order_by(MessageModel.created_at.desc()).first()

        last_message = None
        if last_message_obj:
            last_message = last_message_obj.content[:100] + "..." if len(last_message_obj.content) > 100 else last_message_obj.content

        result.append({
            "conversation_id": conv.id,
            "title": conv.title,
            "status": conv.status.value,
            "message_count": message_count,
            "last_message": last_message,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        })

    return {
        "code": 200,
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "conversations": result,
        },
        "message": "获取成功",
    }


@router.get("/{conversation_id}", response_model=dict)
async def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
):
    """
    获取会话详情（包括所有消息）
    """
    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == conversation_id
    ).first()

    if not conversation:
        raise ConversationNotFoundException(conversation_id)

    messages = db.query(MessageModel).filter(
        MessageModel.conversation_id == conversation_id
    ).order_by(MessageModel.created_at.asc()).all()

    message_list = []
    for msg in messages:
        # 如果是助理消息且关联了任务，则查询该任务的思考过程
        thinking_process = None
        if msg.role == MessageRole.assistant and msg.task_id:
            task = db.query(TaskModel).filter(TaskModel.id == msg.task_id).first()
            if task:
                thinking_process = task.thinking_process  # 直接取 JSON 字段

        message_list.append({
            "id": msg.id,
            "role": msg.role.value,
            "content": msg.content,
            "task_id": msg.task_id,
            "thinking_process": thinking_process,  # 新增字段
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        })

    return {
        "code": 200,
        "data": {
            "conversation_id": conversation.id,
            "title": conversation.title,
            "status": conversation.status.value,
            "messages": message_list,
            "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
            "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
        },
        "message": "获取成功",
    }


@router.delete("/{conversation_id}", response_model=dict)
async def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
):
    """
    删除会话（级联删除所有消息）
    """
    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == conversation_id
    ).first()

    if not conversation:
        raise ConversationNotFoundException(conversation_id)

    db.delete(conversation)
    db.commit()

    return {
        "code": 200,
        "data": {
            "conversation_id": conversation_id,
        },
        "message": "会话已删除",
    }


@router.patch("/{conversation_id}", response_model=dict)
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdate,
    db: Session = Depends(get_db),
):
    """
    更新会话标题
    """
    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == conversation_id
    ).first()

    if not conversation:
        raise ConversationNotFoundException(conversation_id)

    conversation.title = request.title
    db.commit()

    return {
        "code": 200,
        "data": {
            "conversation_id": conversation_id,
            "title": request.title,
        },
        "message": "标题更新成功",
    }


@router.post("/{conversation_id}/messages", response_model=dict)
async def add_message(
    conversation_id: str,
    request: MessageCreate,
    db: Session = Depends(get_db),
):
    """
    添加消息到会话
    """
    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == conversation_id
    ).first()

    if not conversation:
        raise ConversationNotFoundException(conversation_id)

    role_enum = MessageRole.user if request.role == "user" else MessageRole.assistant

    message = MessageModel(
        conversation_id=conversation_id,
        role=role_enum,
        content=request.content,
        task_id=request.task_id,
    )
    db.add(message)

    conversation.updated_at = conversation.updated_at
    db.commit()
    db.refresh(message)

    return {
        "code": 200,
        "data": {
            "message_id": message.id,
            "conversation_id": conversation_id,
            "role": message.role.value,
            "content": message.content,
            "task_id": message.task_id,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        },
        "message": "消息添加成功",
    }


@router.post("/{conversation_id}/complete", response_model=dict)
async def complete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
):
    """
    标记会话为已完成
    """
    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == conversation_id
    ).first()

    if not conversation:
        raise ConversationNotFoundException(conversation_id)

    conversation.status = ConversationStatus.completed
    db.commit()

    return {
        "code": 200,
        "data": {
            "conversation_id": conversation_id,
            "status": "completed",
        },
        "message": "会话已标记为完成",
    }

@router.get("/{conversation_id}/active_task")
async def get_active_task(conversation_id: str, db: Session = Depends(get_db)):
    # 未使用。查找该会话下最新且未完成/未失败/未取消的任务，可用于恢复当前任务
    task = db.query(TaskModel).join(
        MessageModel, TaskModel.id == MessageModel.task_id
    ).filter(
        MessageModel.conversation_id == conversation_id,
        TaskModel.status.notin_([TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled])
    ).order_by(TaskModel.created_at.desc()).first()
    
    if task:
        return {
            "code": 200,
            "data": {"task_id": task.id, "status": task.status.value},
            "message": "success"
        }
    return {"code": 404, "data": None, "message": "No active task"}