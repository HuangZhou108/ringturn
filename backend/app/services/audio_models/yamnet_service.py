import numpy as np
import librosa
from pathlib import Path
import urllib.request
import tensorflow as tf
from app.services.audio_models.download_yamnet import download_yamnet

class YAMNetService:
    _instance = None
    _labels = None          # 类级缓存标签

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def _load_labels(self):
        """从官方 CSV 加载标签列表（只执行一次，结果缓存到类变量）"""
        if YAMNetService._labels is not None:
            return YAMNetService._labels

        label_url = "https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv?raw=true"
        try:
            with urllib.request.urlopen(label_url) as response:
                content = response.read().decode('utf-8')
                lines = content.strip().splitlines()
            # 解析 CSV，跳过标题行
            labels = []
            for line in lines:
                if not line.strip() or line.startswith('index'):
                    continue
                parts = line.split(',')
                if len(parts) >= 3:
                    label = parts[2].strip().strip('"')
                    labels.append(label)
            YAMNetService._labels = labels
            print(f"[YAMNet] Loaded {len(labels)} labels from GitHub.")
            return labels
        except Exception as e:
            print(f"[YAMNet] Failed to load labels from GitHub: {e}")
            # 降级：返回占位标签
            fallback = [f"unknown_{i}" for i in range(521)]
            YAMNetService._labels = fallback
            return fallback

    def load(self):
        if self._initialized:
            return
        
        # 提前加载标签（确保后续使用）
        self.labels = self._load_labels()

        # 优先尝试加载 TFLite（轻量、部署方便）
        try:
            self._load_tflite_model()
            self._initialized = True
            print("[YAMNet] Loaded TFLite backend (preferred).")
            return
        except Exception as e:
            print(f"[YAMNet] Failed to load TFLite model: {e}, falling back to TensorFlow SavedModel.")

        # 回退到 TensorFlow SavedModel
        tf_available = self._check_tf_available()
        if tf_available:
            try:
                self._load_tf_model()
                self._initialized = True
                print("[YAMNet] Loaded TensorFlow SavedModel backend (fallback).")
                return
            except Exception as e:
                print(f"[YAMNet] Failed to load TF model: {e}")
        else:
            print("[YAMNet] TensorFlow not available, cannot load any model.")
            raise RuntimeError("No YAMNet backend available (TFLite failed, TensorFlow not installed)")

    
    def _check_tf_available(self):
        try:
            import tensorflow as tf
            return True
        except ImportError:
            return False

    def _load_tf_model(self):
        # 下载或定位 SavedModel 目录
        model_dir = download_yamnet(backend="tf", force_download=False)
        self.model = tf.saved_model.load(str(model_dir))
        self.infer = self.model.signatures['serving_default']
        self.backend = "tf"

    def _load_tflite_model(self):
        model_path = download_yamnet(backend="tflite", force_download=False)
        self.interpreter = tf.lite.Interpreter(model_path=str(model_path))
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()[0]
        self.output_details = self.interpreter.get_output_details()[0]
        self.backend = "tflite"

    def predict(self, audio_path: str, sample_rate: int = 16000) -> np.ndarray:
        """返回 (521,) 的得分数组（对整个音频滑动窗口取平均）"""
        self.load()
        waveform, _ = librosa.load(audio_path, sr=sample_rate, mono=True)
        target_len = 15600       # 模型需要的固定长度（约 0.975 秒）
        hop_length = target_len // 2   # 50% 重叠，可根据需要调整（若性能紧张可设为 target_len）
        
        scores_list = []
        for start in range(0, len(waveform), hop_length):
            segment = waveform[start:start+target_len]
            if len(segment) < target_len:
                # 最后一段不足时补零
                segment = np.pad(segment, (0, target_len - len(segment)), mode='constant')
            # 准备输入张量
            if self.backend == "tf":
                input_tensor = np.expand_dims(segment, axis=0).astype(np.float32)
                outputs = self.infer(inputs=input_tensor)
                scores = outputs['scores'].numpy()[0]   # shape (521,)
            else:  # tflite
                # 根据模型期望的形状决定是否增加 batch 维度
                input_shape = self.input_details['shape']
                if len(input_shape) == 1:
                    # 期望 (15600,)
                    input_tensor = segment.astype(np.float32)
                else:
                    # 期望 (1, 15600)
                    input_tensor = np.expand_dims(segment, axis=0).astype(np.float32)
                self.interpreter.set_tensor(self.input_details['index'], input_tensor)
                self.interpreter.invoke()
                scores = self.interpreter.get_tensor(self.output_details['index'])[0]
            scores_list.append(scores)
        
        if not scores_list:
            return np.zeros(521, dtype=np.float32)
        
        # 对所有窗口的分数取平均
        avg_scores = np.mean(scores_list, axis=0)
        return avg_scores

def get_yamnet():
    return YAMNetService()