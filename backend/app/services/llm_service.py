"""
LLM服务模块

封装与语言模型的交互，用于：
- 需求理解与参数提取
- 执行计划生成
- 反思与决策
"""

import asyncio
import os
import time
from collections import Counter
from typing import Any, Callable, Mapping

from app.agent.resilience import RetryPolicy, run_with_retry
from app.agent.trace import (
    create_trace_event,
    get_execution_context,
    persist_trace_event,
)
from app.core.config import get_settings
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

settings = get_settings()


def is_retryable_llm_error(error: BaseException) -> bool:
    """只把无请求副作用的瞬时模型服务故障判定为可重试。"""

    if isinstance(
        error,
        (
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
            asyncio.TimeoutError,
            TimeoutError,
        ),
    ):
        return True
    if isinstance(error, APIStatusError):
        status_code = getattr(error, "status_code", None)
        return status_code in {408, 409, 429} or (
            isinstance(status_code, int) and status_code >= 500
        )
    return False


def build_llm_error(error: BaseException) -> dict[str, Any]:
    """生成不包含 provider 响应正文或用户输入的稳定错误结构。"""

    if isinstance(error, RateLimitError):
        code, message = "LLM_RATE_LIMITED", "LLM provider rate limit exceeded"
    elif isinstance(error, (APITimeoutError, asyncio.TimeoutError, TimeoutError)):
        code, message = "LLM_REQUEST_TIMEOUT", "LLM request timed out"
    elif isinstance(error, APIConnectionError):
        code, message = "LLM_CONNECTION_FAILED", "LLM provider connection failed"
    elif isinstance(error, APIStatusError) and is_retryable_llm_error(error):
        code, message = "LLM_PROVIDER_UNAVAILABLE", "LLM provider is unavailable"
    else:
        code, message = "LLM_REQUEST_FAILED", "LLM request failed"
    return {
        "code": code,
        "scope": "llm",
        "component": "chat_completion",
        "retryable": is_retryable_llm_error(error),
        "exception_type": type(error).__name__,
        "message": message,
    }


def summarize_messages(messages: list[dict]) -> dict[str, Any]:
    """描述消息形状，不复制 prompt、记忆或其他内容。"""

    role_counts = Counter(str(message.get("role", "unknown")) for message in messages)
    content_chars = 0
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            content_chars += len(content)
        elif isinstance(content, list):
            content_chars += sum(
                len(str(part.get("text", "")))
                for part in content
                if isinstance(part, Mapping)
            )
    return {
        "message_count": len(messages),
        "role_counts": dict(sorted(role_counts.items())),
        "content_chars": content_chars,
    }


class LLMService:
    """LLM服务封装"""

    def __init__(
        self,
        client: Any = None,
        *,
        trace_persist: Callable[[str, Mapping[str, Any]], Any] | None = (
            persist_trace_event
        ),
        sleep: Callable[[float], Any] = asyncio.sleep,
    ):
        # 延迟初始化使非 LLM 命令和测试无需配置密钥即可导入应用。
        self.client = client
        self._trace_persist = trace_persist
        self._sleep = sleep

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

    def _emit_trace(
        self,
        *,
        status: str,
        duration_ms: float | None = None,
        details: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> None:
        context = get_execution_context()
        if not context or self._trace_persist is None:
            return
        event_details = {"component": context["component"], **dict(details or {})}
        event = create_trace_event(
            task_id=context["task_id"],
            kind="llm",
            name="chat_completion",
            status=status,
            duration_ms=duration_ms,
            details=event_details,
            error=error,
        )
        self._trace_persist(context["task_id"], event)

    async def _request_completion(
        self,
        *,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[Any, int]:
        policy = RetryPolicy(
            max_attempts=max(1, int(settings.LLM_MAX_ATTEMPTS)),
            timeout_seconds=max(0.001, float(settings.LLM_REQUEST_TIMEOUT_SECONDS)),
            backoff_seconds=max(0.0, float(settings.LLM_RETRY_BACKOFF_SECONDS)),
            max_backoff_seconds=max(0.0, float(settings.LLM_RETRY_MAX_BACKOFF_SECONDS)),
        )

        async def invoke(_attempt: int) -> Any:
            return await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        def on_retry(attempt: int, error: BaseException, delay: float) -> None:
            self._emit_trace(
                status="retrying",
                details={
                    "attempt": attempt,
                    "next_attempt": attempt + 1,
                    "max_attempts": policy.max_attempts,
                    "delay_ms": round(delay * 1000, 3),
                },
                error=build_llm_error(error),
            )

        return await run_with_retry(
            invoke,
            policy=policy,
            on_retry=on_retry,
            retry_if=is_retryable_llm_error,
            sleep=self._sleep,
        )

    async def chat(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        """
        调用 LLM：单次请求有超时，仅瞬时错误进行有限重试。

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

        # 注入 Agent 记忆（全局偏好指令 + 历史画像），作为最高优先级的 system 指令
        from app.services.memory import get_agent_context

        ctx = get_agent_context()
        if ctx:
            messages = [{"role": "system", "content": ctx}, *list(messages)]
        else:
            messages = list(messages)

        started_at = time.perf_counter()
        request_summary = summarize_messages(messages)
        self._emit_trace(
            status="running",
            details={
                "model": model,
                "max_tokens": max_tokens,
                **request_summary,
            },
        )
        try:
            response, attempts = await self._request_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content or ""
            finish_reason = response.choices[0].finish_reason

            # 推理 token 耗尽且没有正文时，仅额外扩大一次输出预算；额外请求仍使用
            # 相同的超时与瞬时错误重试边界。
            if not content.strip() and finish_reason == "length":
                retry_tokens = max(max_tokens * 4, 2000)
                self._emit_trace(
                    status="retrying",
                    details={
                        "reason": "empty_truncated_response",
                        "next_max_tokens": retry_tokens,
                    },
                )
                response, extra_attempts = await self._request_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=retry_tokens,
                )
                attempts += extra_attempts
                content = response.choices[0].message.content or ""
                finish_reason = response.choices[0].finish_reason

            self._emit_trace(
                status="succeeded",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                details={
                    "model": model,
                    "attempts": attempts,
                    "retries": attempts - 1,
                    "finish_reason": finish_reason,
                    "response_chars": len(content),
                },
            )
            return content
        except asyncio.CancelledError:
            self._emit_trace(
                status="cancelled",
                duration_ms=(time.perf_counter() - started_at) * 1000,
            )
            raise
        except Exception as error:
            self._emit_trace(
                status="failed",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                error=build_llm_error(error),
            )
            raise

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

    async def extract_duration(self, user_request: str) -> int | None:
        """
        从用户自然语言请求中提取目标铃声时长（秒）。
        未明确提及时长时返回 None（避免用默认值覆盖 UI 设置）。
        """
        import json
        import re

        system_prompt = """从用户请求中提取目标铃声时长（秒）。
如果用户提到了时长（如"60秒"、"60s"、"1分钟"、"一分半"、"1分20秒"、"40s左右"、"一分钟左右"），提取为秒数。
如果用户没有提及任何时长，返回 null。
转换规则："1分钟"=60，"1分20秒"=80，"一分半"=90，"2分钟"=120，"半分钟"=30。
只输出 JSON：{"duration": 数字或null}"""

        try:
            response = await self.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"用户请求：{user_request}"},
                ],
                temperature=0.1,
                max_tokens=2000,
            )
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
            json_str = match.group(1).strip() if match else response.strip()
            result = json.loads(json_str)
            dur = result.get("duration")
            if dur is None:
                return None
            dur = int(float(dur))
            return dur if dur > 0 else None
        except Exception as e:
            print(f"[LLM] extract_duration failed: {type(e).__name__}")
            return None

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
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = await self.chat(messages, temperature=0.2, max_tokens=150)
            import json

            result = json.loads(response)
            return {
                "style": (
                    result.get("style")
                    if result.get("style") not in (None, "", "null")
                    else None
                ),
                "mood": (
                    result.get("mood")
                    if result.get("mood") not in (None, "", "null")
                    else None
                ),
            }
        except Exception as e:
            print(f"[LLM] extract_style_and_mood failed: {type(e).__name__}")
            return {"style": None, "mood": None}

    async def generate_plan(
        self, user_request: str, analysis_result: dict = None
    ) -> list[str]:
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
1. 通常包含：fetch_source、analyze_structure、extract_melody、generate_midi、arrange、render（这些是基本流程）。
2. 如果用户明确说“不需要分析”、“跳过分析”、“无需解析”、“直接替换”或类似表述，则可以省略 analyze_structure。
3. 默认包含 check_quality（对结果做质量评估与反思），除非用户明确说”不需要质量检查/跳过质量检查”。
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
        valid_steps = [
            "fetch_source",
            "analyze_structure",
            "extract_melody",
            "generate_midi",
            "arrange",
            "render",
            "check_quality",
        ]
        if isinstance(plan, list):
            filtered = [
                item for item in plan if isinstance(item, str) and item in valid_steps
            ]
            if filtered:
                if "check_quality" not in filtered:
                    filtered.append("check_quality")  # 默认执行质量检查
                return filtered
        # 解析失败或结果为空，返回完整默认计划（所有步骤）
        return valid_steps

    async def plan_arrangement(
        self,
        user_request: str,
        analysis_result: dict,
        current: dict,
    ) -> dict:
        """
        根据音频分析结果和用户需求，决定最终改编参数（乐器/速度/移调）。

        这是让 LLM 真正参与改编决策的入口：在分析阶段结束后调用，
        由 LLM 结合检测到的 BPM / 人声 / 情绪风格，产出可落地的改编参数。
        失败时返回空 dict（调用方沿用用户参数）。

        Returns:
            {"instrument": str, "tempo": int, "transpose_semitones": int}
        """
        import json
        import re

        system_prompt = """你是编曲助手。根据音频分析结果和用户需求，决定最终的改编参数。

你会拿到：
- 分析结果：BPM、是否有人声/钢琴/吉他、情绪风格（含 mood、energy_level 1-10、genre 等）
- 用户需求（可能包含情绪描述，如"青春洋溢""温柔""欢快""忧伤"）
- 用户当前的参数（可能是默认值）

请先综合「用户需求中的情绪词」和「分析结果的 mood / energy_level」判断目标情绪，再据此选择乐器和速度：

【情绪 → 乐器/速度 映射】
- 青春洋溢 / 欢快 / 活力 / 明亮 / energetic / happy（energy_level ≥ 7）：
  乐器倾向明亮清脆型：Music Box、Glockenspiel、Bright Acoustic Piano、Electric Piano、Marimba、Vibraphone；
  速度偏快：略高于检测 BPM（例如检测 96 可用 104~120）。
- 温柔 / 舒缓 / 抒情 / 安静 / calm / soothing（energy_level ≤ 4）：
  乐器倾向柔美型：Acoustic Grand Piano、Celesta、Orchestral Harp、Warm Pad、Music Box；
  速度偏慢（80~96）。
- 忧伤 / 伤感 / melancholic / sad：
  乐器倾向温暖低沉型：Cello、Acoustic Grand Piano、Clarinet、String Ensemble；
  速度偏慢。
- 激昂 / 史诗 / epic / dramatic：
  乐器倾向 Brass Section、String Ensemble、Overdriven Guitar；速度中快。
- 无法判断：保持 Acoustic Piano，速度贴合检测 BPM。

输出 JSON：
{"instrument": "GM 乐器英文名", "tempo": 整数BPM, "transpose_semitones": 整数}

规则：
1. 若用户已明确指定乐器/速度（速度不是默认的 120），必须严格保持原值，绝对不要改动。
2. 仅当速度为默认值 120 时，才按上面的映射推荐，且速度调整幅度控制在检测 BPM 的 ±20% 左右，不要大幅偏离。
3. transpose_semitones：旋律整体偏低可 +12，偏高可 -12，没把握填 0（范围 -12~+12）。
只输出 JSON，不要任何解释。"""

        # RAG：检索相关知识，注入提示词（让决策有知识库支撑，而非仅靠硬编码映射）
        try:
            from app.services.knowledge_base import format_knowledge, retrieve_knowledge
            from app.services.memory import get_agent_profile_id

            mood = (analysis_result or {}).get("mood_style", {}).get("mood", "")
            query = f"{user_request} {mood}"
            docs = retrieve_knowledge(
                query,
                top_k=settings.RAG_TOP_K,
                profile_id=get_agent_profile_id(),
            )
            knowledge = format_knowledge(docs)
            print(
                f"[RAG] plan_arrangement 检索到 {len(docs)} 篇知识: {[d['title'] for d in docs]}"
            )
        except Exception as e:
            print(f"[RAG] plan_arrangement 检索失败: {e}")
            knowledge = ""

        user_prompt = (
            f"用户需求：{user_request}\n"
            f"音频分析结果：{json.dumps(analysis_result, ensure_ascii=False, default=str)}\n"
            f"当前参数：{json.dumps(current, ensure_ascii=False, default=str)}"
            + (f"\n\n【相关知识库检索结果】\n{knowledge}" if knowledge else "")
        )

        try:
            response = await self.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
            json_str = match.group(1).strip() if match else response.strip()
            result = json.loads(json_str)

            out = {}
            if (
                isinstance(result.get("instrument"), str)
                and result["instrument"].strip()
            ):
                out["instrument"] = result["instrument"].strip()

            # 速度：用户明确设置（非默认 120）时强制保持；否则限制在检测 BPM 附近
            user_tempo = current.get("tempo")
            try:
                user_tempo = int(user_tempo) if user_tempo is not None else None
            except (TypeError, ValueError):
                user_tempo = None
            try:
                out["tempo"] = int(result.get("tempo"))
            except (TypeError, ValueError):
                out["tempo"] = user_tempo or 120

            if user_tempo and user_tempo != 120:
                out["tempo"] = user_tempo  # 用户明确指定速度，强制保持
            else:
                detected = analysis_result.get("bpm")
                if detected:
                    lo = max(60, int(float(detected) * 0.8))
                    hi = min(200, int(float(detected) * 1.25))
                    out["tempo"] = max(lo, min(hi, out["tempo"]))

            try:
                trans = int(result.get("transpose_semitones"))
                out["transpose_semitones"] = max(-12, min(12, trans))
            except (TypeError, ValueError):
                out["transpose_semitones"] = 0
            return out
        except Exception as e:
            print(f"[LLM] plan_arrangement failed: {type(e).__name__}")
            return {}

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
            import json
            import re

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
            print(f"[LLM] extract_clip_preference failed: {type(e).__name__}")
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
        timeout=max(0.001, settings.LLM_REQUEST_TIMEOUT_SECONDS),
        max_retries=max(0, settings.LLM_MAX_ATTEMPTS - 1),
    )
