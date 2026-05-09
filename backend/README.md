# RingTurn 后端

AI音乐改编Agent - 将歌曲自动改编为独特铃声

## 项目概述

RingTurn是一个基于AI Agent的智能音乐改编系统。用户上传音频文件并用自然语言描述想要的风格，系统自动完成：音乐分析 → 主旋律提取 → MIDI生成 → 乐器改编 → 渲染输出为纯音乐铃声。

### 技术栈

| 类别 | 技术 |
|------|------|
| Web框架 | FastAPI |
| Agent框架 | LangGraph |
| 推理模式 | ReAct |
| 数据库 | SQLite |
| 状态持久化 | langgraph-checkpoint-sqlite |

## 快速开始

### 1. 安装依赖
推荐创建虚拟环境：
```bash
conda create -n ringturn python=3.10
```
安装依赖：
```bash
cd backend
pip install -r requirements.txt
```
#### 其他
**FFmpeg：**  
在没有FFmpeg的情况下，依然可以处理WAV音频。
> 本项目使用 `FFmpeg` 进行音频格式转换、时长获取等操作。虽然代码在缺少 FFmpeg 时会降级运行（仅支持 WAV 复制），但完整功能（如 MP3 与 WAV 互转、任意格式转换）需要依赖 FFmpeg。
检验是否已安装工具：
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

**FluidSynth：**  
Windows下载：
访问github仓库[分发界面](https://github.com/FluidSynth/fluidsynth/releases)，下载最新版本，例如`fluidsynth-v2.5.4-win10-x64-cpp11.zip`。
由于`pyFluidSynth`的局限性，暂时必须把FluidSynth下载解压到`C:\tools\fluidsynth`路径，请确保`C:\tools\fluidsynth\bin`存在。
> 之后我们会尝试通过替换工具等方法解决这个问题，使得项目的部署更加简单。

**下载音色库**：  
为了保证项目正常运行，你至少需要在`backend/soundfonts`文件下下载一个音色库，具体可查看SOUNDFONTS.md。

### 2. 配置环境变量（可选）

创建 `.env` 文件：

```env
LLM_API_KEY=your-api-key-here
LLM_MODEL=gpt-4
LLM_BASE_URL=https://your-api-endpoint
DATABASE_URL=sqlite:///./ringturn.db
```

### 3. 启动服务

```bash
python -m app.main
# 或
uvicorn app.main:app --reload
```

服务运行在 `http://localhost:8000`

### 4. API文档

启动后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 项目结构

```
backend/
├── app/
│   ├── main.py              # FastAPI应用入口
│   ├── core/                # 核心配置
│   │   ├── config.py        # 配置管理（Settings类）
│   │   └── exceptions.py    # 自定义异常类
│   ├── models/              # 数据库模型（SQLAlchemy）
│   │   └── __init__.py      # User, Task, Feedback, Preference
│   ├── schemas/             # Pydantic数据模型
│   │   ├── common.py        # 通用响应格式
│   │   ├── task.py          # 任务相关schema
│   │   └── feedback.py      # 反馈相关schema
│   ├── api/                 # API路由层
│   │   └── v1/
│   │       └── endpoints/
│   │           ├── tasks.py  # 任务CRUD接口
│   │           ├── users.py  # 用户相关接口
│   │           └── health.py # 健康检查
│   ├── agent/               # Agent核心模块
│   │   ├── state.py         # Agent状态定义
│   │   ├── tools.py         # 工具调用网关
│   │   ├── nodes.py         # 各节点处理逻辑
│   │   ├── graph.py         # LangGraph工作流
│   │   └── agent_executor.py # Agent执行器
│   ├── services/            # 业务服务
│   │   └── file_service.py  # 文件上传/下载
│   └── db/                   # 数据库相关
│       └── session.py       # 会话管理
├── uploads/                  # 上传的音频文件
├── static/ringtones/        # 生成的铃声文件
└── requirements.txt
```

## 核心模块详解

### 1. Agent架构（app/agent/）

RingTurn采用**LangGraph + ReAct**架构实现智能Agent。

#### 状态管理（state.py）

```python
class AgentState(TypedDict):
    task_id: str              # 任务标识
    user_request: str         # 用户需求
    audio_path: str | None    # 音频文件路径
    analysis_result: dict     # 分析结果
    melody_data: dict         # 旋律数据
    midi_path: str            # MIDI文件路径
    plan: list[str]           # 执行计划
    current_step: TaskStep    # 当前步骤
    ...
```

#### 执行流程（graph.py）

```
用户请求 → 规划器(planner) → 分析音频(analyze)
    → 生成MIDI(generate_midi) → 乐器改编(arrange)
    → 渲染音频(render) → 质量反思(reflect) → 完成
                              ↓ (质量不达标)
                         等待用户反馈(human_input)
                              ↓
                         返回改编步骤重新执行
```

#### 节点处理（nodes.py）

每个节点对应一个处理步骤：

| 节点 | 功能 | 说明 |
|------|------|------|
| `fetch_source` | 获取音频源 | 根据source_type获取文件 |
| `analyze` | 分析结构 | 提取BPM、调性、段落 |
| `extract_melody` | 提取旋律 | 获取主旋律音符 |
| `generate_midi` | 生成MIDI | 创建MIDI中间文件 |
| `arrange` | 乐器改编 | 更换乐器音色 |
| `render` | 音频渲染 | MIDI转音频 |
| `quality_check` | 质量检查 | 评估生成质量 |

#### 工具网关（tools.py）

统一封装外部API调用：

```python
class ToolGateway:
    async def analyze_audio_structure(audio_path) -> dict
    async def extract_melody(audio_path) -> dict
    async def generate_midi(melody_data, analysis, output_path) -> str
    async def arrange_instrument(midi_path, instruments, style, output) -> str
    async def render_audio(midi_path, instruments, output, duration) -> str
    async def check_quality(audio_path, reference=None) -> dict
```

### 2. 任务状态机（models/__init__.py）

```
pending → planning → executing → completed
              ↓            ↓
         cancelled      waiting_input
              ↓            ↓
            failed     (等待用户输入后回到executing)
```

| 状态 | 说明 |
|------|------|
| `pending` | 任务已创建，等待调度 |
| `planning` | Agent分析需求，制定计划 |
| `executing` | 执行中（包含多个子步骤） |
| `waiting_input` | 等待用户补充信息 |
| `completed` | 完成 |
| `failed` | 失败 |
| `cancelled` | 已取消 |

### 3. API接口（api/v1/endpoints/）

#### 任务相关

| 方法 | 端点 | 功能 |
|------|------|------|
| POST | `/tasks` | 创建任务 |
| GET | `/tasks/{task_id}` | 获取任务详情 |
| GET | `/tasks/{task_id}/status` | 获取任务状态 |
| GET | `/tasks/{task_id}/result` | 获取生成结果 |
| POST | `/tasks/{task_id}/feedback` | 提交反馈 |
| DELETE | `/tasks/{task_id}` | 取消任务 |

#### 用户相关

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/users/{user_id}/tasks` | 获取用户任务列表 |

### 4. 响应格式

所有API返回统一格式：

```json
{
    "code": 200,
    "data": { ... },
    "message": "success"
}
```

| code | 含义 |
|------|------|
| 200 | 成功 |
| 400 | 业务失败 |
| 401 | 认证/异常错误 |
| 404 | 资源不存在 |
| 500 | 服务器错误 |

## 数据库表

### users（用户表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| username | VARCHAR(64) | 用户名（唯一） |
| created_at | DATETIME | 创建时间 |

### tasks（任务表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | CHAR(36) | UUID主键 |
| user_id | INT | 关联用户 |
| user_request | TEXT | 用户需求 |
| status | ENUM | 任务状态 |
| plan | JSON | 执行计划 |
| current_subtask | VARCHAR | 当前子步骤 |
| subtask_progress | INT | 进度 0-100 |
| final_audio_url | VARCHAR | 生成的铃声URL |
| thread_id | VARCHAR | LangGraph检查点ID |
| error_message | TEXT | 错误信息 |

### feedbacks（反馈表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| task_id | CHAR(36) | 关联任务 |
| content | TEXT | 反馈内容 |
| created_at | DATETIME | 创建时间 |

### preferences（偏好表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| user_id | INT | 关联用户 |
| key | VARCHAR(64) | 偏好键 |
| value | JSON | 偏好值 |

## 使用示例

### 1. 创建任务

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "user_request": "把《起风了》做成温暖钢琴风格的铃声",
    "source_type": "upload",
    "source_value": "file-uuid-here"
  }'
```

响应：

```json
{
    "code": 200,
    "data": {
        "task_id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "pending",
        "created_at": "2025-04-15T10:00:00Z"
    },
    "message": "success"
}
```

### 2. 查询状态

```bash
curl http://localhost:8000/api/v1/tasks/{task_id}/status
```

响应：

```json
{
    "code": 200,
    "data": {
        "task_id": "...",
        "status": "executing",
        "current_subtask": "render",
        "subtask_progress": 0.6,
        "message": "正在渲染音频..."
    },
    "message": "success"
}
```

### 3. 获取结果

```bash
curl http://localhost:8000/api/v1/tasks/{task_id}/result
```

响应：

```json
{
    "code": 200,
    "data": {
        "audio_url": "/static/ringtones/xxx.mp3",
        "duration": 18.5,
        "format": "mp3"
    },
    "message": "success"
}
```

## 后续开发

### 待实现功能

1. **音频分析API接入**
   - ChordMini: 和弦/BPM检测
   - Essentia/Beatlyze: 音乐特征提取

2. **MIDI生成接入**
   - Basic Pitch (Spotify)
   - 字节跳动钢琴转录

3. **乐器改编模型**
   - MuseMorphose: 钢琴风格迁移
   - Groove2Groove: 伴奏风格迁移

4. **音频渲染**
   - FluidSynth: MIDI转音频

5. **质量评估**
   - speechmetrics / UTMOS

6. **WebSocket实时流**
   - Agent思考过程可视化

7. **用户系统**
   - 登录认证
   - 偏好存储
   - 历史记录

### 添加新工具

在 `app/agent/tools.py` 的 `ToolGateway` 类中添加方法：

```python
async def your_new_tool(self, params) -> dict:
    """新工具说明"""
    # TODO: 接入真实API
    return {"mock": "result"}
```

然后在 `app/agent/nodes.py` 中创建对应节点处理器。

## 开发规范

### 添加新API

1. 在 `app/schemas/` 添加Pydantic模型
2. 在 `app/api/v1/endpoints/` 添加路由
3. 在 `app/api/v1/__init__.py` 注册路由

### 添加新Agent节点

1. 在 `app/agent/state.py` 的 `TaskStep` 枚举添加步骤
2. 在 `app/agent/nodes.py` 实现节点逻辑
3. 在 `app/agent/agent_executor.py` 添加执行逻辑

### 数据库迁移

使用SQLAlchemy的 `create_all()` 自动创建表。后续可切换到Alembic进行版本管理。

## 常见问题

**Q: 启动报错 "No module named 'app'"**
A: 确保在 `backend/` 目录下执行，或使用 `PYTHONPATH=. python -m app.main`

**Q: 数据库被锁定**
A: SQLite WAL模式已启用，减少并发写入可解决

**Q: 工具调用返回Mock数据**
A: 当前所有工具都是Mock实现，需要接入真实API
