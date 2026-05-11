"""
Agent节点处理逻辑

每个节点负责一个执行步骤的具体实现
"""

import json
from pathlib import Path
from sqlalchemy.orm import Session
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent
from app.services.llm_service import get_llm
from .callbacks import ThinkingCallbackHandler
from app.core.config import get_settings
from app.services.file_service import file_service
from app.agent.state import AgentState, TaskStep
import mido

# 导入所有原子工具
from app.agent.atomic_tools.analysis import (
    get_bpm_tool, get_key_tool, get_spectral_centroid_tool,
    get_rms_energy_tool, extract_chord_progression_tool,
    detect_instruments_tool
)
from app.agent.atomic_tools.melody import (
    extract_melody_basic_pitch_tool, extract_melody_librosa_tool, filter_short_notes_tool, quantize_notes_tool
)
from app.agent.atomic_tools.midi import (
    create_midi_from_notes_tool, validate_midi_file_tool
)
from app.agent.atomic_tools.arrangement import (
    change_instrument_tool, change_tempo_tool, quantize_midi_tool
)
from app.agent.atomic_tools.rendering import (
    render_midi_with_fluidsynth_tool, convert_wav_to_mp3_tool, smart_clip_audio_tool
)
from app.agent.atomic_tools.quality import (
    evaluate_overall_quality_tool
)


settings = get_settings()

async def fetch_source_node(state: AgentState, db: Session, tools) -> None:
    """
    节点1: 获取音频源

    根据source_type获取音频文件
    """
    source_type = state.get("source_type", "upload")
    source_value = state.get("source_value")

    if source_type == "upload":
        # 获取上传文件
        if not source_value:
            raise ValueError("上传类型需要提供source_value（文件ID）")

        file_path = file_service.get_upload_path(source_value)
        if not file_path:
            raise ValueError(f"文件不存在: {source_value}")
        
        # 尝试加载音频文件，验证是否可读
        try:
            import librosa
            # 仅加载前 1 秒进行快速验证
            y, sr = librosa.load(str(file_path), duration=1, sr=22050)
            if y is None or len(y) == 0:
                raise RuntimeError("音频文件内容为空")
        except Exception as e:
            raise RuntimeError(f"无法打开或解析上传的音频文件: {e}")

        state["audio_path"] = str(file_path)

    elif source_type == "search":
        # TODO: 实现搜索功能
        raise NotImplementedError("search类型暂未实现")

    else:
        raise ValueError(f"不支持的source_type: {source_type}")

async def analyze_structure_node(state: AgentState, db: Session, tools) -> None:
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
在每次调用任何工具之前，先输出一句中文说明，格式为：“[思考] 我接下来将使用 <工具名>，因为 <原因>。”
然后调用工具。
完成所有工具调用后，再单独输出最终的 JSON 结果。
**绝对不要省略 `[思考]` 行！**

示例：
[思考] 我接下来将使用 get_bpm，因为需要知道歌曲速度。
（随后调用 get_bpm 工具）
[思考] 我接下来将使用 get_key，因为需要确定调性以便后续改编。
（随后调用 get_key 工具）
最终 JSON 结果：
{{"bpm": 120, "key": "C Major", ...}}
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
        print(f"[NODE DEBUG] final_response type: {type(final_response)}")
        print(f"[NODE DEBUG] messages count: {len(final_response.get('messages', []))}")
        for i, msg in enumerate(final_response.get('messages', [])):
            print(f"[NODE DEBUG] msg[{i}] type={type(msg).__name__}, content={str(msg.content)[:100]}")
        last_msg = final_response["messages"][-1].content
        analysis_result = json.loads(last_msg)
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
在每次调用任何工具之前，先输出一句中文说明，格式为：“[思考] 我接下来将使用 <工具名>，因为 <原因>。”
然后调用工具。
完成所有工具调用后，再单独输出最终的 JSON 结果。
**绝对不要省略 `[思考]` 行！**

示例：
[思考] 我接下来将使用 extract_melody_basic_pitch，因为它是精度最高的深度学习模型。
（随后调用 extract_melody_basic_pitch 工具）
[思考] 我接下来将使用 filter_short_notes，因为需要去除过短的杂音音符。
（随后调用 filter_short_notes 工具，并传入上一步得到的音符列表）
[思考] 我接下来将使用 quantize_notes，因为需要将音符对齐到节拍网格。
（随后调用 quantize_notes 工具）
最终 JSON 结果：
{{"melody_notes": [...], "confidence": 0.8, "midi_path": "/path/to/output.mid"}}
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

async def generate_midi_node(state: AgentState, db: Session, tools) -> None:
    """
    节点4: 生成MIDI

    根据旋律和分析结果生成原始MIDI文件

    由于步骤固定，不再调用大模型。
    """
    melody_data = state["melody_data"]
    analysis_result = state["analysis_result"]
    task_id = state["task_id"]
    # 创建任务专属目录
    task_dir = Path(settings.RINGTONES_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(task_dir / "generate_midi_original.mid")

    # 直接调用工具函数，避免LLM token限制导致失败
    from app.agent.atomic_tools.midi.create_from_notes import create_midi_from_notes
    await create_midi_from_notes(
        notes=melody_data.get("melody_notes", []),
        bpm=analysis_result.get("bpm", 120),
        output_path=output_path
    )
    
    # 验证文件是否生成成功
    output_path_obj = Path(output_path)
    if not output_path_obj.exists():
        raise RuntimeError("MIDI 文件生成失败：文件不存在")
    if output_path_obj.stat().st_size == 0:
        raise RuntimeError("MIDI 文件生成失败：文件为空")
    try:
        mido.MidiFile(output_path)
    except Exception as e:
        raise RuntimeError(f"MIDI 文件无效: {e}")
    
    state["midi_path"] = output_path

async def arrange_node(state: AgentState, db: Session, tools) -> None:
    """
    节点5: 乐器改编

    根据用户需求更换乐器、调整风格
    """
    midi_path = state["midi_path"]
    target_instrument = state.get("instrument", "piano")
    user_tempo = state.get("tempo")
    task_id = state["task_id"]
    task_dir = Path(settings.RINGTONES_DIR) / task_id
    output_path = str(task_dir / "arrange_arranged.mid")

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

async def render_node(state: AgentState, db: Session, tools) -> None:
    """
    节点6: 渲染音频

    将改编后的MIDI渲染为音频文件
    """
    midi_path = state.get("arranged_midi_path") or state.get("midi_path")
    if not Path(midi_path).exists():
        raise FileNotFoundError(f"渲染输入 MIDI 不存在: {midi_path}")
    target_duration = state.get("duration", settings.DEFAULT_RINGTONE_DURATION)
    task_id = state["task_id"]
    task_dir = Path(settings.RINGTONES_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    user_filename = state.get("filename", "ringtone")
    # safe_filename = "".join(c for c in user_filename if c.isalnum() or c in "._- ") or task_id
    mp3_path = str(task_dir / f"{user_filename}.mp3")
    wav_path = str(task_dir / "render_temp.wav")
    soundfont = settings.SOUNDFONT_PATH

    step_tools = [render_midi_with_fluidsynth_tool, convert_wav_to_mp3_tool, smart_clip_audio_tool]
    system_prompt = f"""将 MIDI 渲染为 MP3 铃声。
MIDI 路径: {midi_path}
音色库: {soundfont}
目标长度: {target_duration} 秒
输出文件: {mp3_path}

工作流：
1. 调用 render_midi_with_fluidsynth 生成临时 WAV（路径 {wav_path}，duration_limit={target_duration}）
2. 调用 convert_wav_to_mp3 将 WAV 转为 MP3
3. 调用 smart_clip_audio 截取到目标时长（如果生成长度超过目标）

**你必须严格遵守以下交互格式：**
在每次调用任何工具之前，先输出一句中文说明，格式为：“[思考] 我接下来将使用 <工具名>，因为 <原因>。”
然后调用工具。
完成所有工具调用后，再单独输出最终的 JSON 结果。
**绝对不要省略 `[思考]` 行！**

示例：
[思考] 我接下来将使用 render_midi_with_fluidsynth，因为需要将 MIDI 渲染为音频。
（随后调用 render_midi_with_fluidsynth 工具）
[思考] 我接下来将使用 convert_wav_to_mp3，因为需要转换为 MP3 格式。
（随后调用 convert_wav_to_mp3 工具）
[思考] 我接下来将使用 smart_clip_audio，因为需要截取到目标时长 {target_duration} 秒。
（随后调用 smart_clip_audio 工具）
最终 JSON 结果：
{{"final_audio_path": "{mp3_path}", "audio_duration": 30.0}}
"""
    llm = get_llm()
    callback = ThinkingCallbackHandler(task_id, "render")
    sub_agent = create_react_agent(llm, step_tools)
    resp = await sub_agent.ainvoke(
        {"messages": [SystemMessage(content=system_prompt), HumanMessage(content="渲染音频。")]},
        config={"callbacks": [callback]}
    )
    try:
        result = json.loads(resp["messages"][-1].content)
        final_path = result.get("final_audio_path", mp3_path)
        duration = result.get("audio_duration", target_duration)
    except:
        final_path = mp3_path
        duration = target_duration
    # 验证最终音频文件是否存在
    if not Path(mp3_path).exists():
        raise RuntimeError(f"渲染失败：最终音频文件不存在 {mp3_path}")
    if Path(mp3_path).stat().st_size == 0:
        raise RuntimeError(f"渲染失败：最终音频文件为空 {mp3_path}")
    state["final_audio_path"] = mp3_path
    state["audio_duration"] = duration
    state["final_audio_url"] = f"/static/ringtones/{task_id}/{Path(mp3_path).name}"

async def check_quality_node(state: AgentState, db: Session, tools) -> None:
    """
    节点7: 质量检查

    评估生成音频的质量
    """
    audio_path = state["final_audio_path"]
    task_id = state["task_id"]
    step_tools = [evaluate_overall_quality_tool]  # 也可以包含单个指标工具，但综合工具更高效
    system_prompt = f"""评估音频质量：{audio_path}
调用 evaluate_overall_quality_tool 获得质量报告。

**你必须严格遵守以下交互格式：**
在调用工具之前，先输出一句中文说明，格式为：“[思考] 我接下来将使用 <工具名>，因为 <原因>。”
然后调用工具。
完成工具调用后，再单独输出最终的 JSON 结果。
**绝对不要省略 `[思考]` 行！**

示例：
[思考] 我接下来将使用 evaluate_overall_quality_tool，因为需要综合评估音频的响度、频谱平衡、动态范围等指标。
（随后调用 evaluate_overall_quality_tool 工具）
最终 JSON 结果：
{{"overall_score": 4.2, "quality_issues": [], "passed": true, ...}}
"""
    llm = get_llm()
    callback = ThinkingCallbackHandler(task_id, "check_quality")
    sub_agent = create_react_agent(llm, step_tools)
    resp = await sub_agent.ainvoke(
        {"messages": [SystemMessage(content=system_prompt), HumanMessage(content="评估质量。")]},
        config={"callbacks": [callback]}
    )
    # 强制检查是否调用了工具
    messages = resp.get("messages", [])
    tool_called = any(isinstance(m, ToolMessage) for m in messages)
    if not tool_called:
        raise RuntimeError("质量检查失败：未调用评估工具，LLM 可能直接编造了结果")
    
    try:
        quality = json.loads(resp["messages"][-1].content)
    except:
        raise RuntimeError("质量检查结果解析失败")
    
    # 验证必要字段
    if "overall_score" not in quality:
        raise RuntimeError("质量检查结果缺少 overall_score")
    if not quality.get("passed", False):
        state["needs_revision"] = True
        state["reflection"] = {"message": "质量不达标", "adjustments": {}}
    state["step_results"]["quality_check"] = quality

# 节点处理器映射（使用字符串键，与TaskStep枚举的value一致）
NODE_HANDLERS = {
    TaskStep.FETCH_SOURCE.value: fetch_source_node,
    TaskStep.ANALYZE_STRUCTURE.value: analyze_structure_node,
    TaskStep.EXTRACT_MELODY.value: extract_melody_node,
    TaskStep.GENERATE_MIDI.value: generate_midi_node,
    TaskStep.ARRANGE.value: arrange_node,
    TaskStep.RENDER.value: render_node,
    TaskStep.CHECK_QUALITY.value: check_quality_node,
}
