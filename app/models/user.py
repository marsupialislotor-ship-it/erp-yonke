import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum as SAEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── ENUMS ────────────────────────────────────────────────────────────────────
class UserRole(str, enum.Enum):
    owner      = "owner"
    admin      = "admin"
    supervisor = "supervisor"
    seller     = "seller"
    mechanic   = "mechanic"
    helper     = "helper"


# ─── BRANCH ───────────────────────────────────────────────────────────────────
class Branch(Base):
    __tablename__ = "branches"

    id:               Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name:             Mapped[str]       = mapped_column(String(100), nullable=False)
    code:             Mapped[str]       = mapped_column(String(20), unique=True, nullable=False)
    address:          Mapped[str | None]= mapped_column(String(300))
    phone:            Mapped[str | None]= mapped_column(String(20))
    timezone:         Mapped[str]       = mapped_column(String(50), default="America/Mexico_City")
    is_headquarters:  Mapped[bool]      = mapped_column(Boolean, default=False)
    is_active:        Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:       Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:       Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relaciones
    users:    Mapped[list["User"]]    = relationship("User",    back_populates="branch")
    vehicles: Mapped[list["Vehicle"]] = relationship("Vehicle", back_populates="branch")
    parts:    Mapped[list["Part"]]    = relationship("Part",    back_populates="branch")

    def __repr__(self) -> str:
        return f"<Branch {self.code}: {self.name}>"


# ─── USER ─────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id:               Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email:            Mapped[str]          = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash:    Mapped[str]          = mapped_column(String(255), nullable=False)
    full_name:        Mapped[str]          = mapped_column(String(150), nullable=False)
    phone:            Mapped[str | None]   = mapped_column(String(20))
    role:             Mapped[UserRole]     = mapped_column(SAEnum(UserRole), nullable=False)
    branch_id:        Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    is_active:        Mapped[bool]         = mapped_column(Boolean, default=True)
    dashboard_config: Mapped[dict | None]  = mapped_column(JSON)
    last_login_at:    Mapped[datetime|None]= mapped_column(DateTime(timezone=True))
    created_at:       Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:       Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at:       Mapped[datetime|None]= mapped_column(DateTime(timezone=True))

    # Relaciones
    branch:         Mapped["Branch"]             = relationship("Branch", back_populates="users")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    @property
    def initials(self) -> str:
        parts = self.full_name.strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[1][0]}".upper()
        return self.full_name[:2].upper()

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def __repr__(self) -> str:
        return f"<User {self.email} [{self.role.value}]>"


# ─── REFRESH TOKEN ────────────────────────────────────────────────────────────
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id:          Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:     Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    token_hash:  Mapped[str]          = mapped_column(String(255), unique=True, nullable=False)
    device_info: Mapped[str | None]   = mapped_column(String(200))
    expires_at:  Mapped[datetime]     = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at:  Mapped[datetime|None]= mapped_column(DateTime(timezone=True))
    created_at:  Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    @property
    def is_valid(self) -> bool:
        from datetime import timezone
        return (
            self.revoked_at is None
            and self.expires_at > datetime.now(timezone.utc)
        )

    def __repr__(self) -> str:
        return f"<RefreshToken user={self.user_id} valid={self.is_valid}>"