# app/agent/atomic_tools/analysis/mood_style.py
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from app.services.llm_service import llm_service
import json

async def infer_mood_and_style(audio_path: str, user_request: str, features: dict = None) -> dict:
    # 构建提示词
    prompt = f"""用户需求：{user_request}
音频特征摘要：{json.dumps(features, ensure_ascii=False) if features else "无"}
请推断该音频的情绪（如 happy, sad, energetic, calm）、风格流派（如 pop, rock, lo-fi, classical）、能量等级（1-10）、年代提示（如 80s, 2010s）。
只输出 JSON，格式：{{"mood": str, "genre": str, "energy_level": int, "era_hint": str}}"""
    response = await llm_service.chat([{"role": "user", "content": prompt}], temperature=0.3)
    try:
        result = json.loads(response)
    except:
        result = {"mood": "neutral", "genre": "pop", "energy_level": 5, "era_hint": "unknown"}
    return result

class MoodStyleInput(BaseModel):
    audio_path: str = Field(description="音频文件路径")
    user_request: str = Field(description="用户请求文本")
    features: dict = Field(default=None, description="可选的音频特征摘要")

infer_mood_style_tool = StructuredTool.from_function(
    coroutine=infer_mood_and_style,
    name="infer_mood_and_style",
    description="根据音频和用户请求推断情绪、风格、能量、年代",
    args_schema=MoodStyleInput
)