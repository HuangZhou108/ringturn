"""
Agent 记忆服务

提供两类记忆，并在每次 LLM 调用时自动注入（通过 contextvar）：
1. 全局偏好指令（AGENT.md 式自由文本）：存在 Profile.preferences_data 的 global_instruction 字段
2. 历史使用画像：从 Preference.stats 汇总（常用乐器/速度/时长/风格）
"""
import json
import contextvars

from app.db.session import SessionLocal
from app.models import Profile, Preference


# 当前任务的 Agent 记忆上下文（task-local）
_agent_context = contextvars.ContextVar("agent_context", default=None)


def set_agent_context(ctx: str | None) -> contextvars.Token:
    """设置当前任务的记忆上下文，并返回用于恢复旧值的 token。"""
    return _agent_context.set(ctx)


def reset_agent_context(token: contextvars.Token) -> None:
    """恢复设置前的记忆上下文，防止长生命周期任务串用用户偏好。"""
    _agent_context.reset(token)


def get_agent_context() -> str | None:
    """获取当前任务的记忆上下文。"""
    return _agent_context.get()


def build_agent_context(profile_id: int | None) -> str | None:
    """
    根据 profile 构建注入到 LLM 的上下文文本。
    无任何记忆时返回 None。
    """
    if not profile_id:
        return None

    db = SessionLocal()
    try:
        profile = db.query(Profile).filter(Profile.id == profile_id).first()
        pref = db.query(Preference).filter(Preference.profile_id == profile_id).first()

        parts = []

        # 1. 全局偏好指令（AGENT.md 式）
        global_instruction = None
        if profile and profile.preferences_data:
            try:
                pd = json.loads(profile.preferences_data)
                if isinstance(pd, dict):
                    global_instruction = pd.get("global_instruction") or pd.get("agent_preference")
            except (json.JSONDecodeError, TypeError):
                pass

        # 2. 历史使用画像（从 stats 汇总高频项）
        pref_lines = []
        if pref and pref.stats:
            try:
                stats = json.loads(pref.stats)
                instruments = stats.get("instruments", {})
                tempos = stats.get("tempo_samples", {})
                durations = stats.get("duration_samples", {})
                styles = stats.get("style_tags", {})
                if instruments:
                    top = max(instruments.items(), key=lambda x: x[1])[0]
                    pref_lines.append(f"- 常用乐器: {top}")
                if tempos:
                    top = max(tempos.items(), key=lambda x: x[1])[0]
                    pref_lines.append(f"- 常用速度: {top} BPM")
                if durations:
                    top = max(durations.items(), key=lambda x: x[1])[0]
                    pref_lines.append(f"- 常用时长: {top}s")
                if styles:
                    top_styles = sorted(styles.items(), key=lambda x: x[1], reverse=True)[:3]
                    pref_lines.append(f"- 风格/情绪标签: {', '.join(t for t, _ in top_styles)}")
            except (json.JSONDecodeError, TypeError):
                pass

        if global_instruction:
            parts.append(f"[用户全局偏好指令]\n{global_instruction}")
        if pref_lines:
            parts.append("[用户历史使用偏好]\n" + "\n".join(pref_lines))

        return "\n\n".join(parts) if parts else None
    finally:
        db.close()
