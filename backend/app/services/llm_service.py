"""
LLM服务模块

封装与语言模型的交互，用于：
- 需求理解与参数提取
- 执行计划生成
- 反思与决策
"""

import os
import asyncio
from typing import Optional
from openai import AsyncOpenAI, RateLimitError
from app.core.config import get_settings

settings = get_settings()

# 重试配置
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 2  # 初始重试延迟（秒）
MAX_RETRY_DELAY = 60  # 最大重试延迟（秒）


class LLMService:
    """LLM服务封装"""

    def __init__(self):
        self.client = None
        self._init_client()

    def _init_client(self):
        """初始化LLM配置"""
        api_key = settings.LLM_API_KEY or os.getenv("LLM_API_KEY")
        base_url = settings.LLM_BASE_URL or os.getenv("LLM_BASE_URL")

        if not api_key:
            raise ValueError("LLM_API_KEY未配置")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url if base_url else None,
        )

    async def chat(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        """
        调用LLM进行对话（带重试机制）

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称（默认使用配置）
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            str: LLM响应内容
        """
        if not self.client:
            self._init_client()

        model = model or settings.LLM_MODEL
        last_error = None

        for attempt in range(MAX_RETRIES):
            # 检查当前任务是否被取消
            if asyncio.current_task() and asyncio.current_task().cancelled():
                raise asyncio.CancelledError()
            try:
                print(f"[LLM REQUEST] model={model}, base_url={self.client.base_url}")
                print(f"[LLM REQUEST] messages={messages}")

                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                print(f"[LLM RESPONSE] {response}")
                return response.choices[0].message.content
            except asyncio.CancelledError:
                raise
            except RateLimitError as e:
                last_error = e
                # 计算指数退避延迟
                delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                print(f"[LLM RATE LIMIT] 触发限流，等待 {delay:.2f} 秒后重试 (尝试 {attempt + 1}/{MAX_RETRIES})")
                print(f"[LLM RATE LIMIT] 错误详情: {e}")
                await asyncio.sleep(delay)

            except Exception as e:
                last_error = e
                # 其他错误也尝试重试，但只重试3次
                if attempt < 2:
                    delay = INITIAL_RETRY_DELAY * (2 ** attempt)
                    print(f"[LLM ERROR] 请求失败，等待 {delay:.1f} 秒后重试 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
                    await asyncio.sleep(delay)
                else:
                    # 3次后放弃
                    raise

        # 所有重试都失败
        raise Exception(f"LLM调用失败，已重试 {MAX_RETRIES} 次。最后错误: {last_error}")

    async def parse_user_request(self, user_request: str) -> dict:
        """
        解析用户自然语言请求

        Args:
            user_request: 用户原始请求

        Returns:
            dict: 解析后的参数
                {
                    "style": "风格描述",
                    "instruments": ["piano", "guitar"],
                    "duration": 30,
                    "mood": "温柔",
                    "special_requirements": "..."
                }
        """
        system_prompt = """你是一个音乐改编助手。请从用户请求中提取以下信息：

1. 风格（style）：如"温暖钢琴风""清晨阳光感"
2. 乐器（instruments）：如["piano", "guitar"]
3. 时长（duration）：以秒为单位，若未指定返回默认值30
4. 情绪/氛围（mood）：如"温柔""欢快"
5. 特殊要求（special_requirements）：其他说明

以JSON格式返回，不要包含其他内容。"""

        user_prompt = f"用户请求：{user_request}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        import json
        response = await self.chat(messages, temperature=0.3)
        try:
            return json.loads(response)
        except:
            # 解析失败时返回默认值
            return {
                "style": user_request,
                "instruments": ["piano"],
                "duration": 30,
                "mood": "未知",
                "special_requirements": user_request,
            }

    async def extract_style_and_mood(self, user_request: str) -> dict:
        """
        仅提取用户请求中的音乐风格和情感。
        返回格式：{"style": str | None, "mood": str | None}
        """
        system_prompt = """你是一个音乐分析助手。从用户请求中提取音乐风格和情感。
    如果用户没有明确提及风格或情感，则对应字段返回 null。
    只输出 JSON，格式：{"style": "风格描述或null", "mood": "情感描述或null"}
    不要输出任何其他内容。"""

        user_prompt = f"用户请求：{user_request}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        try:
            response = await self.chat(messages, temperature=0.2, max_tokens=150)
            import json
            result = json.loads(response)
            return {
                "style": result.get("style") if result.get("style") not in (None, "", "null") else None,
                "mood": result.get("mood") if result.get("mood") not in (None, "", "null") else None,
            }
        except Exception as e:
            print(f"[LLM] extract_style_and_mood failed: {e}")
            return {"style": None, "mood": None}

    async def generate_plan(self, user_request: str, analysis_result: dict = None) -> list[str]:
        """
        生成执行计划

        Args:
            user_request: 用户需求
            analysis_result: 音频分析结果（可选）

        Returns:
            list[str]: 步骤列表
        """
        system_prompt = """你是一个音乐制作流程规划助手。根据用户需求，选择以下步骤中的一部分或全部，并以 JSON 数组形式返回步骤名称列表（只返回数组，不含其他内容）。

可选步骤（字符串名称）：
- fetch_source
- analyze_structure
- extract_melody
- generate_midi
- arrange
- render
- check_quality

要求：
1. 通常必须包含：fetch_source、extract_melody、generate_midi、arrange、render（这些是基本流程）。
2. 如果用户明确说“不需要分析”、“跳过分析”、“无需解析”、“直接替换”或类似表述，则可以省略 analyze_structure。
3. 如果用户要求“检查质量”、“评估音质”、“确保质量”，则包含 check_quality；否则通常省略。
4. 只返回 JSON 数组，例如：["fetch_source", "extract_melody", "generate_midi", "arrange", "render"]
   不要包含任何解释、参数或代码块标记。
"""

        user_prompt = f"用户需求：{user_request}"
        if analysis_result:
            user_prompt += f"\n\n音频分析：{analysis_result}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        import json
        response = await self.chat(messages, temperature=0.5)
        import re
        # 在 try 之前提取代码块内容
        content = response
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response, re.DOTALL)
        if match:
            content = match.group(1).strip()

        try:
            plan = json.loads(content)
        except json.JSONDecodeError:
            plan = []

        # 过滤出有效的步骤名称（字符串且属于可选集合）
        valid_steps = ["fetch_source", "analyze_structure", "extract_melody", "generate_midi", "arrange", "render", "check_quality"]
        if isinstance(plan, list):
            filtered = [item for item in plan if isinstance(item, str) and item in valid_steps]
            if filtered:
                return filtered
        # 解析失败或结果为空，返回完整默认计划（所有步骤）
        return valid_steps

    async def extract_clip_preference(self, user_request: str) -> dict:
        """
        解析用户请求中的截取偏好，返回分类结果。
        返回格式: {"category": int, "value": Any}
        category含义:
            1: 能量高（副歌/高潮）
            2: 特定片段（主歌/副歌等，但无法精确定位，故随机）
            3: 特定时间（如"35-75秒"）
            4: 无指定偏好
        当category=3时，value应包含起始时间（秒），例如 {"category": 3, "value": 35}
        """
        prompt = """你是一个音乐分析助手。分析用户对截取音频片段位置的描述，并分类。
    分类规则：
    1. 如果用户希望截取“高潮”、“副歌”、“最精彩”、“能量最高”的部分，类别为1，value为null。
    2. 如果用户提到“主歌”、“第一段”、“第二段”等具体段落，但无法精确定位，类别为2，value为null。
    3. 如果用户指定了具体时间范围，如“35秒到75秒”、“从30秒开始”、“1分20秒”，类别为3，value为起始时间（秒数）。注意将“1分20秒”转换为80秒。
    4. 如果用户没有提及任何位置偏好，类别为4，value为null。

    只输出JSON对象，格式：{"category": 整数, "value": 数字或null}，例如：
    - {"category": 1, "value": null}
    - {"category": 3, "value": 35}
    - {"category": 4, "value": null}
    不要输出其他内容。"""
        messages = [{"role": "user", "content": f"用户请求：{user_request}\n{prompt}"}]
        try:
            response = await self.chat(messages, temperature=0.2, max_tokens=150)
            import re, json
            # 清理 markdown 代码块
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
            else:
                json_str = response.strip()
            result = json.loads(json_str)
            # 验证字段
            if isinstance(result, dict) and "category" in result:
                category = int(result["category"])
                if category not in [1, 2, 3, 4]:
                    return {"category": 4, "value": None}
                value = result.get("value")
                if category == 3:
                    # 尝试将value转换为浮点数，若失败则回退None
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        value = None
                else:
                    value = None
                return {"category": category, "value": value}
            else:
                return {"category": 4, "value": None}
        except Exception as e:
            print(f"[LLM] extract_clip_preference failed: {e}")
            return {"category": 4, "value": None}

    async def reflect_on_quality(
        self,
        quality_result: dict,
        user_request: str,
    ) -> dict:
        """
        反思质量评估结果

        Args:
            quality_result: 质量评估结果
            user_request: 用户原始需求

        Returns:
            dict: 反思结果
                {
                    "needs_revision": bool,
                    "reason": "原因",
                    "suggestions": ["建议1", "建议2"]
                }
        """
        system_prompt = """你是一个音乐质量评估专家。根据质量评估结果判断是否需要重新生成。

评估维度：
- overall_score: 总体分数
- naturalness: 自然度
- musicality: 音乐性
- quality_issues: 问题列表

如果质量不达标（如分数<3.5或有严重问题），返回需要修订。
以JSON格式返回：{"needs_revision": bool, "reason": "...", "suggestions": [...]}"""

        user_prompt = f"""用户需求：{user_request}

质量评估：
{quality_result}

请判断是否需要重新生成。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        import json
        response = await self.chat(messages, temperature=0.3)
        try:
            return json.loads(response)
        except:
            return {
                "needs_revision": False,
                "reason": "LLM响应解析失败，默认通过",
                "suggestions": [],
            }

# 全局LLM服务实例
llm_service = LLMService()

def get_llm():
    """返回一个 LangChain 兼容的 ChatOpenAI 实例"""
    from langchain_openai import ChatOpenAI
    settings = get_settings()
    return ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL or None,
        model=settings.LLM_MODEL,
        temperature=0.7,
        max_retries=5,                # 增加重试次数
        # retry_on=[RateLimitError],    # 仅对限流错误重试
        # retry_delay=2,                # 初始延迟 2 秒（指数退避）
    )