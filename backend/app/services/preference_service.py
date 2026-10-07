"""
偏好统计与推荐服务
"""
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models import Task, TaskStatus, Preference
from app.services.llm_service import llm_service


async def update_profile_preference_stats(profile_id: int, task_id: str) -> None:
    """
    在任务成功完成后，更新 Profile 的统计偏好
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or task.status != TaskStatus.completed:
            return
        
        # 获取或创建 preference 记录
        pref = db.query(Preference).filter(Preference.profile_id == profile_id).first()
        if not pref:
            pref = Preference(
                profile_id=profile_id,
                stats='{"instruments":{},"tempo_samples":{},"duration_samples":{},"style_tags":{}}',
                user_overrides=None
            )
            db.add(pref)
            db.commit()
            db.refresh(pref)
        
        stats = json.loads(pref.stats)
        
        # 1. 提取用户显式指定的参数（instrument, tempo, duration）
        params = task.ringtone_params or {}
        instrument = params.get("instrument")
        if instrument and isinstance(instrument, str):
            stats["instruments"][instrument] = stats["instruments"].get(instrument, 0) + 1
        
        tempo = params.get("tempo")
        if tempo and isinstance(tempo, (int, float)):
            tempo_key = int(tempo)
            if "tempo_samples" not in stats:
                stats["tempo_samples"] = {}
            stats["tempo_samples"][tempo_key] = stats["tempo_samples"].get(tempo_key, 0) + 1
        
        duration = params.get("duration")
        if duration and isinstance(duration, (int, float)):
            duration_key = int(duration)
            if "duration_samples" not in stats:
                stats["duration_samples"] = {}
            stats["duration_samples"][duration_key] = stats["duration_samples"].get(duration_key, 0) + 1
        
        # 2. 从 user_request 提取风格/情感
        style_mood = await llm_service.extract_style_and_mood(task.user_request)
        style = style_mood.get("style")
        mood = style_mood.get("mood")
        if style:
            stats["style_tags"][style] = stats["style_tags"].get(style, 0) + 1
        if mood:
            stats["style_tags"][mood] = stats["style_tags"].get(mood, 0) + 1
        
        stats["last_updated"] = datetime.utcnow().isoformat()
        pref.stats = json.dumps(stats, ensure_ascii=False)
        pref.updated_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        print(f"[ERROR] update_profile_preference_stats: {e}")
    finally:
        db.close()
    try:
        from app.services.memory import capture_task_memory

        capture_task_memory(profile_id, task_id)
    except Exception as e:
        print(f"[MEMORY] task capture failed: {type(e).__name__}")


def get_ai_recommendation(stats: Dict[str, Any]) -> Dict[str, Any]:
    """根据统计信息计算 AI 推荐值"""
    # 乐器：出现次数最高的
    instruments = stats.get("instruments", {})
    instrument = max(instruments.items(), key=lambda x: x[1])[0] if instruments else None
    
    # 速度：众数（出现次数最多的 BPM）
    tempo_samples = stats.get("tempo_samples", {})
    tempo = max(tempo_samples.items(), key=lambda x: x[1])[0] if tempo_samples else None
    
    # 时长：众数
    duration_samples = stats.get("duration_samples", {})
    duration = max(duration_samples.items(), key=lambda x: x[1])[0] if duration_samples else None
    
    # 风格标签：取前 3 个高频标签
    style_tags = stats.get("style_tags", {})
    top_styles = sorted(style_tags.items(), key=lambda x: x[1], reverse=True)[:3]
    style_tags_list = [tag for tag, _ in top_styles]
    
    return {
        "instrument": instrument,
        "tempo": tempo,
        "duration": duration,
        "style_tags": style_tags_list
    }


def get_effective_preference(profile_id: int, db: Session) -> Dict[str, Any]:
    """获取当前 profile 的有效偏好（根据 user_overrides 决定）"""
    pref = db.query(Preference).filter(Preference.profile_id == profile_id).first()
    if not pref:
        return {}
    
    import json
    stats = json.loads(pref.stats)
    user_overrides = json.loads(pref.user_overrides) if pref.user_overrides else None
    
    ai_rec = get_ai_recommendation(stats)
    
    if user_overrides and not user_overrides.get("use_ai_preferences", True):
        # 使用用户覆盖
        return {
            "instrument": user_overrides.get("instrument"),
            "tempo": user_overrides.get("tempo"),
            "duration": user_overrides.get("duration"),
            "style_tags": user_overrides.get("style_tags", [])
        }
    else:
        return ai_rec
