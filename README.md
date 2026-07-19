# RingTurn
[![en](https://img.shields.io/badge/lang-English-red.svg)](./README.en.md)
[![zh](https://img.shields.io/badge/lang-中文-blue.svg)](./README.md)
## 免责声明

**本项目为南京大学智能软件与工程学院本科《软件工程与计算Ⅲ》课程项目，仅供学习使用。**

1. **音频版权**：用户使用的音频文件版权归原权利人所有。用户须确保自己拥有使用该音频的合法权利。本项目仅提供技术处理工具，不承担因用户上传使用内容而产生的任何法律责任。

2. **生成内容的使用**：本项目生成的铃声音频仅供用户个人使用。用户不得将生成内容用于商业目的或进行公开传播。因用户使用生成内容引发的任何版权纠纷，与本项目开发者无关。

3. **“按原样”提供**：本软件按“原样”提供，不提供任何明示或暗示的担保，包括但不限于对适销性、特定用途适用性和非侵权性的担保。在任何情况下，作者或版权持有人均不对任何索赔、损害或其他责任负责。

4. **第三方依赖**：本项目依赖的部分外部工具（如 FluidSynth、Demucs 等）可能有其独立的许可证条款，请用户自行遵守。

## 项目概述

RingTurn 是一款 AI 音乐改编应用，支持用户上传音频、设置参数并用自然语言描述需求，系统自动完成音乐分析、旋律提取、MIDI 生成、乐器改编和音频渲染。

本项目包含前端（React + Vite）和后端（FastAPI + LangGraph）。

本项目默认以本地部署方式运行，不涉及用户注册、登录或任何云端账户体系。因此我们没有采用传统的 User 模块，而是使用 Profile（档案）来管理用户的个性化配置。Profile 仅存储乐器偏好、默认参数等本地配置信息，不收集任何个人敏感数据，既降低了部署与维护的复杂度，也避免了用户隐私合规方面的额外负担。（可参考[Profile与本地存储方案文档](./docs/设计说明文档：Profile模块与本地存储方案.md)）

### 项目背景与动机

当前，普通用户想要将喜欢的歌曲改编为手机铃声面临多重阻碍：**专业软件门槛高**、**AI 生成工具不可控**、**人工编曲成本高**。
RingTurn 尝试填补这一空白，在流程上利用外部工具+LLM语义理解模仿人类编曲师，期望提供一个 **免费、基于原曲进行可控改编** 的 AI Agent，让非专业人士也能轻松获得个性化铃声。

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
conda activate ringturn
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
（在测试中注意到在不同环境下有变化，建议按照实际情况处理）

### 5.下载音色库
为了保证项目正常运行，你至少需要在`backend/soundfonts`文件下下载一个音色库，具体可参考[SOUNDFONTS.md](./backend/SOUNDFONTS.md)。

## 配置环境变量

创建 `.env` 文件：

```
# LLM 配置
LLM_API_KEY=your-api-key-here
LLM_MODEL=glm-4-flash
LLM_BASE_URL=https://your-api-endpoint
DATABASE_URL=sqlite:///./ringturn.db
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

## API 接口（部分）

| 方法   | 路径                             | 说明               |
| :----- | :------------------------------- | :----------------- |
| POST   | `/api/v1/upload`                 | 上传音频文件       |
| POST   | `/api/v1/tasks`                  | 创建改编任务       |
| GET    | `/api/v1/tasks/{task_id}`        | 获取任务详情       |
| GET    | `/api/v1/tasks/{task_id}/status` | 获取任务状态       |
| GET    | `/api/v1/tasks/{task_id}/result` | 获取生成结果       |
| DELETE | `/api/v1/tasks/{task_id}`        | 取消任务           |
| GET    | `/api/v1/profiles/{profile_id}/tasks` | 获取当前档案的任务列表 |
| WS     | `/ws/chat/{task_id}`             | WebSocket 实时推送 |

详情请见[接口文档](./docs/接口文档.md)。

### 常见问题

**Q: 音频生成失败，日志显示 `FluidSynth未找到`**
A: 检查 FluidSynth 是否安装并添加 PATH。

**Q: 音频生成失败，日志显示 `FFmpeg 不可用`**
A: 安装 FFmpeg 并确认 `ffmpeg -version` 能正常输出。

**Q: librosa 相关 warning 导致生成质量差**
A: 使用 Python 3.10 创建虚拟环境，避免 3.13 的兼容性问题。

## 页面
详情请查看[前端页面设计文档](./docs/前端页面设计.md)。

## 技术选型

| 层级 | 技术栈 | 说明 |
| :--- | :--- | :--- |
| **前端** | React 18 + TypeScript | 构建交互式用户界面 |
| **前端可视化** | ReactFlow | 用于工具链图的展示与编辑 |
| **国际化** | i18next | 支持中英文界面切换 |
| **后端框架** | FastAPI + Uvicorn | 提供高性能 REST API 与 WebSocket |
| **Agent 框架** | LangGraph + LangChain | 构建有状态、可恢复的 Agent 工作流 |
| **LLM 模型** | GLM-4-Flash | 负责自然语言理解、任务规划与反思决策 |
| **音频处理** | Librosa, Basic Pitch, Demucs, FluidSynth | 涵盖音频分析、旋律提取、音源分离与 MIDI 渲染 |
| **数据库** | SQLite + SQLAlchemy | 轻量级数据持久化，配合 LangGraph Checkpoint 实现任务状态保存 |

## 项目反思与经验总结

### 1. 设计与实现的错位

在实际开发过程中，我们发现规划与落地之间存在一定差距：

- **页面设计**：原计划通过 Figma/Penpot 进行精细的 UI 设计，但相关工具学习曲线陡峭，且设计和开发之间的错位难以弥合。后期我们改用“快速原型 + 开发中迭代优化”的模式，在保证界面可用性的同时，根据实际开发情况动态调整交互细节。
- **工具链效果**：设计阶段计划利用工具进行精准的音乐分析。但在实际 Windows 环境中测试发现，部分论文中的 SOTA（State-of-the-art）模型落地效果不佳或环境兼容性差，我们不得不重新调整改编策略。
- **开发计划**：原计划在迭代三重点提升 `Arrange` 节点（引入 RAG 知识库、支持用户保存改编 Skill），但由于 `Analysis` 和 `Extract_Melody` 等前置节点的基础不牢，我们花费了大量时间测试外部工具，最终导致学期剩余时间不足以完成 Arrange 节点的进阶功能。

### 2. 架构收获

尽管面临挑战，我们在架构设计上取得了一定进展：

- **动态子图重构**：将 `Analysis`、`Extract_Melody`、`Arrange` 等核心节点重构为基于 JSON 配置驱动的动态子图，极大提升了系统的可扩展性与灵活性。（可参考[用户工具管理功能设计文档](./docs/用户工具管理功能设计.md)）
- **产品化功能落地**：成功实现了历史对话管理、多轮重做（反馈）机制、用户偏好统计与注入等功能，确保了项目在交互层面的完整性。

### 3. 现状与展望

目前，RingTurn 受限于外部工具的实际效果和开发时间，仅能稳定支持**简单的纯音乐乐器更换与基础节奏调整**。但我们在代码结构上为未来接入更多模型与工具预留了充分的空间，体现了本课程项目 **“工程化与可拓展性”** 的核心设计思想。