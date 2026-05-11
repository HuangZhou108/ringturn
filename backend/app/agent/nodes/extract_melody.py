# nodes/extract_melody.py
import json
from sqlalchemy.orm import Session
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.llm_service import get_llm
from app.core.config import get_settings
from app.agent.state import AgentState
from app.agent.atomic_tools.melody import (
    extract_melody_basic_pitch_tool,
    extract_melody_librosa_tool,
    filter_short_notes_tool,
    quantize_notes_tool,
)
from ..callbacks import ThinkingCallbackHandler

async def extract_melody_node(state: AgentState, db: Session, tools) -> None:
    """
    节点3: 提取主旋律

    提取音频中的主旋律数据
    """
    audio_path = state["audio_path"]
    task_id = state["task_id"]
    step_tools = [
        extract_melody_basic_pitch_tool,   # 优先使用 Basic Pitch
        extract_melody_librosa_tool,       # 备选
        filter_short_notes_tool,
        quantize_notes_tool,
    ]
    system_prompt = f"""你是一个旋律提取专家。请从音频文件 `{audio_path}` 中提取主旋律。
你可以使用工具：
- extract_melody_basic_pitch: 使用深度学习模型提取旋律（推荐，精度更高）
- extract_melody_librosa: 提取音符列表并生成 MIDI（作为basic_pitch的降级方案）
- filter_short_notes: 过滤短音符（需提供音符列表和最小时长）
- quantize_notes: 量化音符（需提供音符列表、网格大小、BPM）

用户需求：{state["user_request"]}

请按顺序调用工具，最终输出一个 JSON 对象：
{{
    "melody_notes": list[dict],  # 每个音符 {{"pitch": int, "start": float, "end": float, "velocity": int, "confidence": float}}
    "confidence": float,
    "midi_path": str   # 提取的 MIDI 文件路径
}}
**你必须严格遵守以下交互格式：**
在调用任何工具之前，先输出一段中文说明，格式为：“我接下来将使用 <工具名>，因为 <原因>。”
然后调用工具。
完成所有工具调用后，再单独输出最终的 JSON 结果。
最后再输出一段中文说明，总结JSON结果。
**绝对不要省略自然语言思考内容！**

示例：
我接下来将使用 extract_melody_basic_pitch，因为它是精度最高的深度学习模型；将使用 filter_short_notes，因为需要去除过短的杂音音符，以保证音乐质量；最后将使用 quantize_notes，因为需要将音符对齐到节拍网格。。
（随后调用 extract_melody_basic_pitch 工具）
（随后调用 filter_short_notes 工具，并传入上一步得到的音符列表）
（随后调用 quantize_notes 工具）
最终 JSON 结果：
{{"melody_notes": [...], "confidence": 0.8, "midi_path": "/path/to/output.mid"}}
已完成旋律提取，共提取x个音符。
"""

    llm = get_llm()
    callback = ThinkingCallbackHandler(task_id, "extract_melody")
    sub_agent = create_react_agent(llm, step_tools)
    resp = await sub_agent.ainvoke(
        {"messages": [SystemMessage(content=system_prompt), HumanMessage(content="开始提取旋律。")]},
        config={"callbacks": [callback]}
    )
    try:
        melody_data = json.loads(resp["messages"][-1].content)
    except:
        # 降级：直接调用基础提取
        from app.agent.atomic_tools.melody.extract_with_librosa import extract_melody_librosa
        melody_data = await extract_melody_librosa(audio_path)
    state["melody_data"] = melody_data
