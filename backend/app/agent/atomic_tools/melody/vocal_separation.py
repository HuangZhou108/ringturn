import subprocess
import shutil
from pathlib import Path
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

async def separate_vocals(audio_path: str, output_dir: str | None = None) -> str:
    """
    使用Demucs将音频的人声部分分离出来。
    """
    if not shutil.which("demucs"):
        raise RuntimeError("demucs not found. Please install it with `pip install demucs`")
    
    if output_dir is None:
        # 默认输出到系统临时目录
        output_dir = str(Path(audio_path).parent / "demucs_output")
    
    # 调用Demucs命令行工具，使用htdemucs模型，分离人声
    cmd = [
        "demucs",
        "--two-stems", "vocals", # 只分离人声vocals和伴奏no_vocals
        "-o", output_dir,
        audio_path
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Demucs failed: {e.stderr}")
    
    # 构造分离后的音频文件路径
    stem_name = Path(audio_path).stem
    # Demucs会默认把输出放在 output_dir/htdemucs/ 目录下
    vocals_path = str(Path(output_dir) / "htdemucs" / stem_name / "vocals.wav")
    if not Path(vocals_path).exists():
        raise FileNotFoundError(f"Vocals file not found: {vocals_path}")
        
    return vocals_path

class SeparateVocalsInput(BaseModel):
    audio_path: str = Field(description="输入音频文件的绝对路径")
    output_dir: str | None = Field(default=None, description="输出目录的绝对路径（可选）")

separate_vocals_tool = StructuredTool.from_function(
    coroutine=separate_vocals,
    name="separate_vocals",
    description="使用Demucs分离音频中的人声，返回人声轨道的路径。",
    args_schema=SeparateVocalsInput,
)