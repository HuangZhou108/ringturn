from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Enum, Text, JSON
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