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

本阶段只增加观测能力，不改变音频算法、质量阈值或重试条件。外部工具
的超时、自动重试和降级策略属于后续阶段。

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

- `kind`：`task`、`node`、`tool` 或 `route`。
- `status`：`running`、`succeeded`、`failed`、`cancelled` 或
  `selected`。
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

`retryable` 只是错误分类，不会在本阶段自动触发重试。

## 5. 持久化与 checkpoint 生命周期

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

## 6. 诊断 API

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
