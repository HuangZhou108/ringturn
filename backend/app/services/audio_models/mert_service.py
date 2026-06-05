"""
MERT 音频特征提取服务
"""

import torch
import librosa
import numpy as np
from transformers import AutoModel, Wav2Vec2FeatureExtractor
from pathlib import Path
from typing import Optional, Dict, Any

class MERTService:
    """MERT 模型单例服务，提取音频特征及情绪/风格向量"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_name = "m-a-p/MERT-v1-95M"   # 也可用 330M 版本
        print(f"Loading MERT model {self.model_name} on {self.device}...")
        self.model = AutoModel.from_pretrained(self.model_name, trust_remote_code=True).to(self.device)
        self.processor = Wav2Vec2FeatureExtractor.from_pretrained(self.model_name, trust_remote_code=True)
        self.model.eval()
        self._initialized = True
        print("MERT model loaded.")

    def extract_features(self, audio_path: str, layer_pooling: str = "mean") -> np.ndarray:
        """
        提取 MERT 特征（12 层隐藏状态聚合后的向量）

        Args:
            audio_path: 音频路径
            layer_pooling: 层聚合方式，'mean' 对所有层平均，'last' 只用最后一层，'weighted' 加权

        Returns:
            np.ndarray: 特征向量，维度 (768,) 或 (12*768,)
        """
        waveform, orig_sr = librosa.load(audio_path, sr=None, mono=True)
        target_sr = self.processor.sampling_rate
        if orig_sr != target_sr:
            waveform = librosa.resample(waveform, orig_sr=orig_sr, target_sr=target_sr)

        inputs = self.processor(waveform, sampling_rate=target_sr, return_tensors="pt", padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs, output_hidden_states=True)
            # hidden_states 是一个 tuple，长度为 num_layers+1（包括输入嵌入层）
            # 我们取第2层到第13层（共12层，索引1~12）
            all_hidden = torch.stack(outputs.hidden_states[1:])  # (12, batch, seq_len, hidden_dim)
            # 对时间维度取平均
            time_avg = all_hidden.mean(dim=2)   # (12, batch, hidden_dim)
            # 对 batch 维度 squeeze
            time_avg = time_avg.squeeze(1)      # (12, hidden_dim)

        if layer_pooling == "mean":
            features = time_avg.mean(dim=0).cpu().numpy()   # (hidden_dim,)
        elif layer_pooling == "last":
            features = time_avg[-1].cpu().numpy()
        elif layer_pooling == "concat":
            features = time_avg.flatten().cpu().numpy()     # (12*hidden_dim,)
        else:
            features = time_avg.mean(dim=0).cpu().numpy()

        return features.astype(np.float32)

    def predict_emotion(self, audio_path: str) -> Dict[str, float]:
        """
        使用预置的简单分类器（基于 MERT 特征 + Logistic Regression）预测情绪。
        这里仅演示框架，实际需要训练或加载模型。
        """
        features = self.extract_features(audio_path, layer_pooling="mean")
        # TODO: 加载预先训练好的情绪分类器（例如 sklearn 的 LogisticRegression）
        # 为演示，返回模拟结果
        # 实际使用时，可训练一个简单的 MLP 或使用预训练分类头
        return {
            "happy": 0.7,
            "sad": 0.1,
            "energetic": 0.6,
            "calm": 0.3,
        }


def get_mert() -> MERTService:
    """获取 MERT 服务单例"""
    return MERTService()