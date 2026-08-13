from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SessionPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    kind: Literal["anonymous"] = "anonymous"
    created_at: datetime
    expires_at: datetime


class AuthSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authenticated: Literal[True] = True
    user_id: UUID
    kind: Literal["anonymous"] = "anonymous"
    expires_at: datetime
