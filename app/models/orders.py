# ══════════════════════════════════════════════════════════════════════════════
# ARCHIVO: backend/app/models/orders.py
# CAMBIO: agregar sale_id (FK opcional a sales)
# ══════════════════════════════════════════════════════════════════════════════

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base
from app.models.user import utcnow


class OrderStatus(str, enum.Enum):
    pending     = "pending"
    taken       = "taken"
    in_progress = "in_progress"
    completed   = "completed"
    cancelled   = "cancelled"


class OrderPriority(str, enum.Enum):
    normal = "normal"
    urgent = "urgent"


class DisassemblyOrder(Base):
    __tablename__ = "disassembly_orders"

    id:               Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_key:        Mapped[str]            = mapped_column(String(30), unique=True, nullable=False, index=True)
    part_id:          Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey("parts.id"), nullable=False, index=True)
    vehicle_id:       Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    branch_id:        Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)

    # ── NUEVO: referencia a la venta que originó esta orden ─────────────────
    sale_id:          Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey("sales.id"), nullable=True, index=True)

    status:           Mapped[OrderStatus]    = mapped_column(SAEnum(OrderStatus), nullable=False, default=OrderStatus.pending, index=True)
    priority:         Mapped[OrderPriority]  = mapped_column(SAEnum(OrderPriority), nullable=False, default=OrderPriority.normal)
    instructions:     Mapped[str | None]     = mapped_column(Text)
    created_by_id:    Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_to_id:   Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    assigned_at:      Mapped[datetime|None]  = mapped_column(DateTime(timezone=True))
    started_at:       Mapped[datetime|None]  = mapped_column(DateTime(timezone=True))
    completed_at:     Mapped[datetime|None]  = mapped_column(DateTime(timezone=True))
    completion_notes: Mapped[str|None]       = mapped_column(Text)
    cancelled_at:     Mapped[datetime|None]  = mapped_column(DateTime(timezone=True))
    cancel_reason:    Mapped[str|None]       = mapped_column(Text)
    created_at:       Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:       Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relaciones
    part:        Mapped["Part"]        = relationship("Part")
    vehicle:     Mapped["Vehicle"]     = relationship("Vehicle")
    branch:      Mapped["Branch"]      = relationship("Branch")
    created_by:  Mapped["User"]        = relationship("User", foreign_keys=[created_by_id])
    assigned_to: Mapped["User|None"]   = relationship("User", foreign_keys=[assigned_to_id])
    sale:        Mapped["Sale|None"]   = relationship("Sale", foreign_keys=[sale_id])  # type: ignore

    @property
    def minutes_ago(self) -> int:
        return int((datetime.now(timezone.utc) - self.created_at).total_seconds() / 60)

    def __repr__(self) -> str:
        return f"<Order {self.order_key} [{self.status.value}]>"