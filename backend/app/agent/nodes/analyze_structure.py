import json
from sqlalchemy.orm import Session
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.llm_service import get_llm
from app.agent.state import AgentState
from app.agent.atomic_tools.analysis import (
    get_bpm_tool, get_key_tool, get_spectral_centroid_tool,
    get_rms_energy_tool, extract_chord_progression_tool,
    detect_instruments_tool
)
from ..callbacks import ThinkingCallbackHandler
from app.agent.utils import clean_state, extract_json_from_response

@clean_state
async def analyze_structure_node(state: AgentState) -> dict:
    """
    节点2: 分析音乐结构

    调用分析API提取BPM、调性、段落等
    """
    audio_path = state["audio_path"]
    user_request = state["user_request"]
    task_id = state["task_id"]

    step_tools = [
        get_bpm_tool,
        get_key_tool,
        get_spectral_centroid_tool,
        get_rms_energy_tool,
        extract_chord_progression_tool,
        detect_instruments_tool,
    ]

    system_prompt = f"""你是一个音乐分析专家。当前用户需求：{user_request}
你需要分析音频文件 `{audio_path}` 的音乐特征。你可以使用的工具有：
{', '.join([t.name for t in step_tools])}

请根据用户需求，决定需要提取哪些特征。依次调用必要的工具。
要成功改编一首歌，你至少要知道歌曲速度和其所使用的乐器。
完成所有调用后，请输出一个 JSON 对象，包含以下字段（如果某个特征未提取，可以省略或设为 null）：
{{
    "bpm": float,
    "key": str,
    "spectral_centroid": float,
    "rms_energy": float,
    "chords": list[dict],  # 每个元素 {{"start": float, "end": float, "chord": str}}
    "instruments": list[str]
}}
**你必须严格遵守以下交互格式：**
在调用任何工具之前，先输出一段中文说明，包括你接下来要使用的所有工具以及你使用这些工具的原因。
然后调用工具。
完成所有工具调用后，再单独输出最终的 JSON 结果。
最后用一句话的中文说明总结你所得到的结果。
**绝对不要省略自然语言思考内容！**

示例：
我接下来将使用 get_bpm，因为需要知道歌曲速度。我接下来将使用 get_key，因为需要确定调性以便后续改编。
（随后调用 get_bpm 工具）
（随后调用 get_key 工具）
最终 JSON 结果：
{{"bpm": 120, "key": "C Major", ...}}
我们分析得到歌曲bpm未120，所使用调性未C大调。
"""

    llm = get_llm()
    callback = ThinkingCallbackHandler(task_id, "analyze_structure")
    sub_agent = create_react_agent(llm, step_tools, checkpointer=None)  # 不需要检查点

    try:
        final_response = await sub_agent.ainvoke(
            {"messages": [SystemMessage(content=system_prompt), HumanMessage(content="请开始分析。")]},
            config={"callbacks": [callback]}
        )
        # 调试输出
        # print(f"[NODE DEBUG] final_response type: {type(final_response)}")
        # print(f"[NODE DEBUG] messages count: {len(final_response.get('messages', []))}")
        # for i, msg in enumerate(final_response.get('messages', [])):
        #     print(f"[NODE DEBUG] msg[{i}] type={type(msg).__name__}, content={str(msg.content)[:100]}")
        last_msg = final_response["messages"][-1].content
        analysis_result = extract_json_from_response(last_msg)
    except Exception as e:
        # 降级：使用默认值
        print(f"[WARN] analyze_structure_node 子Agent失败: {e}，使用默认分析结果")
        analysis_result = {
            "bpm": 120,
            "key": "C Major",
            "spectral_centroid": 1500,
            "rms_energy": 0.1,
            "chords": [],
            "instruments": ["piano"]
        }

    state["analysis_result"] = analysis_result
    # 可选：额外提取 duration 和 sections
    import librosa
    y, sr = librosa.load(audio_path, sr=22050)
    state["analysis_result"]["duration"] = librosa.get_duration(y=y, sr=sr)
    # sections 可以单独使用 detect_sections_tool，但为了简化，此处省略

    # analysis_result = convert_numpy_to_native(analysis_result)
    return {"analysis_result": analysis_result}