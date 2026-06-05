#!/usr/bin/env python3
"""下载 YAMNet 模型（支持 TFLite 和 TensorFlow SavedModel）"""
import kagglehub
from pathlib import Path
import shutil
import urllib.request
import zipfile
import io
import sys

# ==================== TFLite 下载 ====================
def download_yamnet_tflite(force_download=False):
    models_dir = Path("./models/yamnet_tflite")
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / "yamnet.tflite"

    if not force_download and model_path.exists():
        return model_path

    # 尝试从 Kaggle 下载
    try:
        print("尝试从 Kaggle 下载 YAMNet TFLite 模型...")
        download_path = kagglehub.model_download("google/yamnet/tfLite/classification-tflite")
        source_file = Path(download_path) / "1.tflite"
        if source_file.exists():
            shutil.copy2(source_file, model_path)
            print("✅ TFLite 模型已从 Kaggle 成功下载。")
            return model_path
        else:
            print("⚠️ 在 Kaggle 下载的目录中未找到 TFLite 模型文件。")
    except Exception as e:
        print(f"⚠️ 从 Kaggle 下载 TFLite 失败: {e}")

    # 尝试从 Hugging Face 下载
    try:
        print("尝试从 Hugging Face 下载 YAMNet TFLite 模型...")
        hf_model_url = "https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/yamnet/releases/v0.50.2/yamnet-tflite-float.zip"
        with urllib.request.urlopen(hf_model_url) as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                tflite_files = [f for f in z.namelist() if f.endswith('.tflite')]
                if tflite_files:
                    with z.open(tflite_files[0]) as source, open(model_path, 'wb') as target:
                        shutil.copyfileobj(source, target)
                    print("✅ TFLite 模型已从 Hugging Face 成功下载。")
                    return model_path
    except Exception as e:
        print(f"⚠️ 从 Hugging Face 下载 TFLite 失败: {e}")

    # 兜底方案：从 Google Storage 下载
    try:
        print("尝试从 Google Storage 下载 YAMNet TFLite 模型...")
        model_url = "https://storage.googleapis.com/mediapipe-models/audio_classifier/yamnet/float32/1/yamnet.tflite"
        urllib.request.urlretrieve(model_url, model_path)
        print("✅ TFLite 模型已从 Google Storage 成功下载。")
        return model_path
    except Exception as e:
        print(f"❌ TFLite 模型下载失败: {e}")
        raise RuntimeError("YAMNet TFLite 模型下载失败。")

# ==================== TensorFlow SavedModel 下载 ====================
def download_yamnet_tf(force_download=False):
    models_dir = Path("./models/yamnet_tf")
    models_dir.mkdir(parents=True, exist_ok=True)

    if not force_download and (models_dir / "saved_model.pb").exists():
        return models_dir

    # 尝试从 Kaggle 下载
    try:
        print("尝试从 Kaggle 下载 YAMNet TensorFlow SavedModel...")
        download_path = kagglehub.model_download("google/yamnet/tensorFlow2/yamnet")
        if (Path(download_path) / "saved_model.pb").exists():
            shutil.copytree(download_path, models_dir, dirs_exist_ok=True)
            print("✅ TensorFlow 模型已从 Kaggle 成功下载。")
            return models_dir
        else:
            print("⚠️ 在 Kaggle 下载的目录中未找到 SavedModel。")
    except Exception as e:
        print(f"⚠️ 从 Kaggle 下载 TensorFlow 模型失败: {e}")

    # 尝试从 TensorFlow Hub 下载
    try:
        import tensorflow_hub as hub
        import tensorflow as tf
        print("尝试从 TensorFlow Hub 下载 YAMNet...")
        hub_model = hub.load("https://tfhub.dev/google/yamnet/1")
        tf.saved_model.save(hub_model, str(models_dir))
        print("✅ TensorFlow 模型已从 Hub 成功下载。")
        return models_dir
    except ImportError:
        print("tensorflow-hub 未安装，跳过 Hub 下载。")
    except Exception as e:
        print(f"⚠️ 从 TensorFlow Hub 下载失败: {e}")

    # 尝试从 Hugging Face 下载
    try:
        print("尝试从 Hugging Face 下载 YAMNet TensorFlow 模型...")
        hf_model_url = "https://huggingface.co/lwd-thefuture/yamnet-tf/resolve/main/saved_model.zip"
        with urllib.request.urlopen(hf_model_url) as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                z.extractall(models_dir)
                print("✅ TensorFlow 模型已从 Hugging Face 成功下载。")
                return models_dir
    except Exception as e:
        print(f"⚠️ 从 Hugging Face 下载 TensorFlow 模型失败: {e}")

    raise RuntimeError("YAMNet TensorFlow SavedModel 下载失败。")

# 统一下载入口
def download_yamnet(backend="auto", force_download=False):
    if backend == "tflite":
        return download_yamnet_tflite(force_download)
    elif backend == "tf":
        return download_yamnet_tf(force_download)
    else:  # auto - 优先 TFLite
        try:
            return download_yamnet_tflite(force_download)
        except Exception as e:
            print(f"TFLite 模型下载失败: {e}，回退到 TensorFlow SavedModel...")
            return download_yamnet_tf(force_download)

if __name__ == "__main__":
    backend = sys.argv[1] if len(sys.argv) > 1 else "auto"
    download_yamnet(backend)