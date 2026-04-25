import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from app.core.deps import CurrentUser, DbSession
from app.models.sales import Sale, Quote, Customer, SaleStatus, QuoteStatus, SaleChannel, PaymentMethod
from app.models.inventory import Part, PartStatus, PartStatusHistory

router = APIRouter(tags=["ventas"])

# ─── SCHEMAS ──────────────────────────────────────────────────────────────────
class CustomerOut(BaseModel):
    id:              uuid.UUID
    name:            str
    phone:           str | None = None
    email:           str | None = None
    customer_type:   str = "individual"
    is_frequent:     bool = False
    total_purchases: int = 0
    total_spent:     float = 0
    initials:        str = ""

class CustomerCreate(BaseModel):
    name:  str
    phone: str | None = None
    email: str | None = None

class SaleItemIn(BaseModel):
    part_id:      uuid.UUID
    unit_price:   float
    has_warranty: bool = False
    warranty_days:int | None = None

class QuoteCreate(BaseModel):
    branch_id:   uuid.UUID
    channel:     str = "counter"
    items:       list[SaleItemIn]
    customer_id: uuid.UUID | None = None
    notes:       str | None = None

class SaleCreate(BaseModel):
    branch_id:        uuid.UUID
    channel:          str = "counter"
    payment_method:   str = "cash"
    items:            list[SaleItemIn]
    customer_id:      uuid.UUID | None = None
    quote_id:         uuid.UUID | None = None
    notes:            str | None = None
    has_shipping:     bool = False
    shipping_address: str | None = None

class ConvertQuoteBody(BaseModel):
    payment_method:   str = "cash"
    has_shipping:     bool = False
    shipping_address: str | None = None

class QuoteStatusUpdate(BaseModel):
    status: str

class SaleOut(BaseModel):
    id:             uuid.UUID
    sale_key:       str
    branch_id:      uuid.UUID
    status:         str
    channel:        str
    payment_method: str
    total_amount:   float
    items:          list
    customer:       CustomerOut | None = None
    seller_name:    str | None = None
    notes:          str | None = None
    created_at:     datetime

class QuoteOut(BaseModel):
    id:           uuid.UUID
    quote_key:    str
    branch_id:    uuid.UUID
    status:       str
    channel:      str
    total_amount: float
    items:        list
    customer:     CustomerOut | None = None
    notes:        str | None = None
    expires_at:   datetime | None = None
    created_at:   datetime


def _customer_out(c: Customer | None) -> CustomerOut | None:
    if not c:
        return None
    return CustomerOut(
        id=c.id, name=c.name, phone=c.phone, email=c.email,
        customer_type=c.customer_type, is_frequent=c.is_frequent,
        total_purchases=c.total_purchases, total_spent=float(c.total_spent),
        initials=c.initials,
    )


async def _next_sale_key(db) -> str:
    from datetime import date
    ym = date.today().strftime("%Y%m")
    result = await db.execute(select(func.count(Sale.id)))
    count = result.scalar_one() + 1
    return f"VTA-{ym}-{count:04d}"


async def _next_quote_key(db) -> str:
    from datetime import date
    ym = date.today().strftime("%Y%m")
    result = await db.execute(select(func.count(Quote.id)))
    count = result.scalar_one() + 1
    return f"COT-{ym}-{count:04d}"


async def _build_items(db, items_in: list[SaleItemIn]) -> tuple[list[dict], float]:
    """Enriquece los items con datos de la pieza."""
    result_items = []
    total = 0.0
    for item in items_in:
        part = await db.get(Part, item.part_id)
        if not part:
            raise HTTPException(status_code=404, detail=f"Pieza {item.part_id} no encontrada")
        result_items.append({
            "part_id":      str(item.part_id),
            "part_key":     part.part_key,
            "part_name":    part.name,
            "brand":        part.brand,
            "model":        part.model,
            "unit_price":   item.unit_price,
            "has_warranty": item.has_warranty,
            "warranty_days":item.warranty_days,
        })
        total += item.unit_price
    return result_items, total


# ─── CUSTOMERS ────────────────────────────────────────────────────────────────
customers_router = APIRouter(prefix="/customers", tags=["clientes"])

@customers_router.get("", response_model=list[CustomerOut])
async def search_customers(db: DbSession, current_user: CurrentUser, q: str = ""):
    from sqlalchemy import or_
    stmt = select(Customer)
    if q:
        stmt = stmt.where(or_(Customer.name.ilike(f"%{q}%"), Customer.phone.ilike(f"%{q}%")))
    stmt = stmt.order_by(Customer.is_frequent.desc(), Customer.name).limit(50)
    customers = (await db.execute(stmt)).scalars().all()
    return [_customer_out(c) for c in customers]

@customers_router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(body: CustomerCreate, db: DbSession, current_user: CurrentUser):
    customer = Customer(name=body.name, phone=body.phone, email=body.email)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return _customer_out(customer)

router.include_router(customers_router)

# ─── QUOTES ───────────────────────────────────────────────────────────────────
quotes_router = APIRouter(prefix="/quotes", tags=["cotizaciones"])

@quotes_router.get("", response_model=list[QuoteOut])
async def list_quotes(db: DbSession, current_user: CurrentUser):
    stmt = select(Quote).options(selectinload(Quote.customer)).order_by(Quote.created_at.desc())
    quotes = (await db.execute(stmt)).scalars().all()
    return [QuoteOut(
        id=q.id, quote_key=q.quote_key, branch_id=q.branch_id,
        status=q.status.value, channel=q.channel.value,
        total_amount=float(q.total_amount), items=q.items or [],
        customer=_customer_out(q.customer), notes=q.notes,
        expires_at=q.expires_at, created_at=q.created_at,
    ) for q in quotes]

@quotes_router.post("", response_model=QuoteOut, status_code=status.HTTP_201_CREATED)
async def create_quote(body: QuoteCreate, db: DbSession, current_user: CurrentUser):
    items, total = await _build_items(db, body.items)
    quote_key = await _next_quote_key(db)

    quote = Quote(
        quote_key=quote_key,
        branch_id=body.branch_id,
        customer_id=body.customer_id,
        created_by_id=current_user.id,
        status=QuoteStatus.draft,
        channel=SaleChannel(body.channel),
        total_amount=total,
        items=items,
        notes=body.notes,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)

    customer = await db.get(Customer, quote.customer_id) if quote.customer_id else None
    return QuoteOut(
        id=quote.id, quote_key=quote.quote_key, branch_id=quote.branch_id,
        status=quote.status.value, channel=quote.channel.value,
        total_amount=float(quote.total_amount), items=quote.items or [],
        customer=_customer_out(customer), notes=quote.notes,
        expires_at=quote.expires_at, created_at=quote.created_at,
    )

@quotes_router.patch("/{quote_id}", response_model=QuoteOut)
async def update_quote_status(quote_id: uuid.UUID, body: QuoteStatusUpdate, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(Quote).options(selectinload(Quote.customer)).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    quote.status = QuoteStatus(body.status)
    await db.commit()
    return QuoteOut(
        id=quote.id, quote_key=quote.quote_key, branch_id=quote.branch_id,
        status=quote.status.value, channel=quote.channel.value,
        total_amount=float(quote.total_amount), items=quote.items or [],
        customer=_customer_out(quote.customer), notes=quote.notes,
        expires_at=quote.expires_at, created_at=quote.created_at,
    )

@quotes_router.post("/{quote_id}/convert", response_model=SaleOut)
async def convert_quote(quote_id: uuid.UUID, body: ConvertQuoteBody, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(Quote).options(selectinload(Quote.customer)).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    quote.status = QuoteStatus.converted
    sale_key = await _next_sale_key(db)

    sale = Sale(
        sale_key=sale_key,
        branch_id=quote.branch_id,
        customer_id=quote.customer_id,
        seller_id=current_user.id,
        quote_id=quote_id,
        status=SaleStatus.confirmed,
        channel=quote.channel,
        payment_method=PaymentMethod(body.payment_method),
        total_amount=quote.total_amount,
        items=quote.items,
        notes=quote.notes,
        has_shipping=body.has_shipping,
        shipping_address=body.shipping_address,
    )
    db.add(sale)
    await db.commit()
    await db.refresh(sale)

    customer = await db.get(Customer, sale.customer_id) if sale.customer_id else None
    return SaleOut(
        id=sale.id, sale_key=sale.sale_key, branch_id=sale.branch_id,
        status=sale.status.value, channel=sale.channel.value,
        payment_method=sale.payment_method.value,
        total_amount=float(sale.total_amount), items=sale.items or [],
        customer=_customer_out(customer), notes=sale.notes,
        seller_name=current_user.full_name, created_at=sale.created_at,
    )

router.include_router(quotes_router)

# ─── SALES ────────────────────────────────────────────────────────────────────
sales_router = APIRouter(prefix="/sales", tags=["ventas"])

@sales_router.get("", response_model=list[SaleOut])
async def list_sales(db: DbSession, current_user: CurrentUser):
    stmt = select(Sale).options(selectinload(Sale.customer), selectinload(Sale.seller)).order_by(Sale.created_at.desc())
    sales = (await db.execute(stmt)).scalars().all()
    return [SaleOut(
        id=s.id, sale_key=s.sale_key, branch_id=s.branch_id,
        status=s.status.value, channel=s.channel.value,
        payment_method=s.payment_method.value,
        total_amount=float(s.total_amount), items=s.items or [],
        customer=_customer_out(s.customer),
        seller_name=s.seller.full_name if s.seller else None,
        notes=s.notes, created_at=s.created_at,
    ) for s in sales]

@sales_router.post("", response_model=SaleOut, status_code=status.HTTP_201_CREATED)
async def create_sale(body: SaleCreate, db: DbSession, current_user: CurrentUser):
    items, total = await _build_items(db, body.items)
    sale_key = await _next_sale_key(db)

    sale = Sale(
        sale_key=sale_key,
        branch_id=body.branch_id,
        customer_id=body.customer_id,
        seller_id=current_user.id,
        quote_id=body.quote_id,
        status=SaleStatus.confirmed,
        channel=SaleChannel(body.channel),
        payment_method=PaymentMethod(body.payment_method),
        total_amount=total,
        items=items,
        notes=body.notes,
        has_shipping=body.has_shipping,
        shipping_address=body.shipping_address,
    )
    db.add(sale)

    # Marcar piezas como vendidas
    for item in body.items:
        part = await db.get(Part, item.part_id)
        if part:
            prev = part.status
            part.status = PartStatus.sold
            db.add(PartStatusHistory(
                part_id=part.id,
                previous_status=prev,
                new_status=PartStatus.sold,
                changed_by_id=current_user.id,
            ))

    await db.commit()
    await db.refresh(sale)

    customer = await db.get(Customer, sale.customer_id) if sale.customer_id else None
    return SaleOut(
        id=sale.id, sale_key=sale.sale_key, branch_id=sale.branch_id,
        status=sale.status.value, channel=sale.channel.value,
        payment_method=sale.payment_method.value,
        total_amount=float(sale.total_amount), items=sale.items or [],
        customer=_customer_out(customer), notes=sale.notes,
        seller_name=current_user.full_name, created_at=sale.created_at,
    )

router.include_router(sales_router)