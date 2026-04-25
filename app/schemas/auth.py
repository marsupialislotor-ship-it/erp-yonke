from pydantic import BaseModel, EmailStr, field_validator
from uuid import UUID
from datetime import datetime


# ─── REQUEST ──────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email:     EmailStr
    password:  str
    device_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
    all_devices:   bool = False


class RecoverRequest(BaseModel):
    email: EmailStr


# ─── RESPONSE ─────────────────────────────────────────────────────────────────
class BranchOut(BaseModel):
    id:               UUID
    name:             str
    code:             str
    is_headquarters:  bool

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id:               UUID
    email:            str
    full_name:        str
    role:             str
    branch:           BranchOut
    phone:            str | None = None
    dashboard_config: dict | None = None
    initials:         str

    model_config = {"from_attributes": True}

    @field_validator("role", mode="before")
    @classmethod
    def role_value(cls, v):
        return v.value if hasattr(v, "value") else v


class LoginResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int
    user:          UserOut


class RefreshResponse(BaseModel):
    access_token: str
    expires_in:   int


class MessageResponse(BaseModel):
    message: str