# app/agent/atomic_tools/analysis/tempo_beats.py
import librosa
import numpy as np
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def detect_tempo_and_beats(audio_path: str) -> dict:
    """
    使用 librosa 检测 BPM、节拍时间点、强拍时间点和节拍号。
    
    强拍检测采用基于 RMS 能量峰值和周期模式分析的方法。
    节拍号通过分析能量序列的自相关周期推断（2、3、4 拍）。
    注意：该方法对于节奏复杂或动态变化剧烈的音乐可能不够准确。
    """
    y, sr = librosa.load(audio_path, sr=22050)
    # BPM
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='time')
    beat_times = beat_frames.tolist() if isinstance(beat_frames, np.ndarray) else []
    
    # 计算每个节拍附近的 RMS 能量（用于强拍识别）
    # 提取 RMS 特征，hop_length=512，帧长 2048
    hop_length = 512
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    
    # 将节拍帧映射到 RMS 帧索引
    beat_rms_indices = (beat_frames * hop_length // hop_length).astype(int)
    beat_rms_indices = np.clip(beat_rms_indices, 0, len(rms) - 1)
    
    # 取每个节拍前后共 3 帧（约 70ms）的 RMS 平均值，避免瞬间噪声
    window = 3
    beat_energies = []
    for idx in beat_rms_indices:
        start = max(0, idx - window)
        end = min(len(rms), idx + window + 1)
        energy = np.mean(rms[start:end])
        beat_energies.append(energy)
    beat_energies = np.array(beat_energies)
    
    # 估计强拍周期（每小节拍数）
    # 方法：计算能量序列的自相关，找到第一个显著峰值的位置（排除零延迟）
    period = 4  # 默认
    if len(beat_energies) > 8:
        # 归一化
        en_norm = (beat_energies - np.mean(beat_energies)) / (np.std(beat_energies) + 1e-8)
        # 自相关
        corr = np.correlate(en_norm, en_norm, mode='full')
        corr = corr[len(corr)//2:]  # 取非负延迟部分
        # 在合理范围内寻找峰值（2-6 拍）
        search_range = slice(2, min(7, len(corr)-1))
        candidate_corr = corr[search_range].copy()
        # 给 lag=4 对应的位置增加权重（因为 4/4 最常见）
        if len(candidate_corr) > 2:  # lag=4 对应索引 2 (因为 slice 起始 2)
            candidate_corr[2] *= 1.2
        if candidate_corr.max() > 0.3:
            period = np.argmax(candidate_corr) + 2
        else:
            period = 4  # 默认 4/4
    else:
        period = 4
    
    # 将周期映射到节拍号（只支持常见拍号）
    time_signature_map = {2: "2/4", 3: "3/4", 4: "4/4", 6: "6/8"}
    time_signature = time_signature_map.get(period, "4/4")
    
    # 5. 强拍检测：在每个周期（period）内，能量最高的拍子作为强拍
    downbeat_indices = []
    for start in range(0, len(beat_energies), period):
        end = min(start + period, len(beat_energies))
        if end - start < 2:
            continue
        # 寻找该段内能量最大的拍子索引（局部峰值）
        segment_energies = beat_energies[start:end]
        peak_local_idx = np.argmax(segment_energies)
        downbeat_index = start + peak_local_idx
        downbeat_indices.append(downbeat_index)
    
    # 去重并排序
    downbeat_indices = sorted(set(downbeat_indices))
    downbeat_times = [beat_times[i] for i in downbeat_indices if i < len(beat_times)]
    

    return {
        "bpm": float(tempo),
        "beat_times": beat_times,
        "downbeat_times": downbeat_times,
        "time_signature": time_signature
    }

class TempoBeatsInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

detect_tempo_beats_tool = StructuredTool.from_function(
    coroutine=detect_tempo_and_beats,
    name="detect_tempo_and_beats",
    description="检测 BPM、节拍时间点、强拍时间点、节拍号",
    args_schema=TempoBeatsInput
)