# app/agent/atomic_tools/rendering/smart_clip.py
from pathlib import Path
import librosa
import numpy as np
import soundfile as sf
from scipy.signal import find_peaks
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from app.agent.thinking_utils import record_thought

async def smart_clip_audio(
    audio_path: str,
    target_duration: float,
    mode: str = "auto",
    output_path: str | None = None
) -> tuple[str, float]:
    """
    智能截取音频中最精华的片段（默认选择能量最高的区域）。

    Args:
        audio_path: 输入音频路径
        target_duration: 目标时长（秒）
        mode: "auto" (高潮区域), "from_start", "from_middle"
        output_path: 输出路径（默认覆盖原文件）

    Returns:
        tuple: (输出路径, 实际截取后时长)
    """
    if output_path is None:
        output_path = audio_path
    y, sr = librosa.load(audio_path, sr=None, mono=False)
    if y.ndim == 1:
        y_mono = y
    else:
        y_mono = np.mean(y, axis=0)
    duration = y.shape[1] / sr if y.ndim > 1 else len(y) / sr
    
    if duration <= target_duration + 1:
        return output_path, duration
    
    if mode == "auto":
        rms = librosa.feature.rms(y=y_mono, hop_length=512)[0]
        frame_times = librosa.times_like(rms, sr=sr, hop_length=512)
        # 在 25%~75% 区间找最大 RMS 片段
        mid_idx = int(len(rms) * 0.5)
        search_range = slice(int(len(rms)*0.25), int(len(rms)*0.75))
        peak_idx = np.argmax(rms[search_range]) + int(len(rms)*0.25)
        start_time = max(0, frame_times[peak_idx] - target_duration/2)
    elif mode == "from_start":
        start_time = 0
    else:
        start_time = (duration - target_duration) / 2  # 中间
    end_time = min(start_time + target_duration, duration)
    actual_dur = end_time - start_time
    
    start_sample = int(start_time * sr)
    end_sample = int(end_time * sr)
    y_clip = y[:, start_sample:end_sample] if y.ndim > 1 else y[start_sample:end_sample]
    sf.write(output_path, y_clip.T if y.ndim > 1 else y_clip, sr)
    return output_path, actual_dur

class SmartClipInput(BaseModel):
    audio_path: str = Field(description="输入音频文件路径")
    target_duration: float = Field(description="目标时长（秒）")
    mode: str = Field(default="auto", description="截取模式：auto（高潮区）, from_start, from_middle")
    output_path: str | None = Field(default=None, description="输出路径（默认覆盖原文件）")

smart_clip_audio_tool = StructuredTool.from_function(
    coroutine=smart_clip_audio,
    name="smart_clip_audio",
    description="智能截取音频中最精彩的部分（默认选择能量最高的区域）使其达到目标时长。",
    args_schema=SmartClipInput,
)

async def smart_clip_with_analysis(
    audio_path: str,
    target_duration: float,
    user_request: str,
    analysis_result: dict,
    task_id: str,
) -> tuple[str, float]:
    """
    基于用户偏好和音频分析结果，智能截取音频片段。
    若任一步骤失败，自动回退到原有 smart_clip_audio 逻辑。
    返回 (输出路径, 实际时长)。
    """
    from app.agent.atomic_tools.rendering.smart_clip import smart_clip_audio
    from app.services.llm_service import llm_service
    from app.agent.utils import log_tool_call

    async def fallback_clip():
        return await log_tool_call(
            task_id=task_id,
            step_name="render",
            tool_func=smart_clip_audio,
            audio_path=audio_path,
            target_duration=target_duration,
            mode="auto",
            output_path=audio_path,
            tool_name="smart_clip_audio"
        )

    # ---- 尝试智能截取 ----
    try:
        if not user_request or not analysis_result:
            record_thought(task_id, "render", "缺少用户请求或分析结果，回退到自动截取")
            return await fallback_clip()

        clip_preference = await llm_service.extract_clip_preference(user_request)
        # 将分类映射为可读描述
        category_map = {
            1: "能量高（副歌/高潮）",
            2: "特定片段",
            3: "指定时间",
            4: "无偏好（随机选择）"
        }
        category_desc = category_map.get(clip_preference.get("category"), "未知")
        value_info = f" (时间: {clip_preference.get('value')}s)" if clip_preference.get("category") == 3 and clip_preference.get("value") is not None else ""
        record_thought(task_id, "render", f"提取到的截取偏好: {category_desc}{value_info}")

        # 加载音频
        y_full, sr_full = librosa.load(audio_path, sr=None, mono=False)
        if y_full.ndim == 1:
            total_duration = len(y_full) / sr_full
        else:
            total_duration = y_full.shape[1] / sr_full

        if total_duration <= target_duration + 1:
            record_thought(task_id, "render", "音频时长已接近目标，无需截取")
            return audio_path, total_duration

        # 生成候选起始点
        candidates = set()

        boundary_sections = []
        msaf = analysis_result.get("msaf_sections", {})
        if msaf and isinstance(msaf, dict) and msaf.get("sections"):
            boundary_sections = msaf.get("sections", [])
        else:
            sections = analysis_result.get("sections", {})
            if isinstance(sections, dict):
                boundary_sections = sections.get("sections", [])

        for sec in boundary_sections:
            start = sec.get("start")
            end = sec.get("end")
            if start is not None and end is not None and (end - start) >= 10.0:
                if 0 <= start <= total_duration - target_duration:
                    candidates.add(start)

        # 计算 RMS 和局部峰值
        y_mono = y_full if y_full.ndim == 1 else np.mean(y_full, axis=0)
        hop_length = 512
        rms = librosa.feature.rms(y=y_mono, hop_length=hop_length)[0]
        frame_times = librosa.times_like(rms, sr=sr_full, hop_length=hop_length)
        peaks, _ = find_peaks(rms, height=0.1 * np.max(rms), distance=10)
        peak_times = frame_times[peaks]
        valid_peak_times = [t for t in peak_times if 0 <= t <= total_duration - target_duration]

        if len(valid_peak_times) > 3:
            peak_rms = rms[peaks]
            sorted_indices = np.argsort(peak_rms)[::-1]
            top_peak_times = [valid_peak_times[i] for i in sorted_indices[:5]]
        else:
            top_peak_times = valid_peak_times
        candidates.update(top_peak_times)

        candidate_list = [t for t in candidates if 0 <= t <= total_duration - target_duration]
        if not candidate_list:
            record_thought(task_id, "render", "没有有效的候选点，回退到自动截取")
            return await fallback_clip()

        # 计算权重
        weights = []
        # 准备段落边界列表（用于判断候选是否为边界）
        boundary_times = []
        for sec in boundary_sections:
            boundary_times.append(sec.get("start"))
        boundary_times = [t for t in boundary_times if t is not None]

        # 能量峰值候选列表（已经按 RMS 降序排列）
        energy_candidates = top_peak_times

        for t in candidate_list:
            is_boundary = any(abs(t - b) < 0.5 for b in boundary_times)  # 边界候选，阈值0.5秒
            # 判断是否为能量峰值，并确定排名（0,1,2）
            energy_rank = None
            if t in energy_candidates:
                energy_rank = energy_candidates.index(t)  # 0,1,2
            if is_boundary and energy_rank is not None:
                w = 1.2  # 重合权重
            elif is_boundary:
                w = 1.0
            elif energy_rank == 0:
                w = 1.0
            elif energy_rank == 1:
                w = 0.9
            elif energy_rank == 2:
                w = 0.8
            else:
                w = 0.5  # 其他非特殊候选的权重（可调整）
            weights.append(w)

                # 根据分类决定选择方式
        start_time = None
        if clip_preference.get("category") == 1:
            # 选择能量最高的候选
            if energy_candidates:
                start_time = energy_candidates[0]
                record_thought(task_id, "render", f"根据用户偏好（能量高）选择起始点: {start_time:.2f}s")
        elif clip_preference.get("category") == 3:
            # 用户指定了时间
            specified_time = clip_preference.get("value")
            if specified_time is not None and 0 <= specified_time <= total_duration - target_duration:
                start_time = specified_time
                record_thought(task_id, "render", f"根据用户指定时间选择起始点: {start_time:.2f}s")
            else:
                record_thought(task_id, "render", "用户指定时间无效，回退到随机选择")
        # 其他情况（category 2 或 4）走随机

        if start_time is None:
            # 随机选择逻辑
            exp_weights = np.exp(np.array(weights))
            probs = exp_weights / np.sum(exp_weights)
            selected_idx = np.random.choice(len(candidate_list), p=probs)
            start_time = candidate_list[selected_idx]
            record_thought(task_id, "render", f"随机选择起始点: {start_time:.2f}s")

        # 执行截取
        end_time = min(start_time + target_duration, total_duration)
        actual_duration = end_time - start_time
        start_sample = int(start_time * sr_full)
        end_sample = int(end_time * sr_full)
        if y_full.ndim == 1:
            y_clip = y_full[start_sample:end_sample]
        else:
            y_clip = y_full[:, start_sample:end_sample]

        # 保存为临时 WAV，再转 MP3
        wav_clip_path = audio_path + ".clip.wav"
        sf.write(wav_clip_path, y_clip.T if y_clip.ndim > 1 else y_clip, sr_full)
        from app.agent.atomic_tools.rendering.convert_to_mp3 import convert_wav_to_mp3
        await convert_wav_to_mp3(wav_clip_path, audio_path, bitrate="192k")
        Path(wav_clip_path).unlink(missing_ok=True)

        record_thought(task_id, "render", f"截取完成，实际时长: {actual_duration:.2f}s")
        return audio_path, actual_duration

    except Exception as e:
        record_thought(task_id, "render", f"智能截取失败: {e}，回退到自动截取")
        return await fallback_clip()