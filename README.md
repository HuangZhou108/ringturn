# RingTurn
## ⚠️ 免责声明 / Disclaimer

**本项目为南京大学本科《软件工程与计算》课程项目，仅供学习与学术研究使用。**

1. **音频版权**：用户上传的音频文件版权归原权利人所有。用户须确保自己拥有使用该音频的合法权利。本项目仅提供技术处理工具，不承担因用户上传使用内容而产生的任何法律责任。

2. **生成内容的使用**：本项目生成的铃声音频仅供用户个人使用。用户不得将生成内容用于商业目的或进行公开传播。因用户使用生成内容引发的任何版权纠纷，与本项目开发者无关。

3. **“按原样”提供**：本软件按“原样”提供，不提供任何明示或暗示的担保，包括但不限于对适销性、特定用途适用性和非侵权性的担保。在任何情况下，作者或版权持有人均不对任何索赔、损害或其他责任负责。

4. **第三方依赖**：本项目依赖的部分外部工具（如 FluidSynth、Demucs 等）可能有其独立的许可证条款，请用户自行遵守。

## 项目概述

RingTurn 是一款 AI 音乐改编应用，支持用户上传音频、设置参数并用自然语言描述需求，系统自动完成音乐分析、旋律提取、MIDI 生成、乐器改编和音频渲染。

本项目包含前端（React + Vite）和后端（FastAPI + LangGraph）。

## 前端部署

```
npm install
```

## 前端启动

```
npm run dev
```

访问 `http://localhost:5173/`

## 后端部署

### 1. 创建虚拟环境

```
conda create -n ringturn python=3.10
或
cd backend
python -m venv venv
+
# Windows
venv\Scripts\Activate

# macOS / Linux
source venv/bin/activate
```

### 2.安装依赖

```
cd backend
pip install -r requirements.txt
```

### 3.安装FFmpeg

在没有FFmpeg的情况下，依然可以处理WAV音频。

> 本项目使用 `FFmpeg` 进行音频格式转换、时长获取等操作。虽然代码在缺少 FFmpeg 时会降级运行（仅支持 WAV 复制），但完整功能（如 MP3 与 WAV 互转、任意格式转换）需要依赖 FFmpeg。
> 检验是否已安装工具：

```bash
ffmpeg -version # 应输出版本信息
```

（虚拟环境）conda安装：

```bash
conda install -c conda-forge ffmpeg
```

Windows安装：

1. 访问 [FFmpeg 官网](https://ffmpeg.org/download.html) → Windows 图标 → Windows builds from gyan.dev。
2. 下载 ffmpeg-release-full.7z 或 ffmpeg-release-full.zip。
3. 解压到本地，如`C:\ffmpeg`
4. 将路径添加到系统环境变量PATH
   Linux安装：

```bash
sudo apt update
sudo apt install ffmpeg
```

### 4.安装FluidSynth

Windows下载：
访问github仓库[分发界面](https://github.com/FluidSynth/fluidsynth/releases)，下载最新版本，例如`fluidsynth-v2.5.4-win10-x64-cpp11.zip`。
由于`pyFluidSynth`的局限性，暂时必须把FluidSynth下载解压到`C:\tools\fluidsynth`路径，请确保`C:\tools\fluidsynth\bin`存在。

> 之后我们会尝试通过替换工具等方法解决这个问题，使得项目的部署更加简单。

### 5.下载音色库

Windows下载：
访问github仓库[分发界面](https://github.com/FluidSynth/fluidsynth/releases)，下载最新版本，例如`fluidsynth-v2.5.4-win10-x64-cpp11.zip`。
由于`pyFluidSynth`的局限性，暂时必须把FluidSynth下载解压到`C:\tools\fluidsynth`路径，请确保`C:\tools\fluidsynth\bin`存在。

> 之后我们会尝试通过替换工具等方法解决这个问题，使得项目的部署更加简单。

## 配置环境变量

创建 `.env` 文件：

```
# LLM 配置
LLM_API_KEY=your-api-key-here
LLM_MODEL=gpt-4
LLM_BASE_URL=https://your-api-endpoint
DATABASE_URL=sqlite:///./ringturn.db

# 音频渲染
FLUIDSYNTH_PATH=C:\tools\fluidsynth\bin\fluidsynth.exe
SOUNDFONT_PATH=./soundfonts/default.sf2

# 音频配置
MAX_AUDIO_SIZE_MB=50
SUPPORTED_AUDIO_FORMATS=["mp3", "wav"]
DEFAULT_RINGTONE_DURATION=30
MAX_RINGTONE_DURATION=60
```

## 后端启动

```
python -m app.main
# 或
uvicorn app.main:app --reload
```

服务运行在 `http://localhost:8000`

### API文档

启动后访问：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 项目结构

更详细的结构信息参见前端和后端的readme

```
ringturn/
├── frontend/ # 前端项目
│ ├── src/
│ │ ├── api/index.ts # API 请求封装
│ │ ├── components/ # 通用组件
│ │ ├── pages/
│ │ │ ├── Home.tsx # 首页
│ │ │ └── ChatFlow.tsx # 聊天页
│ │ ├── types/index.ts # TypeScript 类型
│ │ ├── App.tsx # 路由配置
│ │ ├── main.tsx # 应用入口
│ │ ├── i18n.ts # 国际化配置
│ │ └── index.css # 全局样式
│ ├── vite.config.ts # Vite 配置（含代理）
│ ├── tailwind.config.js # Tailwind 配置
│ └── package.json # 前端依赖
│
└── backend/ # 后端项目
  ├── app/
  │ ├── main.py # FastAPI 入口
  │ ├── core/config.py # 配置管理
  │ ├── models/ # 数据库模型
  │ ├── api/v1/ # API 路由
  │ ├── agent/ # LangGraph Agent
  │ ├── atomic_tools/ # 原子工具集
  │ ├── schemas/ # Pydantic 数据模型
  │ ├── services/ # 业务服务
  │ └── db/session.py # 数据库管理
  ├── soundfonts/ # SoundFont 音色库
  └── requirements.txt # Python 依赖
```

## 环境要求

| 工具       | 版本        | 用途            |
| ---------- | ----------- | --------------- |
| Node.js    | ≥ 18.18.0   | 前端运行环境    |
| Python     | 3.10 ~ 3.12 | 后端运行环境    |
| FFmpeg     | 最新版      | 音频格式转换    |
| FluidSynth | ≥ 2.3       | MIDI 渲染为音频 |

## API 接口

| 方法   | 路径                             | 说明               |
| :----- | :------------------------------- | :----------------- |
| POST   | `/api/v1/upload`                 | 上传音频文件       |
| POST   | `/api/v1/tasks`                  | 创建改编任务       |
| GET    | `/api/v1/tasks/{task_id}`        | 获取任务详情       |
| GET    | `/api/v1/tasks/{task_id}/status` | 获取任务状态       |
| GET    | `/api/v1/tasks/{task_id}/result` | 获取生成结果       |
| DELETE | `/api/v1/tasks/{task_id}`        | 取消任务           |
| GET    | `/api/v1/users/{user_id}/tasks`  | 获取历史任务列表   |
| WS     | `/ws/chat/{task_id}`             | WebSocket 实时推送 |

### 常见问题

**Q: 音频生成失败，日志显示 `FluidSynth未找到`**
A: 检查 FluidSynth 是否安装并添加 PATH。

**Q: 音频生成失败，日志显示 `FFmpeg 不可用`**
A: 安装 FFmpeg 并确认 `ffmpeg -version` 能正常输出。

**Q: librosa 相关 warning 导致生成质量差**
A: 使用 Python 3.10 创建虚拟环境，避免 3.13 的兼容性问题。
