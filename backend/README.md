# RingTurn 后端

FastAPI + LangGraph 实现的 AI 音乐改编后端。当前架构不是“所有节点均为 ReAct
子 Agent”，而是固定主工作流、条件路由、领域子图与可选 function calling 的
混合模式。

## 核心职责

- 提供任务、会话、Profile、反馈、人工介入、知识和记忆 REST API。
- 使用数据库租约调度任务，支持重复执行防护、心跳和重启恢复。
- 运行可 checkpoint 的 LangGraph 音频改编流程。
- 持久化任务事件，通过 WebSocket 实时推送并支持游标回放。
- 记录执行 trace、结构化错误、重试、降级和路由决策。
- 管理持久化 RAG 知识与 Profile 长期记忆。

## 快速启动

推荐 Python 3.10；Python 3.11 也可使用。当前部分音频依赖不适配 Python 3.12。

```bash
conda create -n ringturn python=3.10
conda activate ringturn
cd backend
pip install -r requirements.txt
```

完整渲染还需要：

- FFmpeg：音频探测、裁剪和格式转换；
- FluidSynth：MIDI 渲染；
- GM SoundFont：默认配置为 `./soundfonts/default.sf2`。

SoundFont 说明见 [SOUNDFONTS.md](./SOUNDFONTS.md)。

配置 `backend/.env`：

```env
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4
LLM_BASE_URL=
LLM_REQUEST_TIMEOUT_SECONDS=60
LLM_MAX_ATTEMPTS=3

DATABASE_URL=sqlite:///./ringturn.db
CHECKPOINT_DB_URL=sqlite:///./checkpoints.db

FLUIDSYNTH_PATH=fluidsynth
SOUNDFONT_PATH=./soundfonts/default.sf2
FFMPEG_PATH=

AGENT_PIPELINE_TIMEOUT_SECONDS=1800
AGENT_TOOL_TIMEOUT_SECONDS=180
AGENT_TOOL_MAX_ATTEMPTS=2
AGENT_LEASE_SECONDS=120
AGENT_HEARTBEAT_SECONDS=30
AGENT_RECOVER_ON_STARTUP=true

TASK_EVENT_REPLAY_LIMIT=500
TASK_EVENT_POLL_SECONDS=1
TASK_EVENT_HEARTBEAT_SECONDS=15

RAG_TOP_K=4
MEMORY_TOP_K=6
MEMORY_MAX_PER_PROFILE=200
MEMORY_HALF_LIFE_DAYS=90
```

启动服务：

```bash
python -m app.main
# 或
uvicorn app.main:app --reload
```

- Swagger UI：`http://localhost:8000/docs`
- ReDoc：`http://localhost:8000/redoc`
- 健康检查：`GET http://localhost:8000/api/v1/health`

## Agent 架构

### 主图

`app/agent/graph.py` 定义固定主流程：

```text
entry_router
  → fetch_source
  → analyze_structure
  → extract_melody
  → generate_midi
  → arrange
  → render
  → check_quality
  → reflect
  → retry_router → END / arrange
```

- `entry_router` 支持新任务、反馈子任务和人工介入恢复。
- `retry_router` 只在质量反思要求且未超过 `max_retries` 时回到 `arrange`。
- 主图使用 `AsyncSqliteSaver` 保存 checkpoint，`thread_id` 与任务 ID 一致。
- 每个节点由 `instrument_node` 包装，生成统一 trace 和结构化错误。

### 子图与工具

| 主节点 | 实现方式 | 说明 |
|---|---|---|
| `analyze_structure` | `analysis_graph` | 元数据、节拍、响度、频谱、段落、情绪等分析 |
| `extract_melody` | `extract_graph` | 音源选择、多提取器候选、评分与稳定化 |
| `arrange` | `arrange_graph` | 确定性编曲；可选 function calling，自主失败后回退 |
| `check_quality` | `quality_graph` | 音频与音乐性质量检查 |
| `reflect` | LLM + 确定性边界 | 决定是否有界返工并给出纠正动作 |

原子工具位于 `app/agent/atomic_tools/`：

- `analysis/`：节拍、调性、和弦、响度、频谱、段落、分离等；
- `melody/`：Basic Pitch、librosa、候选选择、量化、调性修正等；
- `midi/`：音符转 MIDI、节拍写入、验证；
- `arrangement/`：换音色、变速、移调、和声、合并轨道等；
- `rendering/`：FluidSynth、MP3 转换和智能截取；
- `quality/`：响度、动态、频谱、旋律和综合质量；
- `knowledge/`：编曲知识检索。

详细说明见 [Agent 详细设计](../docs/Agent详细设计.md)。

## 任务调度与恢复

`services/task_scheduler.py` 使用 `task_execution_leases`：

1. 创建任务后只做本机调度提示，真正执行前必须原子取得数据库租约；
2. 心跳延长租约；其他 worker 不能重复认领；
3. 进程崩溃后租约过期，应用启动会扫描 `pending` 或孤儿活跃任务；
4. `AgentExecutor` 从 LangGraph checkpoint 和任务中间数据恢复；
5. 正常停机使用 `suspend`，不会把任务误标为用户取消。

取消接口先持久化 `cancelled`，再中断当前进程内执行器。终态更新采用条件写入，
迟到的完成/失败不能覆盖取消。

## 实时事件与诊断

`services/task_events.py` 把任务事件写入 `task_events`，同时通过进程内 broker
低延迟扇出。WebSocket：

```text
/ws/chat/{task_id}?after_event_id={cursor}
```

连接时先订阅 broker，再回放数据库事件；之后用轮询补偿其他 worker 的写入。
一个任务可有多个客户端。`GET /api/v1/tasks/{task_id}/trace` 返回清洗后的执行
诊断，敏感参数、路径和提示词正文不会进入 trace。

详见：

- [Agent 执行可观测性](../docs/Agent执行可观测性.md)
- [Agent 运行时连续性](../docs/Agent运行时连续性.md)

## RAG 与长期记忆

- `knowledge_documents`：全局或 Profile 专属知识；启动时幂等写入内置文档。
- `long_term_memories`：Profile 隔离的偏好、约束、反馈、指令和历史。
- 检索融合 BM25 与中文单字/双字、英文词项的哈希向量余弦相似度。
- 反馈、人工回答和成功任务会自动写入；执行前按当前请求召回。
- 记忆带去重、重要度、置信度、置顶、时间衰减、来源和容量上限。

详见 [RAG 与长期记忆](../docs/RAG与长期记忆.md)。

## API 路由

路由统一挂载在 `/api/v1`：

| 模块 | 前缀/路径 | 主要能力 |
|---|---|---|
| Health | `/health` | 健康检查 |
| Upload | `/upload` | 音频上传 |
| Tasks | `/tasks` | 创建、状态、结果、trace、取消 |
| Feedback/HITL | `/tasks/{id}/feedback`、`/interventions` | 反馈重做与人工介入 |
| Conversations | `/conversations` | 会话、消息、活跃任务 |
| Profiles | `/profiles` | 档案、激活、导入导出、偏好、工具配置 |
| Memory | `/profiles/{id}/memories` | 长期记忆管理与检索 |
| Knowledge | `/knowledge` | 知识文档管理与检索 |

完整请求与响应见 [接口文档](../docs/接口文档.md)。

## 数据模型

| 表 | 用途 |
|---|---|
| `profiles` | 本地档案 |
| `tasks` | 任务、计划、状态、产物和恢复数据 |
| `task_execution_leases` | 调度租约与心跳 |
| `task_events` | WebSocket 可回放事件 |
| `feedbacks` | 用户反馈 |
| `human_interventions` | 人工问题与回答 |
| `conversations` / `conversation_messages` | 历史会话 |
| `preferences` / `tool_preferences` | 统计偏好、覆盖参数和子图配置 |
| `knowledge_documents` | RAG 知识 |
| `long_term_memories` | Profile 长期记忆 |

应用启动通过 SQLAlchemy `create_all` 创建缺失表。当前仓库尚未建立完整的 Alembic
版本迁移流程；生产数据库变更应先补迁移脚本和备份策略。

## 测试

```bash
python -m pytest -q
python -m compileall -q app tests
python -m ruff check app tests --select=F821,F822,F823 --ignore=I
```

当前回归基线：`114 passed, 3 skipped`。

## 扩展约定

- 新原子工具放入对应的 `atomic_tools/<domain>/`，声明清晰输入输出；只有无副
  作用、幂等的分析工具才应加入重试白名单。
- 新主节点需更新 `AgentState`、主图、入口路由允许列表、trace 和恢复策略。
- 新子图节点应通过子图状态与主状态显式映射，避免未声明字段丢失。
- 新状态写入必须保留 `cancelled` 终态优先级并考虑租约所有权。
- 新事件必须先持久化再发布，客户端以 `event_id` 去重和续传。
- 任何长期记忆正文都不得写入执行 trace；召回内容应继续视为用户数据。
