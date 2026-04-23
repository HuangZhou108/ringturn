# API与工具接入清单

## 当前实现状态

### ✅ 已完成

| 模块 | 状态 | 说明 |
|------|------|------|
| FastAPI框架 | ✅ 完成 | RESTful API + 异常处理 |
| SQLAlchemy模型 | ✅ 完成 | User, Task, Feedback, Preference |
| Pydantic Schemas | ✅ 完成 | 请求/响应模型 |
| Agent核心（LangGraph） | ✅ 完成 | ReAct模式工作流 |
| LLM服务 | ✅ 完成 | OpenAI兼容API + 解析 |
| 工具网关 | ✅ 完成 | 架构完成，部分Mock |
| WebSocket | ✅ 完成 | 实时状态推送 |
| 用户服务 | ✅ 完成 | CRUD + 偏好管理 |

### 🔄 部分实现（Mock + 预留接口）

| 模块 | 当前实现 | 待接入API/工具 | 说明 |
|------|----------|---------------|------|
| **音频分析** | Mock数据 | ChordMini API | 和弦/BPM/结构检测 |
| **旋律提取** | Mock数据 | Basic Pitch (Spotify) | 主旋律提取 |
| **MIDI生成** | 占位文件 | Basic Pitch | 音频转MIDI |
| **乐器改编** | 占位文件 | MuseMorphose/Groove2Groove | 风格迁移 |
| **音频渲染** | 占位文件 | FluidSynth + .sf2 | MIDI转音频 |
| **质量评估** | Mock数据 | UTMOS/speechmetrics | 音频质量打分 |
| **智能截取** | 直接返回 | Audjust API | 最佳片段选择 |

## 需要补充的API/工具说明

### 1. 音频分析 API

#### ChordMini (Spotify) ⭐推荐
- **功能**: 和弦、BPM、节拍、调性检测
- **部署**: Docker自托管
- **成本**: 免费
- **难度**: 低

**接入方式**:
```python
POST http://localhost:8001/analyze
Content-Type: multipart/form-data

# 返回:
{
  "bpm": 120,
  "key": "C",
  "chords": [...],
  "beats": [...]
}
```

#### Essentia API
- **功能**: 全面音乐特征（调性、节奏、情绪、流派）
- **成本**: 免费额度（需注册）
- **难度**: 中

#### Beatlyze
- **功能**: 段落结构、循环点、节拍边界
- **免费额度**: 每月50次
- **难度**: 低

### 2. MIDI生成

#### Basic Pitch (Spotify)

⚠️ **注意**: basic-pitch 对 Python 版本有要求（推荐 **Python 3.10**），最新版支持到py3.12。

- **功能**: 复调音乐转录（音频→MIDI）
- **成本**: 免费
- **难度**: 低

**安装方式**:

```bash
# 方式一：推荐 - 使用 Python 3.10 虚拟环境
python3.10 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate  # Windows
pip install basic-pitch

# 方式二：从 GitHub 安装最新版（可能已修复兼容性问题）
pip install git+https://github.com/spotify/basic-pitch.git
```

**使用**:
```python
from basic_pitch import ICASSP_2022_MODEL_PATH
from basic_pitch.inference import predict

model_output = predict(
    audio_path,
    model_or_path=ICASSP_2022_MODEL_PATH,
    # 输出MIDI文件
)
```

### 3. 乐器改编/风格迁移

#### MuseMorphose
- **功能**: 钢琴音乐风格迁移（MIDI→MIDI）
- **部署**: PyTorch模型
- **成本**: 免费
- **难度**: 中
- **仓库**: https://github.com/tsukasachandesu/MuseMorphose

#### Groove2Groove
- **功能**: 伴奏风格迁移
- **部署**: Docker
- **成本**: 免费
- **难度**: 中
- **仓库**: https://github.com/cifkao/groove2groove

### 4. 音频渲染

#### FluidSynth
- **功能**: MIDI→音频（需要.sf2音色库）
- **部署**: 系统可执行文件
- **成本**: 免费
- **难度**: 低

**使用方式**:
```bash
# 命令行
fluidsynth -ni soundfont.sf2 input.mid -F output.wav -r 44100

# Python库
import fluidsynth
fs = fluidsynth.Synth()
fs.start(driver="alsa")
```

**音色库获取**:
- GeneralUser GS (~70MB): https://schristiancollins.com/generaluser.php
- Salamander Piano (~30MB): 轻量级钢琴音色

### 5. 质量评估

#### UTMOS
- **功能**: 无参考MOS预测（1-5分）
- **部署**: Python库
- **成本**: 免费
- **难度**: 低

```bash
pip install utmos
```

#### TorchAudio-SQUIM
- **功能**: PESQ, STOI, SI-SDR, MOS
- **部署**: PyTorch内置
- **难度**: 低

### 6. 智能截取

#### Audjust API
- **功能**: 检测最佳片段、循环点
- **成本**: 上传免费，分析按次计费
- **难度**: 低

## 环境变量配置清单

需要在 `backend/.env` 中配置：

```env
# ============ LLM配置 ============
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4
# 可选：自定义API端点
# OPENAI_BASE_URL=https://your-api-endpoint

# ============ 音频分析 ============
# ChordMini服务地址（如自托管）
CHORDMINI_URL=http://localhost:8001

# Beatlyze API Key（如使用）
# BEATLYZE_API_KEY=xxx

# ============ MIDI生成 ============
# Basic Pitch模型路径
BASIC_PITCH_MODEL_PATH=./models/basic-pitch

# ============ 音频渲染 ============
# FluidSynth可执行文件路径
FLUIDSYNTH_PATH=fluidsynth  # Linux/macOS
# FLUIDSYNTH_PATH=C:\Program Files\FluidSynth\bin\fluidsynth.exe  # Windows

# 音色库文件路径（相对backend目录）
SOUNDFONT_PATH=./soundfonts/piano.sf2

# ============ 质量评估 ============
# 选择评估模型: "utmos" 或 "speechmetrics"
QUALITY_EVAL_MODEL=utmos

# ============ 数据库 ============
DATABASE_URL=sqlite:///./ringturn.db

# ============ 其他 ============
# 默认铃声时长（秒）
DEFAULT_RINGTONE_DURATION=30
```

## 优先接入顺序建议

### 阶段一（MVP，1-2天）
1. **ChordMini** - 替代Mock分析数据
2. **Basic Pitch** - 真实MIDI生成
3. **FluidSynth + 音色库** - 真实音频渲染

### 阶段二（增强，3-5天）
4. **UTMOS** - 质量评估
5. **Audjust API** - 智能截取优化
6. **MuseMorphose** - 乐器改编

### 阶段三（高级，1-2周）
7. 用户认证系统（JWT）
8. OSS音频存储
9. 多轮对话优化
10. 在线搜索音频源

## 快速测试

当前代码可用的部分：
- ✅ 创建任务、查询状态、获取结果
- ✅ WebSocket实时推送
- ✅ 提交反馈创建子任务
- ✅ Mock数据生成流程（会创建空文件）

运行测试：
```bash
cd backend
uvicorn app.main:app --reload

# 创建任务
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"user_request": "钢琴版铃声", "source_type": "upload", "source_value": "test.mp3"}'

# 查询状态
curl http://localhost:8000/api/v1/tasks/{task_id}/status

# 连接WebSocket
wscat -c ws://localhost:8000/ws/chat/{task_id}
```

## 常见问题

**Q: 为什么文件生成失败？**
A: 当前工具都是Mock实现，仅创建空文件。需要接入真实API。

**Q: 如何接入真实API？**
A: 修改 `app/agent/tools.py` 中的 `ToolGateway` 类方法，将Mock逻辑替换为实际HTTP请求或本地模型推理。

**Q: 音色库文件在哪里下载？**
A: 见 `SOUNDFONTS.md` 文档。

**Q: 如何配置OpenAI兼容的第三方API？**
A: 在 `.env` 中设置 `OPENAI_BASE_URL` 为API地址，`OPENAI_API_KEY` 为密钥。

**Q: 用户系统如何扩展？**
A: 参考 `app/services/user_service.py`，添加登录认证模块。
