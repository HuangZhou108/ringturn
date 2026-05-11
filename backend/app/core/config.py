import os
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

class Settings(BaseSettings):
    """应用配置"""
    # 应用基础
    APP_NAME: str = "RingTurn"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # 数据库
    DATABASE_URL: str = "sqlite:///./ringturn.db"

    # LangGraph 检查点存储
    CHECKPOINT_DB_URL: str = "sqlite:///./checkpoints.db"

    # 静态文件
    STATIC_DIR: str = "./static"
    UPLOADS_DIR: str = "./uploads"
    RINGTONES_DIR: str = "./static/ringtones"

    # API
    API_V1_PREFIX: str = "/api/v1"
    BASE_URL: str = "http://localhost:8000"

    # LLM参数 (用于Agent推理)
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4"
    LLM_BASE_URL: str = ""  # 可选，用于自定义API端点

    # 音频分析API
    CHORDMINI_URL: str = "http://localhost:8001"  # ChordMini服务地址
    ESSENTIA_API_URL: str = ""  # Essentia API（如使用）
    BEATLYZE_API_KEY: str = ""  # Beatlyze API Key

    # MIDI生成
    BASIC_PITCH_MODEL_PATH: str = "./models/basic-pitch"  # Basic Pitch模型路径

    # 音频渲染
    FLUIDSYNTH_PATH: str = "fluidsynth"  # FluidSynth可执行文件路径
    SOUNDFONT_PATH: str = "./soundfonts/default.sf2"  # 默认音色库
    FFMPEG_PATH: str = ""  # FFmpeg路径（留空则自动查找）

    # 质量评估
    QUALITY_EVAL_MODEL: str = "utmos"  # utmos / speechmetrics

    # 音频处理
    MAX_AUDIO_SIZE_MB: int = 50  # 最大音频文件大小（MB）
    SUPPORTED_AUDIO_FORMATS: list = ["mp3", "wav"]

    # 任务配置
    DEFAULT_RINGTONE_DURATION: int = 30  # 默认铃声时长（秒）
    MAX_RINGTONE_DURATION: int = 60  # 最大时长

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()

def ensure_directories():
    """确保必要的目录存在"""
    settings = get_settings()
    dirs = [
        settings.STATIC_DIR,
        settings.UPLOADS_DIR,
        settings.RINGTONES_DIR,
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
