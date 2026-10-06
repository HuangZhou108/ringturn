"""Validated, single-call interpretation of user feedback."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services.llm_service import llm_service

VALID_NODES = {
    "fetch_source",
    "analyze_structure",
    "extract_melody",
    "generate_midi",
    "arrange",
    "render",
    "check_quality",
}
VALID_PARAMS = {"instrument", "tempo", "duration", "filename"}


class FeedbackDecision(BaseModel):
    resume_from_node: str = "arrange"
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("resume_from_node")
    @classmethod
    def validate_node(cls, value: str) -> str:
        return value if value in VALID_NODES else "arrange"

    @field_validator("params")
    @classmethod
    def validate_params(cls, value: dict[str, Any]) -> dict[str, Any]:
        filtered = {key: item for key, item in value.items() if key in VALID_PARAMS}
        if "tempo" in filtered:
            filtered["tempo"] = max(30, min(300, int(filtered["tempo"])))
        if "duration" in filtered:
            filtered["duration"] = max(1, min(300, int(filtered["duration"])))
        for key in ("instrument", "filename"):
            if key in filtered:
                filtered[key] = str(filtered[key]).strip()[:200]
        return filtered


def sanitize_feedback_params(value: dict[str, Any] | None) -> dict[str, Any]:
    try:
        return FeedbackDecision(params=value or {}).params
    except (ValidationError, ValueError, TypeError):
        return {}


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.S)
    candidate = fenced.group(1) if fenced else stripped
    if not candidate.startswith("{"):
        match = re.search(r"\{.*\}", candidate, re.S)
        candidate = match.group(0) if match else "{}"
    parsed = json.loads(candidate)
    return parsed if isinstance(parsed, dict) else {}


async def analyze_feedback(
    feedback: str,
    current_params: dict[str, Any] | None,
) -> FeedbackDecision:
    prompt = f"""分析下面的铃声修改反馈，只返回一个 JSON 对象：
{{"resume_from_node":"arrange","params":{{"instrument":"Violin"}}}}

resume_from_node 只能是 fetch_source、analyze_structure、extract_melody、
generate_midi、arrange、render、check_quality。params 只能包含 instrument、
tempo、duration、filename；没有明确修改的字段不要输出。

当前参数：{json.dumps(current_params or {}, ensure_ascii=False)}
用户反馈：{feedback}
"""
    try:
        response = await llm_service.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )
        return FeedbackDecision.model_validate(_extract_json(response))
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as error:
        print(f"[FEEDBACK] structured analysis fallback: {type(error).__name__}")
        return FeedbackDecision()
    except Exception as error:
        print(f"[FEEDBACK] analysis unavailable: {type(error).__name__}")
        return FeedbackDecision()
