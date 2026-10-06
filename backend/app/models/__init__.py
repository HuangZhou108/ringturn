from sqlalchemy import (Column, DateTime, Enum, Float, ForeignKey, Index,
                        Integer, JSON, String, Text, UniqueConstraint,
                        create_engine)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import enum

Base = declarative_base()

class ConversationStatus(enum.Enum):
    """会话状态枚举"""
    active = "active"
    completed = "completed"

class MessageRole(enum.Enum):
    """消息角色枚举"""
    user = "user"
    assistant = "assistant"

class TaskStatus(enum.Enum):
    """任务状态枚举"""
    pending = "pending"
    planning = "planning"
    executing = "executing"
    waiting_input = "waiting_input"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"

class HumanInterventionStatus(enum.Enum):
    """人工介入请求状态。"""
    open = "open"
    responded = "responded"
    cancelled = "cancelled"

class Profile(Base):
    """Profile 表（用于多配置切换）"""
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    is_active = Column(Integer, default=0)  # 0=非活跃, 1=活跃
    preferences_data = Column(Text, nullable=True)  # 偏好配置的 JSON 字符串
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    tasks = relationship("Task", back_populates="profile", cascade="all, delete-orphan")
    tool_preference = relationship("ToolPreference", back_populates="profile", uselist=False)
    preference = relationship("Preference", back_populates="profile", uselist=False)

class Task(Base):
    """任务表"""
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True)  # UUID
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=True)  # Profile外键
    parent_task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True)

    # 用户输入
    user_request = Column(Text, nullable=False)
    source_type = Column(String(20), default="upload")  # 'upload', 'link', 'search'
    source_value = Column(String(255))  # 文件ID或链接
    ringtone_params = Column(JSON, nullable=True)  # 铃声参数（instrument, duration, tempo, filename）

    # 任务状态
    status = Column(Enum(TaskStatus), default=TaskStatus.pending, nullable=False)
    current_subtask = Column(String(30))
    subtask_progress = Column(Integer, default=0)

    # Agent 计划
    plan = Column(JSON)  # 执行计划（动作列表）
    current_plan_index = Column(Integer, default=0)

    # LangGraph 关联
    thread_id = Column(String(255))  # LangGraph 线程ID

    # 产出
    final_audio_url = Column(String(500))
    audio_duration = Column(Integer)

    # 思考过程记录
    thinking_process = Column(JSON, nullable=True)  # [{"step": "分析", "content": "...", "timestamp": "..."}]

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 错误信息
    error_message = Column(Text)

    # 关联
    profile = relationship("Profile")
    parent_task = relationship("Task", remote_side=[id], backref="subtasks")
    feedbacks = relationship("Feedback", back_populates="task", cascade="all, delete-orphan")
    conversation_messages = relationship("ConversationMessage", back_populates="task")

    # 反馈处理
    resume_from_node = Column(String(50), nullable=True)   # 反馈任务从哪个节点开始
    intermediate_data = Column(JSON, nullable=True)        # 父任务完成时的中间状态

class Feedback(Base):
    """反馈表"""
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    task = relationship("Task", back_populates="feedbacks")

class TaskExecutionLease(Base):
    """跨进程任务租约，用于防止重复执行并支持崩溃恢复。"""
    __tablename__ = "task_execution_leases"

    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    owner_id = Column(String(128), nullable=False, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    acquired_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    heartbeat_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)

class TaskEvent(Base):
    """可回放的任务事件日志，WebSocket 以自增 ID 作为游标。"""
    __tablename__ = "task_events"
    __table_args__ = (Index("ix_task_events_task_id_id", "task_id", "id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(40), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class HumanIntervention(Base):
    """Agent/操作员发起、用户响应的人工介入记录。"""
    __tablename__ = "human_interventions"

    id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    resume_from_node = Column(String(50), nullable=True)
    status = Column(
        Enum(HumanInterventionStatus),
        nullable=False,
        default=HumanInterventionStatus.open,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)

class KnowledgeDocument(Base):
    """可持久化、可按 Profile 扩展的 RAG 知识文档。"""
    __tablename__ = "knowledge_documents"
    __table_args__ = (Index("ix_knowledge_scope_enabled", "profile_id", "enabled"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_key = Column(String(128), nullable=False, unique=True, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(JSON, nullable=False, default=list)
    source = Column(String(255), nullable=False, default="manual")
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class LongTermMemory(Base):
    """Profile 隔离的长期记忆，支持去重、衰减和来源追踪。"""
    __tablename__ = "long_term_memories"
    __table_args__ = (
        UniqueConstraint("profile_id", "kind", "normalized_hash", name="uq_profile_memory_hash"),
        Index("ix_memory_profile_kind", "profile_id", "kind"),
    )

    id = Column(String(36), primary_key=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(32), nullable=False, default="preference")
    content = Column(Text, nullable=False)
    normalized_hash = Column(String(64), nullable=False)
    source_task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    importance = Column(Float, nullable=False, default=0.5)
    confidence = Column(Float, nullable=False, default=0.7)
    pinned = Column(Integer, nullable=False, default=0)
    memory_metadata = Column("metadata", JSON, nullable=False, default=dict)
    access_count = Column(Integer, nullable=False, default=0)
    last_accessed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class Preference(Base):
    """偏好表：存储每个 Profile 的 AI 统计与用户覆盖配置"""
    __tablename__ = "preferences"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False, unique=True)
    stats = Column(Text, nullable=False)          # AI 统计 JSON
    user_overrides = Column(Text, nullable=True)  # 用户覆盖 JSON
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    profile = relationship("Profile", back_populates="preference")

class Conversation(Base):
    """会话表"""
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True)  # UUID
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    title = Column(String(200))
    status = Column(Enum(ConversationStatus), default=ConversationStatus.active, nullable=False)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    profile = relationship("Profile")
    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan")

class ConversationMessage(Base):
    """会话消息表"""
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    conversation = relationship("Conversation", back_populates="messages")
    task = relationship("Task", back_populates="conversation_messages")

class ToolPreference(Base):
    """工具偏好表"""
    __tablename__ = "tool_preferences"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False, unique=True)
    
    # 各子图的配置 JSON
    analysis_graph_config = Column(Text, nullable=True)
    extract_graph_config = Column(Text, nullable=True)
    arrange_graph_config = Column(Text, nullable=True)
    render_graph_config = Column(Text, nullable=True)
    quality_graph_config = Column(Text, nullable=True)
    reflect_graph_config = Column(Text, nullable=True)
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联
    profile = relationship("Profile", back_populates="tool_preference")
