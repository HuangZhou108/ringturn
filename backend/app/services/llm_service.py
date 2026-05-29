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

    async def generate_plan(self, user_request: str, analysis_result: dict = None) -> list[str]:
        """
        生成执行计划

        Args:
            user_request: 用户需求
            analysis_result: 音频分析结果（可选）

        Returns:
            list[str]: 步骤列表
        """
        system_prompt = """你是一个音乐制作流程规划助手。请根据用户需求生成执行步骤计划。

可选步骤：
- fetch_source: 获取音频源
- analyze_structure: 分析音乐结构（BPM、调性、段落）
- extract_melody: 提取主旋律
- generate_midi: 生成MIDI文件
- arrange: 乐器改编
- render: 渲染音频
- check_quality: 质量检查

返回JSON数组，如：["fetch_source", "analyze_structure", ...]"""

        user_prompt = f"用户需求：{user_request}"
        if analysis_result:
            user_prompt += f"\n\n音频分析：{analysis_result}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        import json
        response = await self.chat(messages, temperature=0.5)
        try:
            plan = json.loads(response)
            if isinstance(plan, list) and len(plan) > 0:
                return plan
        except:
            pass

        # 默认计划
        return [
            "fetch_source",
            "analyze_structure",
            "extract_melody",
            "generate_midi",
            "arrange",
            "render",
            "check_quality",
        ]

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