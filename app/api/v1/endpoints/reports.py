import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_
from pydantic import BaseModel
from app.core.deps import CurrentUser, DbSession
from app.models.sales import Sale, Quote, SaleStatus, QuoteStatus
from app.models.orders import DisassemblyOrder, OrderStatus
from app.models.inventory import Part, PartStatus
from app.models.user import User, UserRole

router = APIRouter(prefix="/reports", tags=["reportes"])


# ─── SCHEMAS ──────────────────────────────────────────────────────────────────
class PeriodSummary(BaseModel):
    total_sales:         int = 0
    total_revenue:       float = 0.0
    total_quotes:        int = 0
    converted_quotes:    int = 0
    conversion_rate:     float = 0.0
    active_quotes:       int = 0
    pending_orders:      int = 0
    completed_orders:    int = 0
    parts_registered:    int = 0
    parts_sold:          int = 0
    parts_available:     int = 0

class SalesByDay(BaseModel):
    date:    str
    sales:   int
    revenue: float

class SalesByChannel(BaseModel):
    channel: str
    sales:   int
    revenue: float

class EmployeeActivity(BaseModel):
    user_id:           str
    user_name:         str
    role:              str
    sales_count:       int = 0
    sales_revenue:     float = 0.0
    quotes_count:      int = 0
    quotes_converted:  int = 0
    parts_registered:  int = 0
    orders_completed:  int = 0
    orders_taken:      int = 0

class ReportSummary(BaseModel):
    period:          str
    date_from:       datetime
    date_to:         datetime
    summary:         PeriodSummary
    sales_by_day:    list[SalesByDay] = []
    sales_by_channel:list[SalesByChannel] = []

class ActivityReport(BaseModel):
    period:     str
    date_from:  datetime
    date_to:    datetime
    employees:  list[EmployeeActivity] = []


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def _get_period_dates(period: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if period == "today":
        date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = now
    elif period == "week":
        date_from = now - timedelta(days=7)
        date_to = now
    elif period == "month":
        date_from = now - timedelta(days=30)
        date_to = now
    elif period == "year":
        date_from = now - timedelta(days=365)
        date_to = now
    else:  # default: month
        date_from = now - timedelta(days=30)
        date_to = now
    return date_from, date_to


# ─── GET /reports/summary ─────────────────────────────────────────────────────
@router.get("/summary", response_model=ReportSummary)
async def get_summary(
    db:           DbSession,
    current_user: CurrentUser,
    period:       str = Query("month", regex="^(today|week|month|year)$"),
    branch_id:    uuid.UUID | None = None,
):
    date_from, date_to = _get_period_dates(period)

    # Filtro base por período
    def period_filter(col):
        return and_(col >= date_from, col <= date_to)

    # ── Ventas ────────────────────────────────────────────────────────────────
    sales_q = select(Sale).where(period_filter(Sale.created_at))
    if branch_id:
        sales_q = sales_q.where(Sale.branch_id == branch_id)
    sales = (await db.execute(sales_q)).scalars().all()

    total_sales = len(sales)
    total_revenue = sum(float(s.total_amount) for s in sales)

    # ── Cotizaciones ──────────────────────────────────────────────────────────
    quotes_q = select(Quote).where(period_filter(Quote.created_at))
    if branch_id:
        quotes_q = quotes_q.where(Quote.branch_id == branch_id)
    quotes = (await db.execute(quotes_q)).scalars().all()

    total_quotes = len(quotes)
    converted_quotes = sum(1 for q in quotes if q.status == QuoteStatus.converted)
    active_quotes = sum(1 for q in quotes if q.status.value in ['draft', 'sent', 'accepted'])
    conversion_rate = (converted_quotes / total_quotes * 100) if total_quotes > 0 else 0.0

    # ── Órdenes de desmonte ───────────────────────────────────────────────────
    orders_q = select(DisassemblyOrder).where(period_filter(DisassemblyOrder.created_at))
    if branch_id:
        orders_q = orders_q.where(DisassemblyOrder.branch_id == branch_id)
    orders = (await db.execute(orders_q)).scalars().all()

    pending_orders = sum(1 for o in orders if o.status == OrderStatus.pending)
    completed_orders = sum(1 for o in orders if o.status == OrderStatus.completed)

    # ── Piezas ────────────────────────────────────────────────────────────────
    parts_registered_q = select(func.count(Part.id)).where(
        period_filter(Part.created_at)
    )
    parts_registered = (await db.execute(parts_registered_q)).scalar_one()

    parts_sold_q = select(func.count(Part.id)).where(
        Part.status == PartStatus.sold
    )
    parts_sold = (await db.execute(parts_sold_q)).scalar_one()

    parts_available_q = select(func.count(Part.id)).where(
        Part.status.in_([PartStatus.in_vehicle, PartStatus.in_stock]),
        Part.deleted_at.is_(None)
    )
    parts_available = (await db.execute(parts_available_q)).scalar_one()

    # ── Ventas por día ────────────────────────────────────────────────────────
    from sqlalchemy import cast, Date as SQLDate
    sales_by_day_q = (
        select(
            cast(Sale.created_at, SQLDate).label("date"),
            func.count(Sale.id).label("sales"),
            func.sum(Sale.total_amount).label("revenue"),
        )
        .where(period_filter(Sale.created_at))
        .group_by(cast(Sale.created_at, SQLDate))
        .order_by(cast(Sale.created_at, SQLDate))
    )
    if branch_id:
        sales_by_day_q = sales_by_day_q.where(Sale.branch_id == branch_id)
    sales_by_day_rows = (await db.execute(sales_by_day_q)).all()
    sales_by_day = [
        SalesByDay(
            date=str(row.date),
            sales=row.sales,
            revenue=float(row.revenue or 0),
        )
        for row in sales_by_day_rows
    ]

    # ── Ventas por canal ──────────────────────────────────────────────────────
    sales_by_channel_q = (
        select(
            Sale.channel,
            func.count(Sale.id).label("sales"),
            func.sum(Sale.total_amount).label("revenue"),
        )
        .where(period_filter(Sale.created_at))
        .group_by(Sale.channel)
    )
    if branch_id:
        sales_by_channel_q = sales_by_channel_q.where(Sale.branch_id == branch_id)
    sales_by_channel_rows = (await db.execute(sales_by_channel_q)).all()
    sales_by_channel = [
        SalesByChannel(
            channel=row.channel.value if hasattr(row.channel, 'value') else str(row.channel),
            sales=row.sales,
            revenue=float(row.revenue or 0),
        )
        for row in sales_by_channel_rows
    ]

    return ReportSummary(
        period=period,
        date_from=date_from,
        date_to=date_to,
        summary=PeriodSummary(
            total_sales=total_sales,
            total_revenue=total_revenue,
            total_quotes=total_quotes,
            converted_quotes=converted_quotes,
            conversion_rate=round(conversion_rate, 1),
            active_quotes=active_quotes,
            pending_orders=pending_orders,
            completed_orders=completed_orders,
            parts_registered=parts_registered,
            parts_sold=parts_sold,
            parts_available=parts_available,
        ),
        sales_by_day=sales_by_day,
        sales_by_channel=sales_by_channel,
    )


# ─── GET /reports/activity ────────────────────────────────────────────────────
@router.get("/activity", response_model=ActivityReport)
async def get_activity(
    db:           DbSession,
    current_user: CurrentUser,
    period:       str = Query("month", regex="^(today|week|month|year)$"),
    branch_id:    uuid.UUID | None = None,
):
    date_from, date_to = _get_period_dates(period)

    def period_filter(col):
        return and_(col >= date_from, col <= date_to)

    # Obtener todos los usuarios activos
    users_q = select(User).where(
        User.is_active.is_(True),
        User.deleted_at.is_(None),
    )
    if branch_id:
        users_q = users_q.where(User.branch_id == branch_id)
    users = (await db.execute(users_q)).scalars().all()

    employees = []
    for user in users:
        # Ventas
        sales_q = select(Sale).where(
            Sale.seller_id == user.id,
            period_filter(Sale.created_at),
        )
        user_sales = (await db.execute(sales_q)).scalars().all()
        sales_count = len(user_sales)
        sales_revenue = sum(float(s.total_amount) for s in user_sales)

        # Cotizaciones
        quotes_q = select(Quote).where(
            Quote.created_by_id == user.id,
            period_filter(Quote.created_at),
        )
        user_quotes = (await db.execute(quotes_q)).scalars().all()
        quotes_count = len(user_quotes)
        quotes_converted = sum(1 for q in user_quotes if q.status == QuoteStatus.converted)

        # Piezas registradas
        parts_q = select(func.count(Part.id)).where(
            Part.registered_by_id == user.id,
            period_filter(Part.created_at),
        )
        parts_registered = (await db.execute(parts_q)).scalar_one()

        # Órdenes completadas
        orders_completed_q = select(func.count(DisassemblyOrder.id)).where(
            DisassemblyOrder.assigned_to_id == user.id,
            DisassemblyOrder.status == OrderStatus.completed,
            period_filter(DisassemblyOrder.completed_at),
        )
        orders_completed = (await db.execute(orders_completed_q)).scalar_one()

        # Órdenes tomadas
        orders_taken_q = select(func.count(DisassemblyOrder.id)).where(
            DisassemblyOrder.assigned_to_id == user.id,
            period_filter(DisassemblyOrder.created_at),
        )
        orders_taken = (await db.execute(orders_taken_q)).scalar_one()

        # Solo incluir usuarios con alguna actividad o rol relevante
        employees.append(EmployeeActivity(
            user_id=str(user.id),
            user_name=user.full_name,
            role=user.role.value,
            sales_count=sales_count,
            sales_revenue=sales_revenue,
            quotes_count=quotes_count,
            quotes_converted=quotes_converted,
            parts_registered=parts_registered,
            orders_completed=orders_completed,
            orders_taken=orders_taken,
        ))

    # Ordenar por ventas desc
    employees.sort(key=lambda e: e.sales_revenue, reverse=True)

    return ActivityReport(
        period=period,
        date_from=date_from,
        date_to=date_to,
        employees=employees,
    )