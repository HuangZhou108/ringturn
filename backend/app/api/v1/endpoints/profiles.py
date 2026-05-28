"""
Profile 管理接口
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
import json
from datetime import datetime

from app.db.session import get_db
from app.models import Profile, Task as TaskModel
from app.schemas.profile import (
    ProfileCreate,
    ProfileUpdate,
    ProfileResponse,
    ProfileListResponse,
    PreferencesImport,
    PreferencesExport,
)
from app.core.exceptions import AppException

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileNotFoundException(AppException):
    """Profile 不存在异常"""
    def __init__(self, profile_id: int):
        self.status_code = 404
        self.detail = f"Profile {profile_id} 不存在"


def get_or_create_default_profile(db: Session) -> Profile:
    """获取或创建默认 Profile"""
    profile = db.query(Profile).filter(Profile.name == "默认").first()
    if not profile:
        profile = Profile(name="默认", is_active=1)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def ensure_profiles_exist(db: Session) -> None:
    """确保存在至少一个 Profile"""
    count = db.query(Profile).count()
    if count == 0:
        default = Profile(name="default", is_active=1)
        db.add(default)
        db.commit()


@router.post("", response_model=dict)
async def create_profile(
    request: ProfileCreate,
    db: Session = Depends(get_db),
):
    """
    创建新 Profile

    新创建的 Profile 默认为非活跃状态
    """
    try:
        profile = Profile(
            name=request.name,
            is_active=0,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        return {
            "code": 200,
            "data": {
                "profile_id": profile.id,
                "name": profile.name,
                "is_active": bool(profile.is_active),
                "created_at": profile.created_at.isoformat() if profile.created_at else None,
            },
            "message": "Profile 创建成功",
        }
    except Exception as e:
        return {
            "code": 400,
            "data": None,
            "message": f"Profile 创建失败: {str(e)}",
        }


@router.get("", response_model=dict)
async def list_profiles(
    db: Session = Depends(get_db),
):
    """
    获取所有 Profile 列表
    """
    ensure_profiles_exist(db)

    profiles = db.query(Profile).order_by(Profile.created_at.desc()).all()

    return {
        "code": 200,
        "data": [
            {
                "profile_id": p.id,
                "name": p.name,
                "is_active": bool(p.is_active),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in profiles
        ],
        "message": "获取成功",
    }


@router.get("/active", response_model=dict)
async def get_active_profile(
    db: Session = Depends(get_db),
):
    """
    获取当前活跃的 Profile
    """
    ensure_profiles_exist(db)

    profile = db.query(Profile).filter(Profile.is_active == 1).first()
    if not profile:
        # 如果没有活跃的，取第一个
        profile = db.query(Profile).first()
        if profile:
            profile.is_active = 1
            db.commit()
            db.refresh(profile)

    return {
        "code": 200,
        "data": {
            "profile_id": profile.id,
            "name": profile.name,
            "is_active": bool(profile.is_active),
            "preferences_data": profile.preferences_data,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
        },
        "message": "获取成功",
    }


@router.put("/{profile_id}/activate", response_model=dict)
async def activate_profile(
    profile_id: int,
    db: Session = Depends(get_db),
):
    """
    切换活跃 Profile

    将指定 Profile 设为活跃，同时取消其他 Profile 的活跃状态
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)

    # 取消所有 Profile 的活跃状态
    db.query(Profile).update({Profile.is_active: 0})
    db.commit()

    # 设置指定 Profile 为活跃
    profile.is_active = 1
    db.commit()
    db.refresh(profile)

    # 清理缓存（扩展点）
    _clear_profile_cache()

    return {
        "code": 200,
        "data": {
            "profile_id": profile.id,
            "name": profile.name,
            "is_active": True,
        },
        "message": f"已切换到 Profile: {profile.name}",
    }


def _clear_profile_cache():
    """
    清理Profile相关缓存
    
    目前为空实现，未来如果有缓存需求可扩展：
    - LRU缓存清理
    - Redis缓存清理
    - 内存缓存清理
    """
    # 清理config中的LRU缓存（如果有相关配置）
    from app.core.config import get_settings
    if hasattr(get_settings, 'cache'):
        get_settings.cache.clear()
    pass


@router.put("/{profile_id}", response_model=dict)
async def update_profile(
    profile_id: int,
    request: ProfileUpdate,
    db: Session = Depends(get_db),
):
    """
    更新 Profile 名称或偏好配置
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)

    if request.name is not None:
        profile.name = request.name

    if request.preferences_data is not None:
        profile.preferences_data = request.preferences_data

    db.commit()
    db.refresh(profile)

    return {
        "code": 200,
        "data": {
            "profile_id": profile.id,
            "name": profile.name,
            "is_active": bool(profile.is_active),
            "preferences_data": profile.preferences_data,
        },
        "message": "更新成功",
    }


@router.delete("/{profile_id}", response_model=dict)
async def delete_profile(
    profile_id: int,
    db: Session = Depends(get_db),
):
    """
    删除 Profile

    如果删除的是当前活跃 Profile，会自动切换到第一个其他 Profile
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)

    was_active = profile.is_active == 1
    db.delete(profile)
    db.commit()

    # 如果删除的是活跃 Profile，切换到其他 Profile
    if was_active:
        other = db.query(Profile).first()
        if other:
            other.is_active = 1
            db.commit()

    return {
        "code": 200,
        "data": None,
        "message": "Profile 已删除",
    }


@router.get("/{profile_id}/export", response_model=dict)
async def export_preferences(
    profile_id: int,
    db: Session = Depends(get_db),
):
    """
    导出偏好配置

    返回适合在前端使用的 JSON 对象
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)

    preferences = {}
    if profile.preferences_data:
        try:
            preferences = json.loads(profile.preferences_data)
        except json.JSONDecodeError:
            preferences = {}

    return {
        "code": 200,
        "data": {
            "profile_name": profile.name,
            "preferences": preferences,
            "exported_at": datetime.utcnow().isoformat(),
        },
        "message": "导出成功",
    }


@router.post("/{profile_id}/import", response_model=dict)
async def import_preferences(
    profile_id: int,
    request: PreferencesImport,
    db: Session = Depends(get_db),
):
    """
    导入偏好配置

    接收前端传来的偏好对象，存储到后端
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)

    profile.preferences_data = json.dumps(request.preferences, ensure_ascii=False)
    db.commit()
    db.refresh(profile)

    return {
        "code": 200,
        "data": {
            "profile_id": profile.id,
            "preferences": request.preferences,
        },
        "message": "导入成功",
    }


@router.get("/{profile_id}", response_model=dict)
async def get_profile(
    profile_id: int,
    db: Session = Depends(get_db),
):
    """
    获取指定 Profile 详情
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)

    return {
        "code": 200,
        "data": {
            "profile_id": profile.id,
            "name": profile.name,
            "is_active": bool(profile.is_active),
            "preferences_data": profile.preferences_data,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        },
        "message": "获取成功",
    }

@router.get("/{profile_id}/tasks")
async def get_profile_tasks(
    profile_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """获取指定 Profile 的任务列表"""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)

    query = db.query(TaskModel).filter(TaskModel.profile_id == profile_id)
    if status:
        query = query.filter(TaskModel.status == status)
    total = query.count()
    tasks = query.order_by(TaskModel.created_at.desc()) \
                 .offset((page - 1) * page_size) \
                 .limit(page_size) \
                 .all()
    items = [{
        "task_id": t.id,
        "user_request": t.user_request,
        "status": t.status.value,
        "final_audio_url": t.final_audio_url,
        "audio_duration": t.audio_duration,
        "created_at": t.created_at.isoformat(),
    } for t in tasks]
    return {
        "code": 200,
        "data": {"total": total, "page": page, "page_size": page_size, "tasks": items},
        "message": "success"
    }