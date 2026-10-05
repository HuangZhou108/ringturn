# Agent 可观测性

## 目标

RingTurn 将面向用户的 `thinking_process` 与面向工程诊断的
`execution_trace` 分开：

- `thinking_process` 用于展示简短、自然语言的处理进度；
- `execution_trace` 用于定位节点、路由和工具调用的耗时与失败。

执行轨迹不保存 LLM prompt、完整模型回复或隐藏推理，也会对常见的
token、password、secret、authorization 等字段进行脱敏。单个任务最多
保留最近 500 个事件，避免诊断数据无限增长。

## 事件模型

每个事件使用同一份 JSON 契约：

```json
{
  "version": 1,
  "event_id": "5a21...",
  "kind": "node",
  "name": "extract_melody",
  "status": "success",
  "started_at": "2026-10-05T09:20:00.000+00:00",
  "finished_at": "2026-10-05T09:20:08.250+00:00",
  "duration_ms": 8250,
  "metadata": {
    "attempt": 1,
    "updates": ["melody_data", "melody_source_path"]
  }
}
```

`kind` 支持：

| 类型 | 含义 |
| --- | --- |
| `lifecycle` | Agent 整体运行或规划阶段 |
| `node` | LangGraph 主图节点 |
| `tool` | 原子工具或 function calling 工具 |
| `routing` | 入口恢复和质量重试路由 |

失败事件包含标准错误：

```json
{
  "code": "RENDER_FILE_NOT_FOUND",
  "type": "FileNotFoundError",
  "message": "missing.mid",
  "retryable": false
}
```

`retryable` 表示错误类别是否具备重试可能性，并不代表当前版本一定会
自动重试。超时、重试和 fallback 策略将在后续阶段统一实现。

## 数据流

1. Agent 开始时创建 `agent_run` lifecycle 事件。
2. 主图注册节点时统一套用 trace 包装器，不侵入音频算法实现。
3. 节点开始时写入 `running`，结束后按同一 `event_id` 更新为终态。
4. 节点终态同时进入 `AgentState.execution_trace`，因此可由 LangGraph
   checkpoint 序列化。
5. 工具事件由原子工具包装器或 LangChain callback 记录。
6. 所有事件实时保存在 `Task.intermediate_data.execution_trace`。

使用现有 JSON 字段可以兼容旧数据库，无需新增列或迁移。任务结束时，
AgentExecutor 合并音频中间结果，不会覆盖已写入的 trace。

## 查询接口

为避免高频轮询的普通状态接口反复传输完整事件列表，trace 只通过诊断
专用接口返回：

```http
GET /api/v1/tasks/{task_id}/trace
```

返回：

```json
{
  "code": 200,
  "data": {
    "task_id": "...",
    "status": "executing",
    "events": []
  },
  "message": "获取 Agent 执行轨迹成功。"
}
```

## 当前边界

- trace 当前保存在 Task 的 JSON 字段中，适合单机和项目演示；大规模部署
  应迁移到独立事件表或 OpenTelemetry 后端。
- 并发写入保护目前是进程内锁；多 worker 部署应使用独立事件表，避免
  不同进程同时更新同一 JSON 字段。
- 当前只建立可观测性和错误分类，不改变节点 routing、音频参数或 retry
  行为。
- LangGraph checkpoint 保存节点 trace；工具的实时事件以任务数据库中的
  trace 为准。
