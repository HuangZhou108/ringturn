"""
MERT 音频特征提取服务
"""

import torch
import librosa
import numpy as np
import os
# from transformers import AutoModel, Wav2Vec2FeatureExtractor
from pathlib import Path
from typing import Optional, Dict, Any

# 定义模型源列表（按优先级排序，可使用环境变量覆盖）
DEFAULT_SOURCES = [
    {
        "name": "modelscope",
        "url": "https://www.modelscope.cn/models/m-a-p/MERT-v1-95M",
        "model_id": "m-a-p/MERT-v1-95M",
        "backend": "modelscope",
        "description": "ModelScope 国内镜像"
    },
    {
        "name": "modelscope_330m",
        "url": "https://www.modelscope.cn/models/m-a-p/MERT-v1-330M",
        "model_id": "m-a-p/MERT-v1-330M",
        "backend": "modelscope",
        "description": "ModelScope 330M 版本"
    },
    {
        "name": "huggingface",
        "url": "https://huggingface.co/m-a-p/MERT-v1-95M",
        "model_id": "m-a-p/MERT-v1-95M",
        "backend": "huggingface",
        "description": "Hugging Face 官方源"
    },
    {
        "name": "local",
        "path": "./models/MERT-v1-95M",
        "backend": "local",
        "description": "本地模型文件夹"
    }
]

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
        self.model = None
        self.processor = None
        
        # 尝试从多个源加载模型
        self._load_model_from_sources()
        
        if self.model is None:
            raise RuntimeError("无法从任何源加载 MERT 模型，请检查网络或手动下载模型到 ./models/ 目录")
        
        self.model.eval()
        self._initialized = True
        print(f"MERT model loaded successfully on {self.device}")
    
    def _load_model_from_sources(self):
        """按顺序尝试从不同源加载模型"""
        from transformers import AutoModel, Wav2Vec2FeatureExtractor
        
        # 获取用户指定的优先源（环境变量）
        preferred_source = os.environ.get("MERT_MODEL_SOURCE", "").lower()
        
        # 重新排序：如果指定了优先源，将其移到最前面
        sources = list(DEFAULT_SOURCES)
        if preferred_source:
            for i, src in enumerate(sources):
                if src["name"] == preferred_source:
                    sources.insert(0, sources.pop(i))
                    break
        
        for source in sources:
            try:
                print(f"尝试从 {source['description']} 加载 MERT 模型...")
                
                if source["backend"] == "modelscope":
                    # ModelScope 加载方式
                    from modelscope.models import Model
                    from modelscope.pipelines import pipeline
                    from modelscope.preprocessors import Preprocessor
                    
                    # 使用 ModelScope 的 AutoModel（与 transformers 兼容）
                    model_id = source["model_id"]
                    # 设置缓存目录
                    cache_dir = os.environ.get("MODELSCOPE_CACHE", "./models/modelscope")
                    
                    self.model = AutoModel.from_pretrained(
                        model_id,
                        trust_remote_code=True,
                        cache_dir=cache_dir,
                        resume_download=True,
                    ).to(self.device)
                    
                    self.processor = Wav2Vec2FeatureExtractor.from_pretrained(
                        model_id,
                        trust_remote_code=True,
                        cache_dir=cache_dir,
                    )
                    
                elif source["backend"] == "huggingface":
                    # 标准 Hugging Face 方式
                    model_id = source["model_id"]
                    # 设置 Hugging Face 镜像（如果环境变量存在）
                    hf_endpoint = os.environ.get("HF_ENDPOINT")
                    if hf_endpoint:
                        print(f"使用 HF_ENDPOINT={hf_endpoint}")
                    
                    self.model = AutoModel.from_pretrained(
                        model_id,
                        trust_remote_code=True,
                        resume_download=True,
                        low_cpu_mem_usage=True,
                    ).to(self.device)
                    
                    self.processor = Wav2Vec2FeatureExtractor.from_pretrained(
                        model_id,
                        trust_remote_code=True,
                    )
                    
                elif source["backend"] == "local":
                    # 本地路径
                    local_path = source["path"]
                    if not Path(local_path).exists():
                        print(f"本地模型路径不存在: {local_path}")
                        continue
                    
                    self.model = AutoModel.from_pretrained(
                        local_path,
                        trust_remote_code=True,
                    ).to(self.device)
                    
                    self.processor = Wav2Vec2FeatureExtractor.from_pretrained(
                        local_path,
                        trust_remote_code=True,
                    )
                
                # 如果成功加载，跳出循环
                if self.model is not None:
                    print(f"成功从 {source['description']} 加载模型")
                    return
                    
            except ImportError as e:
                if source["backend"] == "modelscope":
                    print(f"ModelScope 未安装: {e}。请运行 `pip install modelscope` 以使用该源。")
                else:
                    print(f"从 {source['description']} 加载失败: {e}")
                continue
            except Exception as e:
                print(f"从 {source['description']} 加载失败: {e}")
                continue
        
        # 所有源都失败
        print("所有 MERT 加载源均失败")

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