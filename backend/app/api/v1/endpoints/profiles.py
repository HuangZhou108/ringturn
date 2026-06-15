"""
Profile 管理接口
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Literal
import json
from datetime import datetime

from app.db.session import get_db
from app.models import Profile, Task as TaskModel, ToolPreference, Preference as PreferenceModel
from app.schemas.profile import (
    ProfileCreate,
    ProfileUpdate,
    ProfileResponse,
    ProfileListResponse,
    PreferencesImport,
    PreferencesExport,
)
from app.services.preference_service import (
    get_effective_preference,
    update_profile_preference_stats,
    get_ai_recommendation,
)
from app.schemas.preference import (
    PreferenceGetResponse,
    PreferenceUpdateRequest,
    PreferenceUpdateResponse,
)
from app.core.exceptions import AppException
from app.agent.tool_graphs.analysis_graph import _analysis_graph_cache as analysis_cache
from app.agent.tool_graphs.extract_graph import _extract_graph_cache as extract_cache
from app.agent.tool_graphs.arrange_graph import _arrange_graph_cache as arrange_cache


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

def _clear_profile_cache(profile_id: Optional[int] = None):
    """
    清除 Profile 缓存
    - 若传入 profile_id，仅清除该 Profile 的子图缓存
    - 若不传参数，清除全局配置缓存（如有）
    """
    # 1. 清除指定 Profile 的子图缓存
    if profile_id is not None:
        if profile_id in analysis_cache:
            del analysis_cache[profile_id]
        if profile_id in extract_cache:
            del extract_cache[profile_id]
        if profile_id in arrange_cache:
            del arrange_cache[profile_id]
        # 其他子图缓存同理
    else:
        # 2. 清除全局配置缓存
        from app.core.config import get_settings
        settings = get_settings()
        if hasattr(settings, 'cache') and settings.cache:
            settings.cache.clear()
        # 也可以选择清除所有子图缓存（视业务需求）
        # analysis_cache.clear()
        # extract_cache.clear()
        # arrange_cache.clear()

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
    _clear_profile_cache(profile_id)

    return {
        "code": 200,
        "data": {
            "profile_id": profile.id,
            "name": profile.name,
            "is_active": True,
        },
        "message": f"已切换到 Profile: {profile.name}",
    }


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


# 定义允许的 graph_name
ALLOWED_GRAPH_NAMES = {"analysis", "extract", "arrange", "quality", "render", "reflect"}

# 列名映射
GRAPH_COLUMN_MAP = {
    "analysis": "analysis_graph_config",
    "extract": "extract_graph_config",
    "arrange": "arrange_graph_config",
    "quality": "quality_graph_config",
    "render": "render_graph_config",
    "reflect": "reflect_graph_config",
}


class ToolPreferenceUpdate(BaseModel):
    config: dict  # 完整的图 JSON 对象


@router.put("/{profile_id}/tool-preferences/{graph_name}")
async def update_tool_preference(
    profile_id: int,
    graph_name: str,
    request: ToolPreferenceUpdate,
    db: Session = Depends(get_db),
):
    """保存/更新指定子图的自定义配置"""
    if graph_name not in ALLOWED_GRAPH_NAMES:
        raise HTTPException(status_code=400, detail="Invalid graph_name")
    
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)
    
    # 获取或创建 tool_preference 记录
    pref = db.query(ToolPreference).filter(ToolPreference.profile_id == profile_id).first()
    if not pref:
        pref = ToolPreference(profile_id=profile_id)
        db.add(pref)
    
    # 更新对应列
    column = GRAPH_COLUMN_MAP[graph_name]
    setattr(pref, column, json.dumps(request.config, ensure_ascii=False))
    pref.updated_at = datetime.utcnow()
    db.commit()
    
    _clear_profile_cache(profile_id)
    return {"code": 200, "data": None, "message": f"{graph_name} graph preference saved"}

@router.get("/{profile_id}/tool-preferences/{graph_name}")
async def get_tool_preference(
    profile_id: int,
    graph_name: str,
    db: Session = Depends(get_db),
):
    """获取指定子图的自定义配置（若无则返回 null）"""
    if graph_name not in ALLOWED_GRAPH_NAMES:
        raise HTTPException(status_code=400, detail="Invalid graph_name")
    
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)
    
    pref = db.query(ToolPreference).filter(ToolPreference.profile_id == profile_id).first()
    if not pref:
        return {"code": 200, "data": None, "message": "No custom config, using default"}
    
    column = GRAPH_COLUMN_MAP[graph_name]
    config_json = getattr(pref, column)
    if config_json:
        try:
            config = json.loads(config_json)
            return {"code": 200, "data": config, "message": "success"}
        except json.JSONDecodeError:
            return {"code": 500, "data": None, "message": "Invalid stored config"}
    
    return {"code": 200, "data": None, "message": "No custom config, using default"}


@router.delete("/{profile_id}/tool-preferences/{graph_name}")
async def delete_tool_preference(
    profile_id: int,
    graph_name: str,
    db: Session = Depends(get_db),
):
    """删除自定义配置（恢复默认）"""
    if graph_name not in ALLOWED_GRAPH_NAMES:
        raise HTTPException(status_code=400, detail="Invalid graph_name")
    
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)
    
    pref = db.query(ToolPreference).filter(ToolPreference.profile_id == profile_id).first()
    if not pref:
        return {"code": 200, "data": None, "message": "No custom config to remove"}
    
    column = GRAPH_COLUMN_MAP[graph_name]
    setattr(pref, column, None)
    pref.updated_at = datetime.utcnow()
    db.commit()
    
    return {"code": 200, "data": None, "message": "Custom config removed, will use default"}


# ========== 偏好管理接口 ==========

@router.get("/{profile_id}/preferences")
async def get_profile_preferences(
    profile_id: int,
    db: Session = Depends(get_db),
):
    """
    获取当前有效偏好（含 AI 推荐与用户覆盖）
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)
    
    # 获取或创建 preference 记录
    pref = db.query(PreferenceModel).filter(PreferenceModel.profile_id == profile_id).first()
    if not pref:
        pref = PreferenceModel(
            profile_id=profile_id,
            stats='{"instruments":{},"tempo_samples":{},"duration_samples":{},"style_tags":{}}',
            user_overrides=None
        )
        db.add(pref)
        db.commit()
        db.refresh(pref)
    
    import json
    stats = json.loads(pref.stats)
    user_overrides = json.loads(pref.user_overrides) if pref.user_overrides else None
    
    ai_rec = get_ai_recommendation(stats)
    
    # 构建 user_overrides 结构（若为 None 则使用默认）
    if user_overrides is None:
        user_overrides = {
            "use_ai_preferences": True,
            "instrument": None,
            "tempo": None,
            "duration": None,
            "style_tags": []
        }
    
    # 计算 effective
    effective = {}
    if user_overrides.get("use_ai_preferences", True):
        effective = ai_rec
    else:
        effective = {
            "instrument": user_overrides.get("instrument"),
            "tempo": user_overrides.get("tempo"),
            "duration": user_overrides.get("duration"),
            "style_tags": user_overrides.get("style_tags", [])
        }
    
    return {
        "code": 200,
        "data": {
            "ai_recommendation": ai_rec,
            "user_overrides": user_overrides,
            "effective": effective,
        },
        "message": "获取偏好成功"
    }


@router.put("/{profile_id}/preferences")
async def update_profile_preferences(
    profile_id: int,
    request: PreferenceUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    保存用户覆盖偏好
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)
    
    pref = db.query(PreferenceModel).filter(PreferenceModel.profile_id == profile_id).first()
    if not pref:
        pref = PreferenceModel(
            profile_id=profile_id,
            stats='{"instruments":{},"tempo_samples":{},"duration_samples":{},"style_tags":{}}',
            user_overrides=None
        )
        db.add(pref)
    
    # 加载现有 user_overrides
    import json
    current = json.loads(pref.user_overrides) if pref.user_overrides else {}
    
    # 合并新值
    current["use_ai_preferences"] = request.use_ai_preferences
    if request.instrument is not None:
        current["instrument"] = request.instrument if request.instrument else None
    if request.tempo is not None:
        current["tempo"] = request.tempo
    if request.duration is not None:
        current["duration"] = request.duration
    if request.style_tags is not None:
        current["style_tags"] = request.style_tags if request.style_tags else []
    
    pref.user_overrides = json.dumps(current, ensure_ascii=False)
    pref.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "code": 200,
        "data": None,
        "message": "用户偏好已保存"
    }


@router.delete("/{profile_id}/preferences")
async def reset_profile_preferences(
    profile_id: int,
    db: Session = Depends(get_db),
):
    """
    恢复 AI 推荐偏好（清除用户覆盖）
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise ProfileNotFoundException(profile_id)
    
    pref = db.query(PreferenceModel).filter(PreferenceModel.profile_id == profile_id).first()
    if pref:
        pref.user_overrides = None
        pref.updated_at = datetime.utcnow()
        db.commit()
    
    return {
        "code": 200,
        "data": None,
        "message": "已恢复 AI 推荐偏好，用户覆盖已清除"
    }