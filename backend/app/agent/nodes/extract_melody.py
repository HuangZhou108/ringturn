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
    separate_vocals_tool,
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
        separate_vocals_tool,
    ]
    system_prompt = f"""你是一个旋律提取专家。请从音频文件 `{audio_path}` 中提取主旋律。
你可以使用工具：
- extract_melody_basic_pitch: 使用深度学习模型提取旋律（推荐，精度更高）
- extract_melody_librosa: 提取音符列表并生成 MIDI（仅当 Basic Pitch 失败或返回空结果时作为备用）
- filter_short_notes: 过滤短音符（需提供音符列表和最小时长）
- quantize_notes: 量化音符（需提供音符列表、网格大小、BPM）
- separate_vocals_tool：分离人声，为音频提取提供更好的原料。

用户需求：{state["user_request"]}

**关键规则（必须严格遵守）**：
0. **首先必须调用 separate_vocals 工具分离人声，然后使用分离后的人声文件路径进行后续操作。**
1. **首先必须调用 extract_melody_basic_pitch**。
2. **如果 extract_melody_basic_pitch 返回了 melody_notes 且长度大于 0，则必须立即输出最终 JSON，绝对不能调用 extract_melody_librosa 或任何其他工具。**
3. 仅在 extract_melody_basic_pitch 失败（返回空 melody_notes 或出错）时，才允许调用 extract_melody_librosa 作为备用。
4. 不要重复调用同一个提取工具。
最终输出 JSON 格式：
{{
    "melody_notes": list[dict],  # 每个音符 {{"pitch": int, "start": float, "end": float, "velocity": int, "confidence": float}}
    "confidence": float,
    "midi_path": str            # 提取的 MIDI 文件路径
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
    # 解析结果
    try:
        melody_data = json.loads(resp["messages"][-1].content)
        print(f"[extract_melody] LLM 返回 melody_data: {melody_data}")
    except Exception as e:
        print(f"[WARN] JSON 解析失败: {e}，启用降级逻辑")
        melody_data = None

    # 降级/覆盖保护逻辑
    if not melody_data or not melody_data.get("melody_notes"):
        print("[WARN] 子 Agent 未返回有效 melody_notes，尝试直接调用 Basic Pitch 降级...")
        try:
            from app.agent.atomic_tools.melody.extract_with_basic_pitch import extract_melody_basic_pitch
            melody_data = await extract_melody_basic_pitch(audio_path)
            print(f"[降级] Basic Pitch 降级成功，音符数: {len(melody_data['melody_notes'])}")
        except Exception as bp_err:
            print(f"[ERROR] Basic Pitch 降级失败: {bp_err}，使用 librosa 降级")
            from app.agent.atomic_tools.melody.extract_with_librosa import extract_melody_librosa
            melody_data = await extract_melody_librosa(audio_path)

    # 确保 meloy_data 包含 midi_path
    if "midi_path" not in melody_data:
        # 尝试从 Basic Pitch 结果中提取（从工具返回可能已丢失，此时从常见位置推断）
        import os
        possible_midi = audio_path.replace(".mp3", "_melody.mid").replace(".wav", "_melody.mid")
        if os.path.exists(possible_midi):
            melody_data["midi_path"] = possible_midi
        else:
            melody_data["midi_path"] = ""  # 后续 generate_midi 会重建

    state["melody_data"] = melody_data
