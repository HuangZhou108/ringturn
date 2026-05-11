import json
from pathlib import Path
from sqlalchemy.orm import Session
from app.agent.state import AgentState
from app.core.config import get_settings
from app.agent.atomic_tools.rendering.fluidsynth_render import render_midi_with_fluidsynth
from app.agent.atomic_tools.rendering.convert_to_mp3 import convert_wav_to_mp3
from app.agent.atomic_tools.rendering.smart_clip import smart_clip_audio
from app.agent.thinking_utils import record_thought

settings = get_settings()

async def render_node(state: AgentState, db: Session, tools) -> None:
    """
    节点6: 渲染音频

    将改编后的MIDI渲染为音频文件
    """
    midi_path = state.get("arranged_midi_path") or state.get("midi_path")
    if not Path(midi_path).exists():
        raise FileNotFoundError(f"渲染输入 MIDI 不存在: {midi_path}")
    target_duration = state.get("duration", settings.DEFAULT_RINGTONE_DURATION)
    task_id = state["task_id"]
    task_dir = Path(settings.RINGTONES_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    user_filename = state.get("filename", "ringtone")
    # safe_filename = "".join(c for c in user_filename if c.isalnum() or c in "._- ") or task_id
    mp3_path = str(task_dir / f"{user_filename}.mp3")
    wav_path = str(task_dir / "render_temp.wav")
    soundfont = settings.SOUNDFONT_PATH

#     step_tools = [render_midi_with_fluidsynth_tool, convert_wav_to_mp3_tool, smart_clip_audio_tool]
#     system_prompt = f"""将 MIDI 渲染为 MP3 铃声。
# MIDI 路径: {midi_path}
# 音色库: {soundfont}
# 目标长度: {target_duration} 秒
# 输出文件: {mp3_path}

# 工作流：
# 1. 调用 render_midi_with_fluidsynth 生成临时 WAV（路径 {wav_path}，duration_limit={target_duration}）
# 2. 调用 convert_wav_to_mp3 将 WAV 转为 MP3
# 3. **必须调用** smart_clip_audio 将音频截取到 {target_duration} 秒

# **你必须严格遵守以下交互格式：**
# 在每次调用任何工具之前，先输出一句中文说明，格式为：“[思考] 我接下来将使用 <工具名>，因为 <原因>。”
# 然后调用工具。(注意，如果生成长度大于目标长度，一定要使用smart_clip_audio截取)
# 完成所有工具调用后，再单独输出最终的 JSON 结果。
# **绝对不要省略 `[思考]` 行！**

# 示例：
# [思考] 我接下来将使用 render_midi_with_fluidsynth，因为需要将 MIDI 渲染为音频。
# （随后调用 render_midi_with_fluidsynth 工具）
# [思考] 我接下来将使用 convert_wav_to_mp3，因为需要转换为 MP3 格式。
# （随后调用 convert_wav_to_mp3 工具）
# [思考] 我接下来将使用 smart_clip_audio，因为需要截取到目标时长 {target_duration} 秒。
# （随后调用 smart_clip_audio 工具）
# 最终 JSON 结果：
# {{"final_audio_path": "{mp3_path}", "audio_duration": 30.0}}
# """
#     llm = get_llm()
#     callback = ThinkingCallbackHandler(task_id, "render")
#     sub_agent = create_react_agent(llm, step_tools)
#     resp = await sub_agent.ainvoke(
#         {"messages": [SystemMessage(content=system_prompt), HumanMessage(content="渲染音频。")]},
#         config={"callbacks": [callback]}
#     )
#     try:
#         result = json.loads(resp["messages"][-1].content)
#         final_path = result.get("final_audio_path", mp3_path)
#         duration = result.get("audio_duration", target_duration)
#     except:
#         final_path = mp3_path
#         duration = target_duration
    

    # # 验证最终音频文件是否存在
    # if not Path(mp3_path).exists():
    #     raise RuntimeError(f"渲染失败：最终音频文件不存在 {mp3_path}")
    # if Path(mp3_path).stat().st_size == 0:
    #     raise RuntimeError(f"渲染失败：最终音频文件为空 {mp3_path}")
    # state["final_audio_path"] = mp3_path
    # state["audio_duration"] = duration
    # state["final_audio_url"] = f"/static/ringtones/{task_id}/{Path(mp3_path).name}"
    # ---- 步骤1: MIDI → WAV ----
    record_thought(task_id, "render", "开始渲染 MIDI 到 WAV...")
    try:
        await render_midi_with_fluidsynth(
            midi_path=midi_path,
            soundfont_path=soundfont,
            output_wav_path=wav_path,
            sample_rate=44100,
            duration_limit=None,   # 渲染完整时长，后续由 smart_clip 截断
        )
    except Exception as e:
        record_thought(task_id, "render", f"FluidSynth 渲染失败: {e}")
        raise RuntimeError(f"MIDI 渲染出错: {e}")

    if not Path(wav_path).exists() or Path(wav_path).stat().st_size == 0:
        raise RuntimeError("FluidSynth 未生成有效的 WAV 文件")

    # ---- 步骤2: WAV → MP3 ----
    record_thought(task_id, "render", "开始转换 WAV 到 MP3...")
    try:
        await convert_wav_to_mp3(wav_path, mp3_path)
    except Exception as e:
        record_thought(task_id, "render", f"WAV→MP3 转换失败: {e}")
        raise RuntimeError(f"MP3 转换出错: {e}")

    if not Path(mp3_path).exists() or Path(mp3_path).stat().st_size == 0:
        raise RuntimeError("MP3 文件未生成或为空")

    # ---- 步骤3: 智能截取到目标时长 ----
    record_thought(task_id, "render", f"开始截取音频到 {target_duration} 秒...")
    try:
        clipped_path, actual_duration = await smart_clip_audio(
            audio_path=mp3_path,
            target_duration=target_duration,
            mode="auto",
            output_path=mp3_path,   # 直接覆盖
        )
    except Exception as e:
        record_thought(task_id, "render", f"截取失败: {e}")
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
                ffmpeg, "-i", mp3_path,
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

    # ---- 更新状态 ----
    state["final_audio_path"] = mp3_path
    state["audio_duration"] = actual_duration
    state["final_audio_url"] = f"/static/ringtones/{task_id}/{Path(mp3_path).name}"

    record_thought(task_id, "render", f"渲染完成，最终文件: {mp3_path}, 时长: {actual_duration}s")