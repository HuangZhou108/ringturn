"""
用户服务模块

提供用户管理、认证和偏好管理功能
"""

import uuid
from typing import Optional
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.models import User, Preference
from app.core.exceptions import UserNotFoundException

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserService:
    """用户服务类"""

    @staticmethod
    def create_user(db: Session, username: str, password: str = None) -> User:
        """
        创建用户

        Args:
            db: 数据库会话
            username: 用户名
            password: 密码（可选，暂未实现密码功能）

        Returns:
            User: 创建的用户对象
        """
        # 检查用户名是否已存在
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            raise ValueError(f"用户名已存在: {username}")

        user = User(username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_user(db: Session, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def get_or_create_default_user(db: Session) -> User:
        """
        获取或创建默认用户

        用于简化开发，提供一个通用用户
        """
        user = db.query(User).filter(User.username == "default").first()
        if not user:
            user = User(username="default")
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def set_preference(
        db: Session,
        user_id: int,
        key: str,
        value: dict
    ) -> Preference:
        """
        设置用户偏好

        Args:
            db: 数据库会话
            user_id: 用户ID
            key: 偏好键（如"disliked_instruments"）
            value: 偏好值（JSON对象）

        Returns:
            Preference: 偏好记录
        """
        # 查找现有偏好
        pref = db.query(Preference).filter(
            Preference.user_id == user_id,
            Preference.key == key
        ).first()

        if pref:
            pref.value = value
        else:
            pref = Preference(
                user_id=user_id,
                key=key,
                value=value,
            )
            db.add(pref)

        db.commit()
        db.refresh(pref)
        return pref

    @staticmethod
    def get_preferences(db: Session, user_id: int) -> dict:
        """
        获取用户所有偏好

        Returns:
            dict: {key: value, ...}
        """
        prefs = db.query(Preference).filter(
            Preference.user_id == user_id
        ).all()
        return {p.key: p.value for p in prefs}

# 全局用户服务实例
user_service = UserService()
