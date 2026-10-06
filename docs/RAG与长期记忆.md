# RAG 与长期记忆

## 1. 能力边界

本实现面向 RingTurn 的小型、可本地部署知识库，不要求外部向量数据库或
Embedding API。知识和记忆均存储在主数据库中，应用启动时幂等写入内置编曲
知识。后续如需迁移到 pgvector，只需替换检索层，不影响 Agent 和 API 协议。

## 2. RAG

`knowledge_documents` 保存全局知识和 Profile 专属知识。检索同时使用：

- BM25 词项相关度；
- 英文词和中文单字/双字特征的哈希向量余弦相似度；
- Profile 专属文档在同分时优先。

Agent 的 `plan_arrangement` 与自主编曲 `search_knowledge` 工具都会读取当前
Profile，只能看到全局文档及该 Profile 的私有文档。返回内容包含来源和相关度，
便于提示词引用和问题诊断。

## 3. 长期记忆

`long_term_memories` 按 Profile 隔离，支持五类记忆：`preference`、
`constraint`、`feedback`、`instruction` 和 `history`。每条记录包含：

- 内容哈希去重；
- 重要度、置信度和置顶标记；
- 来源任务、访问次数和最近访问时间；
- 创建/更新时间及可选过期时间；
- JSON 元数据。

召回分数综合当前任务相关度、重要度、置信度、时间衰减和置顶加权。每个
Profile 默认最多保留 200 条；超限时优先清理未置顶、低重要度且长期未访问的
记录。

系统会自动记录：

1. 用户对已完成任务提交的反馈；
2. 人工介入回答；
3. 成功任务的需求和最终核心参数。

执行任务时，以“用户请求 + 乐器 + 速度”为查询召回相关记忆。召回内容明确
标记为用户数据而非系统指令，避免历史文本覆盖系统约束。检索只记录数量等
诊断元数据，不把记忆正文写入 trace。

## 4. 管理 API

```http
POST   /api/v1/profiles/{profile_id}/memories
GET    /api/v1/profiles/{profile_id}/memories?query=史诗铜管
PATCH  /api/v1/profiles/{profile_id}/memories/{memory_id}
DELETE /api/v1/profiles/{profile_id}/memories/{memory_id}

GET    /api/v1/knowledge/search?query=抒情铃声&profile_id=1&top_k=4
GET    /api/v1/knowledge/documents?profile_id=1
POST   /api/v1/knowledge/documents
DELETE /api/v1/knowledge/documents/{document_id}
```

内置知识可查询但不能通过 API 删除。自定义知识可设为全局，也可绑定单个
Profile。记忆列表不传 `query` 时按置顶、重要度和更新时间排序；传入查询时
返回混合检索分数。

## 5. 配置

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `RAG_TOP_K` | 4 | 编曲决策注入的知识数量 |
| `MEMORY_TOP_K` | 6 | 每次任务召回的记忆数量 |
| `MEMORY_MAX_PER_PROFILE` | 200 | 单个 Profile 的记忆容量 |
| `MEMORY_HALF_LIFE_DAYS` | 90 | 记忆时间衰减半衰期 |

## 6. 可观测性

每次 Agent 启动会生成 `memory/context_retrieval` trace 事件，包含
`memory_count`、是否存在全局指令、是否存在统计画像以及是否实际注入上下文。
事件不包含记忆正文。RAG 检索日志会输出命中文档标题，知识搜索 API 则直接
返回文档来源和相关度。
