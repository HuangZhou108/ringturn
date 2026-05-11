import json
from pathlib import Path
from sqlalchemy.orm import Session
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.llm_service import get_llm
from app.agent.state import AgentState
from app.core.config import get_settings
from app.agent.atomic_tools.arrangement import (
    change_instrument_tool, change_tempo_tool, quantize_midi_tool
)
from ..callbacks import ThinkingCallbackHandler
import mido
settings = get_settings()

async def arrange_node(state: AgentState, db: Session, tools) -> None:
    """
    节点5: 乐器改编

    根据用户需求更换乐器、调整风格
    """
    midi_path = state["midi_path"].replace("\\", "/")
    target_instrument = state.get("instrument", "piano")
    user_tempo = state.get("tempo")
    task_id = state["task_id"]
    task_dir = Path(settings.RINGTONES_DIR) / task_id
    output_path = str(task_dir / "arrange_arranged.mid").replace("\\", "/")

    step_tools = [change_instrument_tool, change_tempo_tool, quantize_midi_tool]
    system_prompt = f"""你是一个音乐改编专家。你需要严格按照以下步骤操作：：
**固定变量（不得修改）**：
- 输入 MIDI：`{midi_path}`
- 目标乐器：`{target_instrument}`
- 用户指定速度: {user_tempo if user_tempo else '保持原速'}
- 最终输出路径（必须使用）：`{output_path}`

**工作流**：
1. 调用 `change_instrument`，传入 midi_path、target_instrument 和 output_path。
2. 如果需要调整速度，再调用 `change_tempo`（输入为上一步的输出路径，输出路径自行拼接，但必须基于 output_path 所在目录）。
3. 可选调用 `quantize_midi`量化。

**你必须严格遵守以下交互格式：**
在开始调用任何工具之前，先输出一段中文说明，格式为：“我接下来将使用 <工具名> 用来 <用途>，使用 <工具名> 用来 <用途>，...，因为 <原因>。”
然后调用工具。
完成所有工具调用后，再单独输出最终的 JSON 结果。
在输出JSON结果以后对结果进行思考与总结。
**绝对不要省略以上任何交互流程！**

示例：
我接下来将使用 change_instrument 用于将乐器修改为 {target_instrument}，使用 change_tempo将速度修改为{user_tempo} BPM，因为用户要求将乐器更换为 {target_instrument}，指定速度为 {user_tempo} BPM。
（随后调用工具）
最终 JSON 结果：
{{"arranged_midi_path": "{output_path}"}}
根据结果，我们已经将乐器修改为钢琴，速度修改为xxBPM，基本完成了用户要求。
"""
    llm = get_llm()
    callback = ThinkingCallbackHandler(task_id, "arrange")
    sub_agent = create_react_agent(llm, step_tools)
    await sub_agent.ainvoke(
        {"messages": [SystemMessage(content=system_prompt), HumanMessage(content="开始改编。")]},
        config={"callbacks": [callback]}
    )

    # 验证改编后的 MIDI 文件
    if not Path(output_path).exists():
        raise RuntimeError(f"改编失败：输出文件不存在 {output_path}")
    try:
        mido.MidiFile(output_path)
    except Exception as e:
        raise RuntimeError(f"改编后的 MIDI 无效: {e}")
    state["arranged_midi_path"] = output_path
