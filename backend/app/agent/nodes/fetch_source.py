import asyncio
from pathlib import Path

from app.agent.state import AgentState
from app.services.file_service import file_service
from app.agent.thinking_utils import record_thought
from app.agent.utils import clean_state


def _clip_to_chorus_sync(audio_path: str, output_path: str, target_duration: float) -> tuple[str, float]:
    """
    同步函数：在原曲里找到能量最高的段落（副歌/高潮），截取 target_duration 秒。
    在子线程中执行（避免阻塞事件循环）。
    """
    import librosa
    import numpy as np
    import soundfile as sf

    y, sr = librosa.load(audio_path, sr=None, mono=False)
    if y.ndim == 1:
        y_mono = y
        total_dur = len(y) / sr
    else:
        y_mono = np.mean(y, axis=0)
        total_dur = y.shape[1] / sr

    # 原曲已经很短，无需截取
    if total_dur <= target_duration:
        return audio_path, total_dur

    # 在 25%~75% 区间找能量最高点（避免开头/结尾的静音或淡出）
    rms = librosa.feature.rms(y=y_mono, hop_length=512)[0]
    lo, hi = int(len(rms) * 0.25), int(len(rms) * 0.75)
    if lo >= hi:
        lo, hi = 0, len(rms)
    peak_idx = int(np.argmax(rms[lo:hi])) + lo
    peak_time = float(librosa.times_like(rms, sr=sr, hop_length=512)[peak_idx])

    start = max(0.0, peak_time - target_duration / 2.0)
    end = min(start + target_duration, total_dur)
    start = max(0.0, end - target_duration)  # 保证正好 target_duration 长

    start_sample = int(start * sr)
    end_sample = int(end * sr)
    y_clip = y[:, start_sample:end_sample] if y.ndim > 1 else y[start_sample:end_sample]
    sf.write(output_path, y_clip.T if y.ndim > 1 else y_clip, sr)
    return output_path, end - start


@clean_state
async def fetch_source_node(state: AgentState) -> dict:
    """
    节点1: 获取音频源 + 预截取能量最高段（副歌）

    先在原曲上找到能量最高的段落并截取出来，后续 Demucs 分离 / CREPE 提取
    都只针对这段密集的副歌，而不是整首稀疏的曲子。
    """
    plan = state.get("plan", [])
    if "fetch_source" not in plan:
        return {}

    source_type = state.get("source_type", "upload")
    source_value = state.get("source_value")
    task_id = state["task_id"]

    if source_type == "upload":
        if not source_value:
            raise ValueError("上传类型需要提供source_value（文件ID）")

        file_path = file_service.get_upload_path(source_value)
        if not file_path:
            raise ValueError(f"文件不存在: {source_value}")

        # 尝试加载音频文件，验证是否可读
        try:
            import librosa
            y, sr = librosa.load(str(file_path), duration=1, sr=22050)
            if y is None or len(y) == 0:
                raise RuntimeError("音频文件内容为空")
        except Exception as e:
            raise RuntimeError(f"无法打开或解析上传的音频文件: {e}")

        audio_path = str(file_path)

        # ---- 预截取能量最高段（副歌）----
        try:
            from app.core.config import get_settings
            settings = get_settings()
            duration = state.get("duration", 30)
            clip_len = min(max(duration + 30, 60), 300)  # 副歌 + 上下文，最多 300s
            clip_dir = Path(settings.UPLOADS_DIR) / "pre_clip"
            clip_dir.mkdir(parents=True, exist_ok=True)
            clip_path = str(clip_dir / f"{task_id}_chorus.wav")
            clipped, actual = await asyncio.to_thread(
                _clip_to_chorus_sync, audio_path, clip_path, float(clip_len)
            )
            audio_path = clipped
            record_thought(task_id, "fetch_source", f"已预截取能量最高段（副歌），时长 {actual:.1f}s")
        except Exception as e:
            record_thought(task_id, "fetch_source", f"副歌预截取失败(使用全曲): {e}")

        record_thought(task_id, "fetch_source", f"音频源获取成功: {audio_path}")
        return {"audio_path": audio_path}

    elif source_type == "search":
        raise NotImplementedError("search类型暂未实现")

    else:
        raise ValueError(f"不支持的source_type: {source_type}")
