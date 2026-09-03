from pydantic import BaseModel


class RateLimitRequest(BaseModel):
    client_id: str


class RateLimitResponse(BaseModel):
    allowed: bool
    remaining: int
    reset_at: int