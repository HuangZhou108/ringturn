from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Enum, Text, JSON
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import enum

Base = declarative_base()

class TaskStatus(enum.Enum):
    """任务状态枚举"""
    pending = "pending"
    planning = "planning"
    executing = "executing"
    waiting_input = "waiting_input"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("Preference", back_populates="user", cascade="all, delete-orphan")

class Task(Base):
    """任务表"""
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
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
    user = relationship("User", back_populates="tasks")
    parent_task = relationship("Task", remote_side=[id], backref="subtasks")
    feedbacks = relationship("Feedback", back_populates="task", cascade="all, delete-orphan")

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
    """用户偏好表"""
    __tablename__ = "preferences"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key = Column(String(64), nullable=False)
    value = Column(JSON, nullable=False)  # 如 ["cello"] 或 {"bpm": 120}

    # 关联
    user = relationship("User", back_populates="preferences")
