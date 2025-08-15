# app/schemas.py
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime

# -------- Auth --------
class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=4, max_length=100)
    nickname: str = Field(min_length=1, max_length=50)

class LoginIn(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

# -------- User/Profile --------
class UserOut(BaseModel):
    id: int
    username: str
    nickname: str
    created_at: datetime
    class Config:
        from_attributes = True

class ScoreCreate(BaseModel):
    text: str
    score: float

class ScoreOut(BaseModel):
    id: int
    text: str
    score: float
    created_at: datetime
    class Config:
        from_attributes = True

class ProfileOut(BaseModel):
    user: UserOut
    scores: List[ScoreOut]
