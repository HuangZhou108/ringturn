"""
音频转换服务

支持音频格式转换、音频处理等功能
"""
import os
import subprocess
from pathlib import Path
from app.core.config import get_settings

settings = get_settings()


class AudioConverter:
    """音频格式转换器"""

    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()

    def _find_ffmpeg(self) -> str | None:
        """查找 FFmpeg 路径"""
        # 1. 检查配置路径
        if settings.FFMPEG_PATH and os.path.exists(settings.FFMPEG_PATH):
            return settings.FFMPEG_PATH

        # 2. 尝试系统 PATH
        import shutil
        path = shutil.which("ffmpeg")
        if path:
            return path

        return None

    def is_available(self) -> bool:
        """检查 FFmpeg 是否可用"""
        return self.ffmpeg_path is not None

    async def convert(
        self,
        input_path: str,
        output_path: str,
        format: str = "mp3",
        bitrate: str = "192k",
        sample_rate: int = 44100,
    ) -> str:
        """
        转换音频格式

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            format: 目标格式 (mp3, wav, flac, etc.)
            bitrate: 比特率 (仅对 mp3/aac 有效)
            sample_rate: 采样率

        Returns:
            str: 输出文件路径
        """
        if not self.is_available():
            # 没有 FFmpeg，直接复制文件（保留原格式）
            print(f"[WARN] FFmpeg 不可用，跳过格式转换: {Path(input_path).suffix} -> {format}")
            return await self._convert_without_ffmpeg(input_path, output_path, format)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path,
            "-y",  # 覆盖输出
            "-i", input_path,
            "-ar", str(sample_rate),
        ]

        if format == "mp3":
            cmd.extend(["-ab", bitrate, "-acodec", "libmp3lame"])
        elif format == "aac":
            cmd.extend(["-ab", bitrate, "-acodec", "aac"])
        elif format == "wav":
            cmd.extend(["-acodec", "pcm_s16le"])
        # flac, ogg 等使用默认编码器

        cmd.append(output_path)

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg 转换失败: {result.stderr}")

        return output_path

    async def _convert_without_ffmpeg(
        self,
        input_path: str,
        output_path: str,
        format: str,
    ) -> str:
        """无 FFmpeg 时的转换（仅支持直接复制）"""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 如果输出是 WAV 且输入是 WAV，直接复制
        if Path(input_path).suffix.lower() == ".wav" and format == "wav":
            import shutil
            shutil.copy(input_path, output_path)
            return output_path

        # 其他情况，创建占位文件并警告
        print(f"[WARN] 非 WAV 到 WAV 转换需要 FFmpeg")
        Path(output_path).touch()
        return output_path

    async def convert_wav_to_mp3(self, wav_path: str, mp3_path: str, bitrate: str = "192k") -> str:
        """WAV 转 MP3 的便捷方法"""
        return await self.convert(wav_path, mp3_path, format="mp3", bitrate=bitrate)

    async def get_duration(self, audio_path: str) -> float | None:
        """获取音频时长（秒）"""
        try:
            if self.is_available():
                cmd = [
                    self.ffmpeg_path,
                    "-i", audio_path,
                    "-f", "null",
                    "-",
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                # 解析时长
                import re
                match = re.search(r"Duration: (\d+):(\d+):(\d+)\.(\d+)", result.stderr)
                if match:
                    h, m, s, ms = match.groups()
                    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 100
            else:
                # 使用 librosa
                import librosa
                return librosa.get_duration(path=audio_path)
        except Exception as e:
            print(f"[WARN] 获取音频时长失败: {e}")
        return None


# 全局实例
audio_converter = AudioConverter()
