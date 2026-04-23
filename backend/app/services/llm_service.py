"""
LLM服务模块

封装与语言模型的交互，用于：
- 需求理解与参数提取
- 执行计划生成
- 反思与决策
"""

import os
from typing import Optional
from openai import AsyncOpenAI
from app.core.config import get_settings

settings = get_settings()

class LLMService:
    """LLM服务封装"""

    def __init__(self):
        self.client = None
        self._init_client()

    def _init_client(self):
        """初始化OpenAI客户端"""
        api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        base_url = settings.OPENAI_BASE_URL or os.getenv("OPENAI_BASE_URL")

        if not api_key:
            raise ValueError("OPENAI_API_KEY未配置")

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
        调用LLM进行对话

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

        response = await self.client.chat.completions.create(
            model=model or settings.OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

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
