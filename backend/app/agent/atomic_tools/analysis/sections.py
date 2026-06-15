import librosa
import numpy as np
from scipy.signal import find_peaks
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def detect_sections_tool(audio_path: str) -> dict:
    """
    基于 Chroma 自相似矩阵检测段落边界，返回段落列表和能量曲线。
    """
    y, sr = librosa.load(audio_path, sr=22050)
    hop_length = 512
    # 1. 提取 chroma 特征 (12 维)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    # 2. 计算自相似矩阵 (SSM)
    # 归一化 chroma 向量
    chroma_norm = chroma.T / (np.linalg.norm(chroma.T, axis=1, keepdims=True) + 1e-8)
    ssm = np.dot(chroma_norm, chroma_norm.T)
    # 3. 计算新颖性曲线 (对角线偏移相似度)
    nov = np.zeros(ssm.shape[0])
    for i in range(2, ssm.shape[0] - 2):
        # 比较当前帧与前后帧的相似度变化
        nov[i] = np.mean(np.diag(ssm, k=i))  # 简化，实际使用更复杂的核
    # 4. 能量突变作为补充
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    nov_energy = np.abs(np.diff(rms, prepend=rms[0]))
    # 合并两种新颖性
    novelty = 0.6 * nov + 0.4 * nov_energy
    # 5. 寻找峰值作为边界
    peaks, _ = find_peaks(novelty, prominence=0.1, distance=10)
    frame_times = librosa.frames_to_time(peaks, sr=sr, hop_length=hop_length)
    duration = librosa.get_duration(y=y, sr=sr)
    times = [0.0] + [float(t) for t in frame_times if 0 < t < duration] + [duration]

    # 6. 对每个段落标记简单类型
    sections = []
    for i in range(len(times) - 1):
        start = times[i]
        end = times[i + 1]
        frame_start = librosa.time_to_frames(start, sr=sr, hop_length=hop_length)
        frame_end = librosa.time_to_frames(end, sr=sr, hop_length=hop_length)
        mean_rms = float(np.mean(rms[frame_start:frame_end])) if frame_end > frame_start else 0.5
        if i == 0:
            typ = "intro"
        elif i == len(times) - 2:
            typ = "outro"
        else:
            # 根据能量高低区分 verse/chorus
            typ = "chorus" if mean_rms > 0.3 else "verse"
        sections.append({
            "start": start,
            "end": end,
            "type": typ,
            "energy_level": mean_rms
        })

    return {
        "sections": sections,
        "energy_curve": rms.tolist(),
        "detection_method": "chroma_ssm"
    }

class SectionsInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")

detect_sections_tool = StructuredTool.from_function(
    coroutine=detect_sections_tool,
    name="detect_sections",
    description="检测段落边界、段落类型、能量曲线（基于 chroma 自相似矩阵）",
    args_schema=SectionsInput
)