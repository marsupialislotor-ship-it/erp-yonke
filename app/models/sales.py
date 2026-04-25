import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum as SAEnum, Text, Numeric, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base
from app.models.user import utcnow


class SaleChannel(str, enum.Enum):
    counter      = "counter"
    whatsapp     = "whatsapp"
    mercadolibre = "mercadolibre"
    private      = "private"


class PaymentMethod(str, enum.Enum):
    cash     = "cash"
    transfer = "transfer"


class SaleStatus(str, enum.Enum):
    pending_payment = "pending_payment"
    confirmed       = "confirmed"
    in_process      = "in_process"
    delivered       = "delivered"
    cancelled       = "cancelled"


class QuoteStatus(str, enum.Enum):
    draft     = "draft"
    sent      = "sent"
    accepted  = "accepted"
    rejected  = "rejected"
    expired   = "expired"
    converted = "converted"


class Customer(Base):
    __tablename__ = "customers"

    id:               Mapped[uuid.UUID]   = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name:             Mapped[str]         = mapped_column(String(150), nullable=False, index=True)
    phone:            Mapped[str|None]    = mapped_column(String(20))
    email:            Mapped[str|None]    = mapped_column(String(255))
    customer_type:    Mapped[str]         = mapped_column(String(20), default="individual")
    is_frequent:      Mapped[bool]        = mapped_column(Boolean, default=False)
    total_purchases:  Mapped[int]         = mapped_column(default=0)
    total_spent:      Mapped[float]       = mapped_column(Numeric(14, 2), default=0)
    shipping_address: Mapped[str|None]    = mapped_column(Text)
    city:             Mapped[str|None]    = mapped_column(String(100))
    created_at:       Mapped[datetime]    = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:       Mapped[datetime]    = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    quotes: Mapped[list["Quote"]] = relationship("Quote", back_populates="customer")
    sales:  Mapped[list["Sale"]]  = relationship("Sale",  back_populates="customer")

    @property
    def initials(self) -> str:
        parts = self.name.strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[1][0]}".upper()
        return self.name[:2].upper()


class Quote(Base):
    __tablename__ = "quotes"

    id:           Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quote_key:    Mapped[str]          = mapped_column(String(30), unique=True, nullable=False, index=True)
    branch_id:    Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    customer_id:  Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    created_by_id:Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status:       Mapped[QuoteStatus]  = mapped_column(SAEnum(QuoteStatus), nullable=False, default=QuoteStatus.draft)
    channel:      Mapped[SaleChannel]  = mapped_column(SAEnum(SaleChannel), nullable=False, default=SaleChannel.counter)
    total_amount: Mapped[float]        = mapped_column(Numeric(14, 2), nullable=False, default=0)
    notes:        Mapped[str|None]     = mapped_column(Text)
    items:        Mapped[list]         = mapped_column(JSON, default=list)
    expires_at:   Mapped[datetime|None]= mapped_column(DateTime(timezone=True))
    created_at:   Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:   Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    customer:   Mapped["Customer|None"] = relationship("Customer", back_populates="quotes")
    branch:     Mapped["Branch"]        = relationship("Branch")  # type: ignore
    created_by: Mapped["User"]          = relationship("User")    # type: ignore


class Sale(Base):
    __tablename__ = "sales"

    id:               Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sale_key:         Mapped[str]          = mapped_column(String(30), unique=True, nullable=False, index=True)
    branch_id:        Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    customer_id:      Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    seller_id:        Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    quote_id:         Mapped[uuid.UUID|None] = mapped_column(UUID(as_uuid=True), ForeignKey("quotes.id"))
    status:           Mapped[SaleStatus]   = mapped_column(SAEnum(SaleStatus), nullable=False, default=SaleStatus.confirmed)
    channel:          Mapped[SaleChannel]  = mapped_column(SAEnum(SaleChannel), nullable=False)
    payment_method:   Mapped[PaymentMethod]= mapped_column(SAEnum(PaymentMethod), nullable=False)
    total_amount:     Mapped[float]        = mapped_column(Numeric(14, 2), nullable=False)
    items:            Mapped[list]         = mapped_column(JSON, default=list)
    notes:            Mapped[str|None]     = mapped_column(Text)
    has_shipping:     Mapped[bool]         = mapped_column(Boolean, default=False)
    shipping_address: Mapped[str|None]     = mapped_column(Text)
    created_at:       Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:       Mapped[datetime]     = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    customer: Mapped["Customer|None"] = relationship("Customer", back_populates="sales")
    branch:   Mapped["Branch"]        = relationship("Branch")   # type: ignore
    seller:   Mapped["User|None"]     = relationship("User")     # type: ignore