import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum as SAEnum, Text, Numeric, SmallInteger, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base
from app.models.user import utcnow


# ─── ENUMS ────────────────────────────────────────────────────────────────────
class VehicleStatus(str, enum.Enum):
    complete    = "complete"
    dismantling = "dismantling"
    partial     = "partial"
    depleted    = "depleted"


class PurchaseOrigin(str, enum.Enum):
    auction = "auction"
    private = "private"


class PartStatus(str, enum.Enum):
    in_vehicle   = "in_vehicle"
    dismounting  = "dismounting"
    in_stock     = "in_stock"
    reserved     = "reserved"
    sold         = "sold"
    transferred  = "transferred"


class MediaType(str, enum.Enum):
    photo = "photo"
    video = "video"


# ─── PART CONDITION ───────────────────────────────────────────────────────────
class PartCondition(Base):
    __tablename__ = "part_conditions"

    id:          Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name:        Mapped[str]       = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str|None]  = mapped_column(Text)
    sort_order:  Mapped[int]       = mapped_column(SmallInteger, default=0)
    is_active:   Mapped[bool]      = mapped_column(Boolean, default=True)

    parts: Mapped[list["Part"]] = relationship("Part", back_populates="condition")


# ─── VEHICLE ──────────────────────────────────────────────────────────────────
class Vehicle(Base):
    __tablename__ = "vehicles"

    id:               Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_key:      Mapped[str]              = mapped_column(String(20), unique=True, nullable=False, index=True)
    branch_id:        Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    brand:            Mapped[str]              = mapped_column(String(80), nullable=False, index=True)
    model:            Mapped[str]              = mapped_column(String(80), nullable=False, index=True)
    year:             Mapped[int]              = mapped_column(SmallInteger, nullable=False, index=True)
    color:            Mapped[str|None]         = mapped_column(String(50))
    purchase_origin:  Mapped[PurchaseOrigin]   = mapped_column(SAEnum(PurchaseOrigin), nullable=False)
    purchase_cost:    Mapped[float]            = mapped_column(Numeric(12, 2), nullable=False)
    purchase_date:    Mapped[datetime]         = mapped_column(DateTime(timezone=True), nullable=False)
    status:           Mapped[VehicleStatus]    = mapped_column(SAEnum(VehicleStatus), nullable=False, default=VehicleStatus.complete, index=True)
    general_condition:Mapped[str|None]         = mapped_column(Text)
    notes:            Mapped[str|None]         = mapped_column(Text)
    seller_name:      Mapped[str|None]         = mapped_column(String(150))
    seller_phone:     Mapped[str|None]         = mapped_column(String(20))
    registered_by_id: Mapped[uuid.UUID|None]   = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at:       Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:       Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    branch:  Mapped["Branch"]          = relationship("Branch", back_populates="vehicles")  # type: ignore
    photos:  Mapped[list["VehiclePhoto"]] = relationship("VehiclePhoto", back_populates="vehicle", cascade="all, delete-orphan")
    parts:   Mapped[list["Part"]]      = relationship("Part", back_populates="vehicle")

    def __repr__(self) -> str:
        return f"<Vehicle {self.vehicle_key}: {self.brand} {self.model} {self.year}>"


class VehiclePhoto(Base):
    __tablename__ = "vehicle_photos"

    id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False, index=True)
    storage_path:   Mapped[str]       = mapped_column(Text, nullable=False)
    thumbnail_path: Mapped[str|None]  = mapped_column(Text)
    is_main:        Mapped[bool]      = mapped_column(Boolean, default=False)
    sort_order:     Mapped[int]       = mapped_column(SmallInteger, default=0)
    created_at:     Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=utcnow)

    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="photos")


# ─── PART ─────────────────────────────────────────────────────────────────────
class Part(Base):
    __tablename__ = "parts"

    id:             Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    part_key:       Mapped[str]          = mapped_column(String(30), unique=True, nullable=False, index=True)
    vehicle_id:     Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False, index=True)
    branch_id:      Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name:           Mapped[str]          = mapped_column(String(150), nullable=False, index=True)
    brand:          Mapped[str]          = mapped_column(String(80), nullable=False, index=True)
    model:          Mapped[str]          = mapped_column(String(80), nullable=False, index=True)
    year_from:      Mapped[int|None]     = mapped_column(SmallInteger)
    year_to:        Mapped[int|None]     = mapped_column(SmallInteger)
    specifications: Mapped[str|None]     = mapped_column(Text)
    observations:   Mapped[str|None]     = mapped_column(Text)
    condition_id:   Mapped[uuid.UUID|None]= mapped_column(UUID(as_uuid=True), ForeignKey("part_conditions.id"))
    status:         Mapped[PartStatus]   = mapped_column(SAEnum(PartStatus), nullable=False, default=PartStatus.in_vehicle, index=True)
    sale_price:     Mapped[float]        = mapped_column(Numeric(12, 2), nullable=False)
    has_warranty:   Mapped[bool]         = mapped_column(Boolean, default=False)
    warranty_days:  Mapped[int|None]     = mapped_column(SmallInteger)
    registered_by_id: Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at:     Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:     Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at:     Mapped[datetime|None]= mapped_column(DateTime(timezone=True))

    branch:    Mapped["Branch"]          = relationship("Branch", back_populates="parts")  # type: ignore
    vehicle:   Mapped["Vehicle"]         = relationship("Vehicle", back_populates="parts")
    condition: Mapped["PartCondition|None"] = relationship("PartCondition", back_populates="parts")
    media:     Mapped[list["PartMedia"]] = relationship("PartMedia", back_populates="part", cascade="all, delete-orphan", order_by="PartMedia.sort_order")
    status_history: Mapped[list["PartStatusHistory"]] = relationship("PartStatusHistory", back_populates="part")

    @property
    def main_photo_url(self) -> str | None:
        photos = [m for m in self.media if m.media_type == MediaType.photo]
        if not photos:
            return None
        main = next((p for p in photos if p.is_main), None)
        target = main or photos[0]
        return target.thumbnail_path or target.storage_path

    def __repr__(self) -> str:
        return f"<Part {self.part_key}: {self.name}>"


class PartMedia(Base):
    __tablename__ = "part_media"

    id:             Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    part_id:        Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), ForeignKey("parts.id"), nullable=False, index=True)
    media_type:     Mapped[MediaType]  = mapped_column(SAEnum(MediaType), nullable=False, default=MediaType.photo)
    storage_path:   Mapped[str]        = mapped_column(Text, nullable=False)
    thumbnail_path: Mapped[str|None]   = mapped_column(Text)
    is_main:        Mapped[bool]       = mapped_column(Boolean, default=False)
    sort_order:     Mapped[int]        = mapped_column(SmallInteger, default=0)
    created_at:     Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=utcnow)

    part: Mapped["Part"] = relationship("Part", back_populates="media")


class PartStatusHistory(Base):
    __tablename__ = "part_status_history"

    id:              Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    part_id:         Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), ForeignKey("parts.id"), nullable=False, index=True)
    previous_status: Mapped[PartStatus|None]= mapped_column(SAEnum(PartStatus))
    new_status:      Mapped[PartStatus]     = mapped_column(SAEnum(PartStatus), nullable=False)
    reason:          Mapped[str|None]       = mapped_column(Text)
    changed_by_id:   Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at:      Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=utcnow)

    part: Mapped["Part"] = relationship("Part", back_populates="status_history")