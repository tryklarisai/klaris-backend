"""
Pydantic Schemas for User
Validated input/output for User endpoints.
"""
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

class UserBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: EmailStr

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserRead(UserBase):
    user_id: UUID
    tenant_id: UUID
    is_root: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    tenant_name: str
    email: EmailStr
    password: str
