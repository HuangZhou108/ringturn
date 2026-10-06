# Agent 执行可观测性

## 1. 目标与边界

RingTurn 将面向用户的 `thinking_process` 与工程诊断用的
`execution_trace` 分开：

| 数据 | 用途 | 内容 |
|---|---|---|
| `thinking_process` | 前端展示 | 规划说明、友好进度和简化工具反馈 |
| `execution_trace` | 开发与故障诊断 | 节点、工具、路由、耗时、结果结构、标准错误 |

执行轨迹不保存模型隐藏思维链、API Key、令牌、工具参数值或工具结果
原文。工具输入只保留参数数量、参数名和类型；输出只保留类型、键名和
集合大小。

可观测性之上增加了独立的执行韧性策略，但不改变音频算法、质量阈值或
质量返工条件：规划与主图共享总执行时限；只有显式白名单中的无副作用
分析工具可以针对瞬时错误进行有限重试；已有安全降级路径会记录为事件。

## 2. 当前 Agent 架构

主图是确定性的 LangGraph 工作流，而不是“每个节点都是 ReAct Agent”：

```text
entry_router
  → fetch_source → analyze_structure → extract_melody
  → generate_midi → arrange → render → check_quality → reflect
  → retry_router
      ├─ arrange（needs_revision 且未超过重试上限）
      └─ END
```

分析、旋律提取、编排和质量检查内部可使用子图；`arrange` 可选使用
function calling 自主编排，失败时回退到确定性流程。主图节点通过统一包装器
记录事件，因此音频节点不需要重复编写日志代码。

## 3. 事件模型

示例：

```json
{
  "event_id": "4e69c770-5fa4-4a96-a165-3eae9c8dc08b",
  "task_id": "task-uuid",
  "thread_id": "task-uuid",
  "timestamp": "2026-10-05T10:45:00.000Z",
  "kind": "node",
  "name": "extract_melody",
  "status": "succeeded",
  "duration_ms": 1824.317,
  "details": {
    "updated_fields": ["melody_data", "selected_melody_extractor"]
  }
}
```

字段约束：

- `kind`：`task`、`node`、`tool`、`route` 或 `resilience`。
- `status`：`running`、`succeeded`、`failed`、`cancelled` 或
  `selected`；韧性事件还可使用 `retrying`、`fallback`、`exhausted`。
- `thread_id`：与 LangGraph checkpoint 的 `thread_id` 一致，当前为
  `task_id`。
- `details`：只允许轻量结构摘要，不能放音符列表、音频内容或完整模型输出。
- 单个任务最多保留最近 500 个事件，按 `event_id` 去重。

节点开始、成功、失败和取消都会产生事件。入口恢复选择与质量重试选择会
产生 `route` 事件，并包含确定性的 `reason` 标签。

## 4. 统一错误模型

节点、工具和任务级错误均使用以下结构：

```json
{
  "code": "TOOL_EXECUTION_FAILED",
  "scope": "tool",
  "component": "render_midi_with_fluidsynth",
  "retryable": false,
  "exception_type": "RuntimeError",
  "message": "FluidSynth returned exit code 1"
}
```

当前稳定错误码：

| 错误码 | `retryable` | 含义 |
|---|---:|---|
| `EXECUTION_CANCELLED` | false | 用户或系统取消 |
| `EXECUTION_TIMEOUT` | true | 执行超时 |
| `REQUIRED_FILE_NOT_FOUND` | false | 必需文件不存在 |
| `DEPENDENCY_CONNECTION_FAILED` | true | 外部依赖连接失败 |
| `NODE_EXECUTION_FAILED` | false | 未进一步分类的节点错误 |
| `TOOL_EXECUTION_FAILED` | false | 未进一步分类的工具错误 |
| `TASK_EXECUTION_FAILED` | false | 规划或任务级未分类错误 |

`retryable` 是错误分类，不代表一定重试。只有工具名同时位于
`AGENT_RETRYABLE_TOOLS` 白名单、尚未达到尝试上限时，才会自动重试。
用户取消、校验错误、文件缺失和未知错误均不会自动重放。

## 5. 超时、异常重试与降级

三类机制彼此独立：

| 机制 | 范围 | 默认策略 |
|---|---|---|
| Pipeline deadline | 规划 + LangGraph 主流程 | 1800 秒，共享同一个 deadline |
| 异常重试 | 白名单中的无副作用分析工具 | 最多 2 次尝试，单次 180 秒，指数退避 |
| 质量返工 | `reflect → retry_router → arrange` | 继续使用任务的 `max_retries` |

默认异常重试白名单只包含读取/分析操作，不包含旋律提取、写 MIDI、编曲、
渲染或 Demucs。同步音频库若长时间不向事件循环让出控制权，协程超时无法
强制终止底层原生计算；这类工具后续应迁移到可终止的独立 worker/子进程。

当前显式安全降级包括：

- Demucs 失败后使用原始音频；
- Basic Pitch 失败后尝试 librosa；
- 自主 function-calling 编曲失败后使用确定性编曲子图；
- 长休止伴奏失败后保留基础编曲结果。

重试产生 `resilience/retrying` 事件；降级产生 `resilience/fallback` 事件；
总时限耗尽产生 `resilience/exhausted` 和任务失败事件。工具成功事件包含
`attempts` 与 `retries`，便于区分首次成功与重试恢复。

可通过环境变量调整策略：

```env
AGENT_PIPELINE_TIMEOUT_SECONDS=1800
AGENT_TOOL_TIMEOUT_SECONDS=180
AGENT_TOOL_MAX_ATTEMPTS=2
AGENT_TOOL_RETRY_BACKOFF_SECONDS=1
AGENT_TOOL_RETRY_MAX_BACKOFF_SECONDS=8
AGENT_RETRYABLE_TOOLS=get_metadata,detect_tempo_beats
```

## 6. 持久化与 checkpoint 生命周期

1. `AgentState.execution_trace` 使用 LangGraph reducer 合并事件，因此节点和
   路由事件进入 SQLite checkpoint。
2. 工具回调在执行过程中把事件同步写入现有
   `Task.intermediate_data.execution_trace`，状态 API 可即时看到进展。
3. 任务完成时，执行器将 checkpoint 中的节点事件与数据库中的工具事件
   按 `event_id` 合并。
4. 任务失败时，失败节点与任务级错误仍保存在 `intermediate_data`，无需等待
   图返回最终 state。
5. 反馈子任务继承音频中间产物，但不继承父任务的 trace 或 error；新任务使用
   自己的 checkpoint `thread_id`。

轨迹复用现有 JSON 字段，不需要数据库迁移。完整候选音符和二进制音频不会
进入轨迹。

## 7. 诊断 API

```http
GET /api/v1/tasks/{task_id}/trace
```

响应包含任务状态、checkpoint ID、事件数量、事件列表和最近的结构化错误。
`GET /api/v1/tasks/{task_id}/status` 只返回事件数量、最新事件和错误，不在轮询
接口中重复传输完整轨迹。

排查顺序建议：

1. 查看最后一个 `failed` 或 `cancelled` 事件。
2. 用 `component` 定位节点或工具。
3. 查看前一个 `route` 事件，确认恢复或重试分支。
4. 用 `thread_id` 对应 LangGraph checkpoint。
5. 结合 `thinking_process` 查看面向用户的步骤说明，但不要把它当作工程 trace。
