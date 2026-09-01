from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class CheckResponse(BaseModel):
    allowed: bool
    remaining: int
    reset_at: datetime


class CheckID(BaseModel):
    client_id: UUID


class UserCreate(BaseModel):
    username: str