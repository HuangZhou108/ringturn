from pydantic import BaseModel
from typing import Optional, List


class PreferenceGetResponse(BaseModel):
    ai_recommendation: dict
    user_overrides: dict
    effective: dict


class PreferenceUpdateRequest(BaseModel):
    use_ai_preferences: bool = False
    instrument: Optional[str] = None
    tempo: Optional[int] = None
    duration: Optional[int] = None
    style_tags: Optional[List[str]] = None


class PreferenceUpdateResponse(BaseModel):
    message: str