# Agent 运行时连续性与人工介入

## 1. 持久化调度与重启恢复

任务执行不再只依赖 FastAPI 进程内的 `BackgroundTasks`。每次执行前必须先在
`task_execution_leases` 表取得租约：

- `pending` 任务在取得租约的同一事务中进入 `planning`；
- `planning` 或 `executing` 任务只有在旧租约过期后才能被其他实例恢复；
- 执行期间定时刷新 `heartbeat_at` 和 `expires_at`；
- 正常结束、人工暂停或优雅停机后释放租约；
- 服务启动时扫描待执行任务与过期租约，并重新加入本机调度器。

`executing` 任务优先读取相同 `thread_id` 的 LangGraph checkpoint：存在待执行
节点时以 `ainvoke(None, config)` 继续；图已经结束但业务结果尚未同步时，直接
用 checkpoint 最终状态补齐任务结果。`planning` 阶段没有图检查点，因此会重新
生成计划。

应用停机调用 `AgentExecutor.suspend()`，保留任务的可恢复状态，不会把服务关闭
误记成用户取消。用户主动取消仍写入终态 `cancelled`。

相关配置：

```env
AGENT_INSTANCE_ID=
AGENT_LEASE_SECONDS=120
AGENT_HEARTBEAT_SECONDS=30
AGENT_RECOVER_ON_STARTUP=true
```

## 2. 可回放 WebSocket 事件流

`task_events` 是任务事件的持久化日志，自增 `id` 是断线续传游标。当前进程内
使用内存 broker 即时唤醒所有订阅者；其他进程产生的事件通过短周期增量查询
补偿，因此不再轮询整条 Task 记录。

连接方式：

```text
ws://localhost:8000/ws/chat/{task_id}?after_event_id=123
```

| `type` | 说明 |
|---|---|
| `status_update` | pending/planning/executing 状态变化 |
| `thinking_update` | 新增一条用户可见思考记录 |
| `trace_event` | 新增一条结构化工程 trace |
| `waiting_input` | Agent 已暂停并请求人工输入 |
| `completed` / `failed` / `cancelled` | 终态事件 |
| `scheduler_claimed` | 任务取得租约，包含恢复标记与尝试次数 |
| `heartbeat` | 连接保活及当前游标 |

同一任务允许多个客户端同时连接。前端保存每个任务最后收到的事件 ID，重连时
只回放缺失事件。数据库补偿轮询默认 1 秒，WebSocket 心跳默认 15 秒。

## 3. 反馈与人工介入闭环

普通优化反馈仍创建子任务，但现在会持久化原始反馈，并用一次结构化 LLM 调用
同时决定重入节点和参数更新。节点、参数名及数值范围均经过校验。

人工介入用于暂停并恢复同一个任务：

```http
POST /api/v1/tasks/{task_id}/interventions
{
  "question": "需要更快还是更慢？",
  "resume_from_node": "arrange"
}
```

任务原子进入 `waiting_input`，当前执行器仅暂停本地工作，不将任务取消。用户
回答后：

```http
POST /api/v1/tasks/{task_id}/interventions/{intervention_id}/response
{
  "response": "更快一些，调整到 140 BPM",
  "params": {"tempo": 140}
}
```

回答和参数持久化后，任务回到 `pending`，从指定节点使用最新 checkpoint 和
中间产物恢复。前端在收到 `waiting_input` 后直接把普通输入框切换为回答入口。

介入历史可通过 `GET /api/v1/tasks/{task_id}/interventions` 查询。

## 4. 部署边界

- SQLite 适合本地和小规模部署；多实例的事件即时通知依赖数据库增量补偿，
  延迟上限由 `TASK_EVENT_POLL_SECONDS` 决定。
- 长时间不释放 Python 事件循环的原生计算可能导致心跳延后，应把这类工具迁移
  到独立、可终止的 worker。
- 新能力新增表，不修改已有表字段；现有 `init_db()` 的 `create_all` 会自动创建。
