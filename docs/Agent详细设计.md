# RingTurn Agent 详细设计文档

## 1. 概述

### 1.1 Agent 定位

RingTurn Agent 是整个系统的智能核心，负责理解用户需求、规划执行步骤、调用外部工具完成音乐改编任务，并支持多轮对话迭代优化。

### 1.2 技术选型

| 组件 | 技术 | 作用 |
|------|------|------|
| Agent 框架 | LangGraph | 构建有状态、可中断、可恢复的工作流 |
| 推理模式 | ReAct (LangChain) | 结合推理与行动的交互范式 |
| 状态持久化 | langgraph-checkpoint-sqlite | 支持任务中断恢复 |
| LLM 调用 | OpenAI / ChatGLM | 理解自然语言、决策规划 |

### 1.3 核心能力

1. **自然语言理解**：解析用户模糊需求（"温柔钢琴风" → 乐器=钢琴，力度=柔和）
2. **任务规划**：将复杂任务分解为有序步骤（通过 LLM 生成）
3. **工具编排**：调用原子工具完成音频处理、MIDI 生成、渲染等
4. **质量反思**：评估生成结果，决定是否需要重试
5. **多轮对话**：支持基于用户反馈迭代优化

---

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户请求                                  │
│              (上传音频 + 铃声参数 + 自然语言描述)                   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI 入口                                │
│                   POST /api/v1/tasks                             │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AgentExecutor                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              LangGraph Workflow (graph.py)               │   │
│  │                                                          │   │
│  │   ┌──────────┐    ┌──────────┐    ┌──────────┐          │   │
│  │   │ planner │───▶│ fetch_   │───▶│ analyze_ │───▶...   │   │
│  │   │         │    │ source   │    │ structure│          │   │
│  │   └──────────┘    └──────────┘    └──────────┘          │   │
│  │                                                          │   │
│  │   每个节点使用 create_react_agent 创建子 Agent            │   │
│  │   子 Agent 通过 ReAct 模式调用原子工具                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                  原子工具层 (atomic_tools/)                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐              │
│  │  analysis/  │ │   melody/   │ │    midi/    │              │
│  │  BPM,Key... │ │ BasicPitch..│ │ create,val..│              │
│  └─────────────┘ └─────────────┘ └─────────────┘              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐              │
│  │arrangement/ │ │ rendering/  │ │  quality/   │              │
│  │instrument.. │ │FluidSynth.. │ │ evaluate... │              │
│  └─────────────┘ └─────────────┘ └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
backend/app/agent/
├── __init__.py              # 模块导出
├── state.py                 # AgentState 定义、TaskStep 枚举
├── graph.py                 # LangGraph 工作流定义（节点编排）
├── nodes.py                 # 各节点处理逻辑 + NODE_HANDLERS 映射
├── agent_executor.py       # Agent 执行器入口
├── callbacks.py             # LangChain 回调处理器（思考记录）
├── thinking_utils.py        # 思考记录工具
└── atomic_tools/           # 原子工具集
    ├── __init__.py
    ├── analysis/           # 音频分析工具
    │   ├── bpm.py          # BPM 检测
    │   ├── key.py          # 调性检测
    │   ├── chords.py       # 和弦检测
    │   ├── energy.py       # 能量分析
    │   ├── spectral_centroid.py
    │   ├── sections.py     # 段落检测
    │   └── instrument_detection.py
    ├── melody/             # 旋律提取工具
    │   ├── extract_with_basic_pitch.py
    │   ├── extract_with_librosa.py
    │   ├── filter_short_notes.py
    │   └── quantize_notes.py
    ├── midi/               # MIDI 处理工具
    │   ├── create_from_notes.py
    │   ├── validate_midi.py
    │   └── set_tempo.py
    ├── arrangement/         # 改编工具
    │   ├── change_instrument.py
    │   ├── change_tempo.py
    │   └── quantize_midi.py
    ├── rendering/           # 渲染工具
    │   ├── fluidsynth_render.py
    │   ├── convert_to_mp3.py
    │   └── smart_clip.py
    └── quality/            # 质量评估工具
        ├── overall_quality.py
        ├── loudness_check.py
        ├── dynamic_range.py
        ├── spectral_balance.py
        └── zero_crossing_rate.py
```

---

## 3. 状态管理 (state.py)

### 3.1 AgentState 定义

```python
class AgentState(TypedDict, total=False):
    # 任务标识
    task_id: str
    user_id: int
    thread_id: str              # LangGraph 检查点 ID

    # 用户输入
    user_request: str           # 原始用户需求
    source_type: str            # 'upload', 'link', 'search'
    source_value: str           # 文件ID或链接
    file_id: str | None         # 上传文件的ID

    # 铃声参数
    instrument: str             # 目标乐器
    duration: int               # 时长（秒）
    tempo: int                  # 速度
    filename: str               # 文件名

    # 中间结果
    audio_path: str | None      # 音频文件路径
    analysis_result: dict | None # 音频分析结果
    melody_data: dict | None    # 旋律数据
    midi_path: str | None       # 原始 MIDI 路径
    arrangement_params: dict | None  # 改编参数
    arranged_midi_path: str | None   # 改编后 MIDI

    # 输出
    final_audio_path: str | None
    final_audio_url: str | None
    audio_duration: float | None

    # 执行状态
    current_step: TaskStep | None
    current_step_index: int
    plan: list[str]
    step_results: dict

    # 反馈与反思
    feedback_history: list[dict]
    reflection: str | None
    needs_revision: bool

    # 错误处理
    error: str | None
    retry_count: int

    # 元数据
    created_at: datetime
    updated_at: datetime
```

### 3.2 TaskStep 枚举

```python
class TaskStep(str, Enum):
    """子步骤枚举"""
    FETCH_SOURCE = "fetch_source"
    ANALYZE_STRUCTURE = "analyze_structure"
    EXTRACT_MELODY = "extract_melody"
    GENERATE_MIDI = "generate_midi"
    ARRANGE = "arrange"
    RENDER = "render"
    CHECK_QUALITY = "check_quality"
```

### 3.3 任务状态机

```
                    ┌──────────────┐
                    │   pending    │ ←─── 新建任务
                    └──────┬───────┘
                           │
                           ▼
              ┌────────────────────────┐
              │   planning → executing │
              └────────────┬───────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │completed │   │executing │   │ cancelled│
    └──────────┘   └────┬─────┘   └──────────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
         ▼              ▼              ▼
  ┌──────────┐   ┌──────────┐   ┌──────────┐
  │completed │   │waiting_  │   │  failed  │
  │ (通过)   │   │  input   │   │ (失败)   │
  └──────────┘   └──────────┘   └──────────┘
                      (用户反馈后回到 executing)
```

| 状态 | 说明 |
|------|------|
| `pending` | 任务已创建，等待调度 |
| `planning` | Agent 分析需求，制定计划 |
| `executing` | 执行中（包含多个子步骤） |
| `waiting_input` | 等待用户补充信息或反馈 |
| `completed` | 任务完成 |
| `failed` | 执行失败 |
| `cancelled` | 用户取消 |

---

## 4. 工作流设计 (graph.py)

### 4.1 LangGraph 工作流

RingTurn 使用 LangGraph 定义状态机工作流，支持：

- **节点编排**：顺序执行各处理步骤
- **条件分支**：根据执行结果决定下一步
- **循环**：质量不达标时重新执行改编步骤
- **检查点**：任务可中断、可恢复

### 4.2 节点图

```
                    ┌─────────┐
                    │ planner │
                    └────┬────┘
                         │
                         ▼
                 ┌───────────────┐
                 │ FETCH_SOURCE  │ ←── 获取上传的音频文件
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │ ANALYZE_      │ ←── 调用分析工具提取特征
                 │ STRUCTURE     │    (BPM, Key, Chords, Energy...)
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │ EXTRACT_      │ ←── 旋律提取
                 │ MELODY        │    (Basic Pitch / librosa)
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │ GENERATE_MIDI │ ←── 从音符生成 MIDI 文件
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │   ARRANGE     │ ←── 更换乐器、调整速度
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │    RENDER     │ ←── FluidSynth 渲染 + 格式转换
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │CHECK_QUALITY │ ←── 质量评估
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │    REFLECT    │ ←── 反思决策
                 └───────┬───────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │   END     │   │WAITING_  │   │  RETRY    │
   │(完成)     │   │  INPUT   │   │(重试)    │
   └──────────┘   └──────────┘   └────┬─────┘
                                       │
                              (回到 ARRANGE 重新执行)
```

### 4.3 执行流程说明

1. **planner**: 使用 LLM 生成执行计划
2. **每个节点**: 使用 `create_react_agent` 创建子 Agent，传入相关原子工具
3. **子 Agent**: 通过 ReAct 模式自主决定调用哪些工具
4. **失败重试**: `generate_midi`, `arrange`, `render` 步骤失败时自动重试
5. **质量循环**: 质量不达标时，重新执行改编和渲染步骤

---

## 5. 节点处理 (nodes.py)

### 5.1 节点处理器映射

```python
NODE_HANDLERS = {
    TaskStep.FETCH_SOURCE.value: fetch_source_node,
    TaskStep.ANALYZE_STRUCTURE.value: analyze_structure_node,
    TaskStep.EXTRACT_MELODY.value: extract_melody_node,
    TaskStep.GENERATE_MIDI.value: generate_midi_node,
    TaskStep.ARRANGE.value: arrange_node,
    TaskStep.RENDER.value: render_node,
    TaskStep.CHECK_QUALITY.value: check_quality_node,
}
```

### 5.2 各节点职责

| 节点 | 子 Agent 工具 | 说明 |
|------|--------------|------|
| `fetch_source_node` | - | 验证上传文件，初始化 audio_path |
| `analyze_structure_node` | get_bpm, get_key, get_spectral_centroid, get_rms_energy, extract_chord_progression, detect_instruments | 提取 BPM、调性、和弦、乐器等 |
| `extract_melody_node` | extract_melody_basic_pitch, extract_melody_librosa, filter_short_notes, quantize_notes | 提取主旋律音符 |
| `generate_midi_node` | create_midi_from_notes | 从音符生成 MIDI |
| `arrange_node` | change_instrument, change_tempo, quantize_midi | 更换乐器、调整速度 |
| `render_node` | render_midi_with_fluidsynth, convert_wav_to_mp3, smart_clip_audio | 渲染并截取 |
| `check_quality_node` | evaluate_overall_quality | 综合质量评估 |

### 5.3 子 Agent Prompt 设计

每个节点使用结构化 Prompt，引导 LLM 按 `[思考]` → 工具调用 → 结果 的格式执行：

```
**你必须严格遵守以下交互格式：**
在每次调用任何工具之前，先输出一句中文说明，格式为："[思考] 我接下来将使用 <工具名>，因为 <原因>。"
然后调用工具。
完成所有工具调用后，再单独输出最终的 JSON 结果。
**绝对不要省略 `[思考]` 行！**

示例：
[思考] 我接下来将使用 get_bpm，因为需要知道歌曲速度。
（随后调用 get_bpm 工具）
[思考] 我接下来将使用 get_key，因为需要确定调性以便后续改编。
（随后调用 get_key 工具）
最终 JSON 结果：
{"bpm": 120, "key": "C Major", ...}
```

---

## 6. 原子工具 (atomic_tools/)

### 6.1 工具分类

#### 分析工具 (analysis/)

| 工具 | 功能 |
|------|------|
| `get_bpm_tool` | 检测 BPM |
| `get_key_tool` | 检测调性 |
| `get_spectral_centroid_tool` | 频谱质心 |
| `get_rms_energy_tool` | RMS 能量 |
| `extract_chord_progression_tool` | 和弦进行 |
| `detect_instruments_tool` | 乐器检测 |
| `get_sections_tool` | 段落检测 |

#### 旋律工具 (melody/)

| 工具 | 功能 |
|------|------|
| `extract_melody_basic_pitch_tool` | Basic Pitch 深度学习提取 |
| `extract_melody_librosa_tool` | librosa 峰值提取（降级） |
| `filter_short_notes_tool` | 过滤短音符 |
| `quantize_notes_tool` | 量化音符到网格 |

#### MIDI 工具 (midi/)

| 工具 | 功能 |
|------|------|
| `create_midi_from_notes_tool` | 从音符创建 MIDI |
| `validate_midi_file_tool` | 验证 MIDI 文件 |
| `set_tempo_tool` | 设置速度 |

#### 改编工具 (arrangement/)

| 工具 | 功能 |
|------|------|
| `change_instrument_tool` | 更换乐器 |
| `change_tempo_tool` | 调整速度 |
| `quantize_midi_tool` | MIDI 量化 |

#### 渲染工具 (rendering/)

| 工具 | 功能 |
|------|------|
| `render_midi_with_fluidsynth_tool` | FluidSynth 渲染 |
| `convert_wav_to_mp3_tool` | WAV 转 MP3 |
| `smart_clip_audio_tool` | 智能截取 |

#### 质量工具 (quality/)

| 工具 | 功能 |
|------|------|
| `evaluate_overall_quality_tool` | 综合质量评估 |
| `loudness_check_tool` | 响度检查 |
| `dynamic_range_tool` | 动态范围 |
| `spectral_balance_tool` | 频谱平衡 |
| `zero_crossing_rate_tool` | 过零率 |

### 6.2 降级策略

```python
# 旋律提取降级示例
step_tools = [
    extract_melody_basic_pitch_tool,   # 优先使用 Basic Pitch
    extract_melody_librosa_tool,       # 备选
    filter_short_notes_tool,
    quantize_notes_tool,
]

# 如果子 Agent 失败，降级到直接调用
melody_data = await extract_melody_librosa(audio_path)
```

---

## 7. 回调机制 (callbacks.py)

### 7.1 ThinkingCallbackHandler

```python
class ThinkingCallbackHandler(AsyncCallbackHandler):
    """LangChain 异步回调处理器"""

    async def on_llm_start(self, ...):
        record_thought(task_id, step, "开始调用 LLM...")

    async def on_llm_end(self, response, ...):
        # 提取 LLM 输出并记录
        for gen in response.generations:
            text = gen.message.content
            record_thought(task_id, step, f"[LLM 思考] {text[:500]}")

    async def on_tool_start(self, serialized, input_str, ...):
        record_thought(task_id, step, f"调用工具: {name}")

    async def on_tool_end(self, output, ...):
        record_thought(task_id, step, f"工具返回: {content[:200]}")
```

### 7.2 思考记录存储

思考记录存储在数据库 `Task.thinking_process` JSON 字段中，可通过 WebSocket 实时推送给前端展示。

---

## 8. 执行器 (agent_executor.py)

### 8.1 AgentExecutor 类

```python
class AgentExecutor:
    """Agent 执行入口"""

    async def execute(self) -> dict:
        # 1. 规划阶段
        await self._update_task_status(TaskStatus.planning)
        await self._plan()

        # 2. 执行阶段
        await self._update_task_status(TaskStatus.executing)
        await self._execute_steps()

        # 3. 完成
        await self._update_task_status(TaskStatus.completed)

    async def execute_optimization(self, feedback: str) -> dict:
        """基于用户反馈的优化"""
        # 添加反馈到历史
        self.state["feedback_history"].append({...})

        # 重新执行改编和渲染步骤
        await self._execute_step(TaskStep.ARRANGE.value)
        await self._execute_step(TaskStep.RENDER.value)
        await self._execute_step(TaskStep.CHECK_QUALITY.value)
```

### 8.2 步骤执行

```python
async def _execute_step(self, step: str) -> None:
    handler = NODE_HANDLERS.get(step)
    if not handler:
        raise ValueError(f"未知步骤: {step}")

    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            await handler(self.state, self.db, None)
            return
        except Exception as e:
            if attempt < max_attempts - 1 and step in ("generate_midi", "arrange", "render"):
                continue  # 重试
            raise
```

---

## 9. LLM 集成 (services/llm_service.py)

### 9.1 LLMService 类

```python
class LLMService:
    async def chat(self, messages, model, temperature, max_tokens) -> str:
        """带重试的 LLM 调用"""

    async def parse_user_request(self, user_request: str) -> dict:
        """解析用户需求"""

    async def generate_plan(self, user_request: str) -> list[str]:
        """生成执行计划"""

    async def reflect_on_quality(self, quality_result: dict, user_request: str) -> dict:
        """反思质量评估结果"""

def get_llm():
    """返回 LangChain 兼容的 ChatOpenAI 实例"""
    return ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=0.7,
        max_retries=5,
    )
```

---

## 10. 扩展指南

### 10.1 添加新原子工具

1. 在对应目录创建工具文件：

```python
# app/agent/atomic_tools/analysis/my_tool.py
from langchain_core.tools import tool

@tool
def my_analysis_tool(audio_path: str) -> dict:
    """我的分析工具"""
    # 实现逻辑
    return {"result": "value"}
```

2. 在 `__init__.py` 中导出：

```python
# app/agent/atomic_tools/analysis/__init__.py
from .my_tool import my_analysis_tool
my_new_tool = my_analysis_tool
```

3. 在 `nodes.py` 的对应节点中引入并使用

### 10.2 添加新节点

1. 在 `state.py` 的 `TaskStep` 枚举添加步骤

2. 在 `nodes.py` 实现节点处理器

3. 在 `nodes.py` 的 `NODE_HANDLERS` 映射中添加

4. 在 `graph.py` 中连接新节点

### 10.3 接入外部 API

1. 在 `.env` 中添加配置

2. 在 `atomic_tools/` 中创建对应的工具封装

---

## 11. 数据库模型

### Task 表关键字段

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(36) | UUID 主键 |
| user_id | Integer | 关联用户 |
| user_request | Text | 用户需求 |
| source_type | String | 'upload', 'link', 'search' |
| source_value | String | 文件ID或链接 |
| ringtone_params | JSON | 铃声参数 |
| status | Enum | 任务状态 |
| plan | JSON | 执行计划 |
| thinking_process | JSON | 思考记录 |
| final_audio_url | String | 输出URL |
| error_message | Text | 错误信息 |
