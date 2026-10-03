"""旋律提取与和声分析的音频源选择策略。"""

from pathlib import Path
from typing import TypedDict


class MelodySourceSelection(TypedDict):
    """一次源选择的结果。"""

    melody_source_path: str
    harmony_source_path: str
    reason: str


def _existing_file(path: str | None) -> str | None:
    """返回已落盘的普通文件路径，过滤过期的 Demucs 路径。"""
    if not path:
        return None
    try:
        return path if Path(path).is_file() else None
    except (OSError, TypeError, ValueError):
        return None


def select_melody_sources(
    *,
    original_audio_path: str | None,
    vocals_path: str | None,
    accompaniment_path: str | None,
    demucs_separated: bool,
) -> MelodySourceSelection:
    """
    选择主旋律提取源和和声上下文源。

    有效的人声分离结果优先用于主旋律提取；伴奏轨只用于和声上下文。
    若人声轨不可用，则保持原音频时间轴并回退到原音频。只有原音频
    已丢失时，才把伴奏轨作为最后的可用旋律输入。
    """
    original_file = _existing_file(original_audio_path)
    vocals_file = _existing_file(vocals_path) if demucs_separated else None
    accompaniment_file = _existing_file(accompaniment_path) if demucs_separated else None

    if vocals_file:
        melody_source_path = vocals_file
        reason = "demucs_vocals"
    elif original_file:
        melody_source_path = original_file
        reason = "original_audio_fallback" if demucs_separated else "original_audio"
    elif accompaniment_file:
        melody_source_path = accompaniment_file
        reason = "accompaniment_last_resort"
    else:
        raise ValueError("没有可用的旋律提取音频：原音频和有效的 Demucs 输出均不存在")

    if accompaniment_file:
        harmony_source_path = accompaniment_file
    elif original_file:
        harmony_source_path = original_file
    else:
        harmony_source_path = melody_source_path

    return {
        "melody_source_path": melody_source_path,
        "harmony_source_path": harmony_source_path,
        "reason": reason,
    }
