"""
Agent工具调用网关

封装外部API和工具调用，包括：
- 音频分析工具
- MIDI生成工具
- 乐器改编工具
- 音频渲染工具
- 质量评估工具
"""

import os
import httpx
import numpy as np
from app.core.config import get_settings
from app.services.llm_service import llm_service


settings = get_settings()


class ToolGateway:
    """
    工具调用网关

    统一封装外部API，支持Mock与真实切换
    """

    def __init__(self):
        # API URLs
        self.chordmini_url = settings.CHORDMINI_URL
        self.essentia_url = settings.ESSENTIA_API_URL

        # 本地模型路径
        self.basic_pitch_model_path = settings.BASIC_PITCH_MODEL_PATH
        self.fluidsynth_path = settings.FLUIDSYNTH_PATH
        self.soundfont_path = settings.SOUNDFONT_PATH

    # async def analyze_audio_structure(self, audio_path: str) -> dict:
    #     """
    #     分析音频结构

    #     优先级：ChordMini API > librosa本地分析 > Mock
    #     """
    #     # 1. 尝试 ChordMini API
    #     if self.chordmini_url and self.chordmini_url != "http://localhost:8001":
    #         try:
    #             return await self._call_chordmini(audio_path)
    #         except Exception as e:
    #             print(f"[WARN] ChordMini调用失败: {e}")

    #     # 2. 尝试 librosa 本地分析
    #     try:
    #         return await self._analyze_with_librosa(audio_path)
    #     except Exception as e:
    #         # print(f"[WARN] librosa分析失败: {e}")
    #         raise RuntimeError(f"音频结构分析失败（librosa 不可用或处理出错）: {e}")

    #     # 3. 降级到 Mock
    #     # return {
    #     #     "bpm": 120,
    #     #     "key": "C",
    #     #     "time_signature": "4/4",
    #     #     "sections": [
    #     #         {"start": 0.0, "end": 10.0, "type": "intro"},
    #     #         {"start": 10.0, "end": 30.0, "type": "verse"},
    #     #         {"start": 30.0, "end": 50.0, "type": "chorus"},
    #     #     ],
    #     #     "chords": [
    #     #         {"start": 0.0, "end": 4.0, "chord": "C"},
    #     #         {"start": 4.0, "end": 8.0, "chord": "G"},
    #     #     ],
    #     #     "instruments": ["vocals", "guitar", "bass", "drums"],
    #     # }

    async def _analyze_with_librosa(self, audio_path: str) -> dict:
        """使用 librosa 本地分析音频结构"""
        import librosa
        import numpy as np

        # 加载音频
        y, sr = librosa.load(audio_path, sr=22050)

        # 1. BPM 检测
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo) if tempo else 120

        # 2. 调性分析（简化的方式：使用音高分析）
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = np.mean(chroma, axis=1)
        note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        key_idx = int(np.argmax(chroma_mean))
        key = note_names[key_idx] + " Major"

        # 3. 段落检测（基于能量变化）
        rms = librosa.feature.rms(y=y)[0]
        frame_times = librosa.times_like(rms, sr=sr)

        # 简化段落划分：每15秒一段
        duration = librosa.get_duration(y=y, sr=sr)
        sections = []
        current = 0.0
        section_types = ["intro", "verse", "chorus", "outro"]
        for i, t in enumerate(section_types):
            if current >= duration:
                break
            next_t = min(current + duration / 4, duration)
            sections.append({
                "start": float(current),
                "end": float(next_t),
                "type": t
            })
            current = next_t

        # 4. 和弦进行（简化：使用主和弦循环）
        chord_progression = ["C", "G", "Am", "F"]  # 流行歌常见进行
        chords = []
        chord_duration = duration / len(chord_progression)
        for i, chord in enumerate(chord_progression):
            start = i * chord_duration
            if start >= duration:
                break
            chords.append({
                "start": float(start),
                "end": float(min((i + 1) * chord_duration, duration)),
                "chord": chord
            })

        return {
            "bpm": bpm,
            "key": key,
            "time_signature": "4/4",
            "sections": sections,
            "chords": chords,
            "instruments": self._detect_instruments(y, sr),
            "duration": duration,
        }

    def _detect_instruments(self, y, sr) -> list[str]:
        """简单的声音特征检测"""
        instruments = []
        try:
            import librosa

            # 使用频谱特征粗略判断
            spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
            mean_centroid = float(np.mean(spectral_centroid))

            # 简单的启发式判断
            if mean_centroid < 500:
                instruments.extend(["bass", "drums"])
            if mean_centroid > 1000:
                instruments.append("guitar")
            if mean_centroid > 2000:
                instruments.append("vocals")

            if not instruments:
                instruments = ["piano", "drums"]
        except:
            instruments = ["vocals", "guitar", "bass", "drums"]

        return list(set(instruments))

    async def _call_chordmini(self, audio_path: str) -> dict:
        """
        调用ChordMini API

        参考：https://github.com/spotify/chord-mini
        自托管服务，免费使用
        """
        async with httpx.AsyncClient() as client:
            with open(audio_path, "rb") as f:
                files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
                response = await client.post(
                    f"{self.chordmini_url}/analyze",
                    files=files,
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()

    # async def extract_melody(self, audio_path: str) -> dict:
    #     """
    #     提取主旋律

    #     使用Basic Pitch（Spotify开源）提取旋律

    #     Args:
    #         audio_path: 音频文件路径

    #     Returns:
    #         dict: 旋律数据
    #     """
    #     try:
    #         from basic_pitch.inference import predict
    #         from pathlib import Path

    #         # Basic Pitch 使用默认 TensorFlow 模型
    #         (
    #             model_output,
    #             midi_data,
    #             note_events,
    #         ) = predict(
    #             audio_path=str(audio_path),
    #             onset_threshold=0.5,
    #             frame_threshold=0.3,
    #             minimum_note_length=127.7,
    #         )

    #         melody_notes = []
    #         for start, end, pitch, velocity, _ in note_events:
    #             melody_notes.append({
    #                 "pitch": pitch,
    #                 "start": start,
    #                 "end": end,
    #                 "velocity": int(velocity * 127) if velocity else 80,
    #                 "confidence": velocity or 0.8,
    #             })

    #         # 保存MIDI到临时位置
    #         output_dir = Path(audio_path).parent / "midi_output"
    #         output_dir.mkdir(parents=True, exist_ok=True)
    #         midi_output_path = str(output_dir / f"{Path(audio_path).stem}_melody.mid")
    #         midi_data.write(midi_output_path)

    #         return {
    #             "melody_notes": melody_notes,
    #             "confidence": float(model_output.get("average_note_confidence", 0.8)) if model_output else 0.8,
    #             "midi_path": midi_output_path,
    #         }
    #     except ImportError as e:
    #         # print(f"[WARN] Basic Pitch未安装: {e}")
    #         # return self._mock_melody()
    #         raise RuntimeError(f"Basic Pitch 未安装，无法提取旋律: {e}")
    #     except Exception as e:
    #         # print(f"[WARN] Basic Pitch调用失败: {e}")
    #         # return self._mock_melody()
    #         raise RuntimeError(f"Basic Pitch 调用失败: {e}")

    def _mock_melody(self) -> dict:
        """返回模拟旋律数据"""
        return {
            "melody_notes": [
                {"pitch": 60, "start": 0.0, "end": 0.5, "velocity": 80, "confidence": 0.5},
                {"pitch": 62, "start": 0.5, "end": 1.0, "velocity": 75, "confidence": 0.5},
            ],
            "confidence": 0.5,
        }

    # async def generate_midi(
    #     self,
    #     melody_data: dict,
    #     analysis_result: dict,
    #     output_path: str
    # ) -> str:
    #     """生成MIDI文件，优先使用Basic Pitch直接生成的MIDI"""
    #     # 优先使用Basic Pitch直接生成的MIDI
    #     if melody_data.get("midi_path") and os.path.exists(melody_data["midi_path"]):
    #         Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    #         shutil.copy(melody_data["midi_path"], output_path)
    #         return output_path

    #     # 否则用mido库手动构建
    #     try:
    #         import mido

    #         mid = mido.MidiFile()
    #         mid.ticks_per_beat = 480
    #         track = mido.MidiTrack()
    #         mid.tracks.append(track)

    #         track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(analysis_result.get("bpm", 120)), time=0))

    #         last_time = 0
    #         for note in melody_data.get("melody_notes", []):
    #             start_ticks = int(note["start"] * mid.ticks_per_beat * 4)
    #             duration_ticks = int((note["end"] - note["start"]) * mid.ticks_per_beat * 4)
    #             pitch = int(note["pitch"])
    #             velocity = int(note.get("velocity", 80))

    #             wait_ticks = max(0, start_ticks - last_time)
    #             track.append(mido.Message("note_on", channel=0, note=pitch, velocity=velocity, time=wait_ticks))
    #             track.append(mido.Message("note_off", channel=0, note=pitch, velocity=0, time=duration_ticks))
    #             last_time = start_ticks + duration_ticks

    #         Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    #         mid.save(output_path)
    #         return output_path

    #     except Exception as e:
    #         print(f"[WARN] MIDI生成失败: {e}，创建占位文件")
    #         Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    #         Path(output_path).touch()
    #         return output_path

    # async def arrange_instrument(
    #     self,
    #     midi_path: str,
    #     target_instruments: list[str],
    #     style: str,
    #     output_path: str
    # ) -> str:
    #     """
    #     乐器改编

    #     根据用户需求更换乐器
    #     """
    #     from app.services.midi_arranger import arrange_midi

    #     arranged_path = await arrange_midi(
    #         midi_path,
    #         target_instruments,
    #         style,
    #     )

    #     # 复制到目标位置
    #     Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    #     import shutil
    #     shutil.copy(arranged_path, output_path)
    #     return output_path

    # async def render_audio(
    #     self,
    #     midi_path: str,
    #     instruments: dict[str, str],
    #     output_path: str,
    #     duration: float = 30.0
    # ) -> str:
    #     """使用FluidSynth将MIDI渲染为音频，并转换为MP3"""
    #     fs_path = self.fluidsynth_path
    #     sf2_path = self.soundfont_path

    #     if instruments:
    #         sf2_path = next(iter(instruments.values()), sf2_path)

    #     # fallback: 找不到就用本地 soundfonts 目录下的音色库
    #     if not os.path.exists(fs_path):
    #         fs_path = shutil.which("fluidsynth") or ""
    #     if not os.path.exists(sf2_path):
    #         local_sf = Path(__file__).parent.parent.parent / "soundfonts" / "default.sf2"
    #         if local_sf.exists():
    #             sf2_path = str(local_sf)

    #     if not os.path.exists(fs_path):
    #         print(f"[WARN] FluidSynth未找到: {fs_path}，跳过渲染")
    #         Path(output_path).touch()
    #         return output_path
    #     if not os.path.exists(sf2_path):
    #         print(f"[WARN] 音色库未找到: {sf2_path}，跳过渲染")
    #         Path(output_path).touch()
    #         return output_path

    #     # 临时WAV文件
    #     wav_path = output_path.replace(".mp3", ".wav")
    #     Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    #     # FluidSynth 渲染到 WAV
    #     # 使用 -d 参数限制渲染时长（秒）
    #     cmd = [
    #         fs_path,
    #         "-ni",
    #         "-F", wav_path,
    #         "-r", "44100",
    #         "-d", str(int(duration)),
    #         sf2_path,
    #         midi_path,
    #     ]

    #     result = subprocess.run(cmd, capture_output=True, text=True)
    #     if result.returncode != 0:
    #         print(f"[WARN] FluidSynth渲染失败: {result.stderr}")
    #         Path(output_path).touch()
    #         return output_path

    #     # 转换 WAV 到 MP3
    #     from app.services.audio_converter import audio_converter

    #     if Path(wav_path).exists():
    #         await audio_converter.convert_wav_to_mp3(wav_path, output_path)
    #         # 删除临时 WAV
    #         os.remove(wav_path)

    #     return output_path

    # async def check_quality(
    #     self,
    #     audio_path: str,
    #     reference_path: str | None = None
    # ) -> dict:
    #     """评估音频质量"""
    #     from app.services.quality_evaluator import evaluate_quality

    #     return await evaluate_quality(audio_path, reference_path)

    # async def smart_clip(
    #     self,
    #     audio_path: str,
    #     target_duration: float = 30.0,
    #     mode: str = "auto"
    # ) -> tuple[str, float]:
    #     """
    #     智能截取最佳片段

    #     Args:
    #         audio_path: 音频路径
    #         target_duration: 目标时长
    #         mode: 截取模式（auto/highlight/fade_out）

    #     Returns:
    #         tuple: (截取后的音频路径, 实际时长)
    #     """
    #     print(f"[DEBUG] smart_clip called: path={audio_path}, target_duration={target_duration}")

    #     if not os.path.exists(audio_path):
    #         print(f"[WARN] Audio file not found: {audio_path}")
    #         return audio_path, target_duration

    #     try:
    #         import librosa
    #         import soundfile as sf

    #         # 获取实际音频时长
    #         y, sr = librosa.load(audio_path, sr=None, mono=False)
    #         if y.ndim == 1:
    #             actual_duration = len(y) / sr
    #         else:
    #             actual_duration = y.shape[1] / sr

    #         print(f"[DEBUG] Actual audio duration: {actual_duration}s, target: {target_duration}s")

    #         # 如果实际时长已经接近目标时长（或更短），直接返回
    #         if actual_duration <= target_duration + 1:
    #             print(f"[DEBUG] Audio is short enough, returning as-is")
    #             return audio_path, round(actual_duration, 1)

    #         # 计算需要截取的位置
    #         if mode == "auto" or mode == "highlight":
    #             # 找到能量最大的位置作为截取起点（通常是高潮部分）
    #             y_mono = y if y.ndim == 1 else np.mean(y, axis=0)
    #             hop_length = 512
    #             rms = librosa.feature.rms(y=y_mono, hop_length=hop_length)[0]
    #             frame_times = librosa.times_like(rms, sr=sr, hop_length=hop_length)

    #             # 在中间区域找能量最大的点
    #             mid_start = int(len(rms) * 0.25)
    #             mid_end = int(len(rms) * 0.75)
    #             mid_rms = rms[mid_start:mid_end]
    #             peak_idx = np.argmax(mid_rms) + mid_start
    #             peak_time = frame_times[peak_idx]

    #             # 确保截取后不会超出音频长度
    #             start_time = min(peak_time, max(0, actual_duration - target_duration))
    #         elif mode == "fade_out":
    #             # 从开头截取
    #             start_time = 0
    #         else:
    #             start_time = 0

    #         # 计算结束时间
    #         end_time = min(start_time + target_duration, actual_duration)
    #         actual_clip_duration = end_time - start_time

    #         # 截取音频
    #         start_sample = int(start_time * sr)
    #         end_sample = int(end_time * sr)
    #         y_clipped = y[:, start_sample:end_sample] if y.ndim > 1 else y[start_sample:end_sample]

    #         # 直接覆盖原文件，使用用户指定的文件名
    #         clipped_path = audio_path

    #         # 保存截取后的音频（直接覆盖原文件）
    #         sf.write(clipped_path, y_clipped.T if y.ndim > 1 else y_clipped, sr)
    #         print(f"[DEBUG] Saved clipped audio to: {clipped_path}")

    #         return clipped_path, round(actual_clip_duration, 1)

    #     except Exception as e:
    #         print(f"[ERROR] smart_clip failed: {e}")
    #         # 出错时返回原始路径
    #         return audio_path, target_duration

    async def parse_user_request(self, user_request: str) -> dict:
        """
        解析用户自然语言请求

        Args:
            user_request: 用户原始请求

        Returns:
            dict: 解析后的参数
        """
        # 调用LLM服务解析
        return await llm_service.parse_user_request(user_request)
    
    # 在开始执行前确定Agent规划的工具可用。
    async def ensure_tool_available(self, tool_name: str) -> None:
        """
        确保指定工具可用，不可用时抛出异常
        支持的 tool_name: 'librosa', 'basic_pitch', 'fluidsynth', 'soundfont', 'chordmini'
        """
        if tool_name == 'librosa':
            try:
                import librosa
            except ImportError:
                raise RuntimeError("librosa 未安装，无法进行音频结构分析")
        elif tool_name == 'basic_pitch':
            try:
                from basic_pitch.inference import predict
            except ImportError:
                raise RuntimeError("basic_pitch 未安装，无法提取旋律")
        elif tool_name == 'fluidsynth':
            import shutil
            if not shutil.which('fluidsynth') and not self.fluidsynth_path:
                raise RuntimeError("fluidsynth 未找到，无法渲染音频")
        elif tool_name == 'soundfont':
            if not self.soundfont_path or not os.path.exists(self.soundfont_path):
                raise RuntimeError(f"音色库文件不存在: {self.soundfont_path}")
        elif tool_name == 'chordmini':
            if not self.chordmini_url or self.chordmini_url == "http://localhost:8001":
                raise RuntimeError("ChordMini API 未配置或不可用")

# 全局工具网关实例
tool_gateway = ToolGateway()
