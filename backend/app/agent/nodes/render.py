import json
from pathlib import Path
from sqlalchemy.orm import Session
from app.agent.state import AgentState
from app.core.config import get_settings
from app.agent.atomic_tools.rendering.fluidsynth_render import render_midi_with_fluidsynth
from app.agent.atomic_tools.rendering.convert_to_mp3 import convert_wav_to_mp3
from app.agent.atomic_tools.rendering.smart_clip import smart_clip_audio
from app.agent.thinking_utils import record_thought
from app.agent.utils import log_tool_call
from app.agent.utils import clean_state
from app.agent.atomic_tools.rendering.smart_clip import smart_clip_with_analysis

settings = get_settings()

@clean_state
async def render_node(state: AgentState) -> dict:
    """
    节点6: 渲染音频

    将改编后的MIDI渲染为音频文件
    """
    midi_path = state.get("arranged_midi_path") or state.get("midi_path")
    if not Path(midi_path).exists():
        raise FileNotFoundError(f"渲染输入 MIDI 不存在: {midi_path}")
    target_duration = state.get("duration", settings.DEFAULT_RINGTONE_DURATION)
    # 确保 target_duration 为数值类型
    try:
        target_duration = float(target_duration)
    except (ValueError, TypeError):
        target_duration = float(settings.DEFAULT_RINGTONE_DURATION)
    task_id = state["task_id"]
    task_dir = Path(settings.RINGTONES_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    user_filename = state.get("filename", "ringtone")
    # safe_filename = "".join(c for c in user_filename if c.isalnum() or c in "._- ") or task_id
    mp3_path = str(task_dir / f"{user_filename}.mp3")
    wav_path = str(task_dir / "render_temp.wav")
    soundfont = settings.SOUNDFONT_PATH

    # ---- 步骤1: MIDI → WAV ----
    record_thought(task_id, "render", "开始渲染 MIDI 到 WAV...")
    try:
        await log_tool_call(
            task_id=task_id,
            step_name="render",
            tool_func=render_midi_with_fluidsynth,
            midi_path=midi_path,
            soundfont_path=soundfont,
            output_wav_path=wav_path,
            sample_rate=44100,
            duration_limit=None,
            tool_name="render_midi_with_fluidsynth"
        )
    except Exception as e:
        record_thought(task_id, "render", f"FluidSynth 渲染失败: {e}")
        raise RuntimeError(f"MIDI 渲染出错: {e}")

    if not Path(wav_path).exists() or Path(wav_path).stat().st_size == 0:
        raise RuntimeError("FluidSynth 未生成有效的 WAV 文件")

    # ---- 步骤2: WAV → MP3 ----
    record_thought(task_id, "render", "开始转换 WAV 到 MP3...")
    try:
        await log_tool_call(
            task_id=task_id,
            step_name="render",
            tool_func=convert_wav_to_mp3,
            wav_path=wav_path,
            mp3_path=mp3_path,
            tool_name="convert_wav_to_mp3"
        )
    except Exception as e:
        record_thought(task_id, "render", f"WAV→MP3 转换失败: {e}")
        raise RuntimeError(f"MP3 转换出错: {e}")

    if not Path(mp3_path).exists() or Path(mp3_path).stat().st_size == 0:
        raise RuntimeError("MP3 文件未生成或为空")

    # ---- 步骤3: 智能截取到目标时长 ----
    record_thought(task_id, "render", f"开始截取音频到 {target_duration} 秒...")

    try:
        clipped_path, actual_duration = await smart_clip_with_analysis(
            audio_path=mp3_path,
            target_duration=target_duration,
            user_request=state.get("user_request", ""),
            analysis_result=state.get("analysis_result", {}),
            task_id=task_id,
        )
    except Exception as e:
        record_thought(task_id, "render", f"截取过程异常: {e}")
        raise RuntimeError(f"音频截取出错: {e}")

    # ---- 步骤4: 音量增强（使用 ffmpeg 响度归一化） ----
    record_thought(task_id, "render", "正在调整最终音频音量...")
    try:
        import subprocess
        import shutil
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            record_thought(task_id, "render", "ffmpeg 不可用，跳过音量增强")
        else:
            temp_mp3 = mp3_path + ".tmp.mp3"
            # EBU R128 响度归一化，目标 -16 LUFS，峰值限制 -1.5 dBFS
            cmd = [
                ffmpeg, "-y", "-i", mp3_path,
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:a", "libmp3lame", "-b:a", "192k",
                temp_mp3
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            # 替换原文件
            Path(temp_mp3).replace(mp3_path)
            record_thought(task_id, "render", "音量调整完成（EBU 响度归一化）")
    except Exception as e:
        record_thought(task_id, "render", f"音量增强失败(不影响结果): {e}")
        # 即使增益失败，之前的 mp3 仍然可用（已有截取后的音频）
    record_thought(task_id, "render", f"渲染完成，最终文件: {mp3_path}, 时长: {actual_duration}s")

    final_url = f"/static/ringtones/{task_id}/{Path(mp3_path).name}"

    return {
        "final_audio_path": mp3_path,
        "audio_duration": actual_duration,
        "final_audio_url": final_url,
    }