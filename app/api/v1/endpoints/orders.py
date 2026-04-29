import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from app.core.deps import CurrentUser, DbSession
from app.models.orders import DisassemblyOrder, OrderStatus, OrderPriority
from app.models.inventory import Part, PartStatus, PartStatusHistory
from app.models.user import User

router = APIRouter(prefix="/disassembly-orders", tags=["órdenes de desmonte"])


# ─── SCHEMAS ──────────────────────────────────────────────────────────────────
class OrderOut(BaseModel):
    id:               uuid.UUID
    order_key:        str
    part_id:          uuid.UUID
    part_name:        str = ""
    vehicle_id:       uuid.UUID
    vehicle_key:      str = ""
    vehicle_desc:     str = ""
    branch_id:        uuid.UUID
    branch_name:      str = ""
    status:           str
    priority:         str
    instructions:     str | None = None
    created_by_id:    uuid.UUID
    created_by_name:  str = ""
    assigned_to_id:   uuid.UUID | None = None
    assigned_to_name: str | None = None
    assigned_at:      datetime | None = None
    started_at:       datetime | None = None
    completed_at:     datetime | None = None
    completion_notes: str | None = None
    created_at:       datetime
    minutes_ago:      int = 0


class OrderCreate(BaseModel):
    part_id:      uuid.UUID
    branch_id:    uuid.UUID
    priority:     str = "normal"
    instructions: str | None = None


class CompleteOrderBody(BaseModel):
    completion_notes: str
    photo_urls:       list[str] = []


class CancelOrderBody(BaseModel):
    reason: str


async def _next_order_key(db) -> str:
    from datetime import date
    today = date.today().strftime("%Y%m%d")
    result = await db.execute(
        select(func.count(DisassemblyOrder.id))
        .where(func.date(DisassemblyOrder.created_at) == date.today())
    )
    count = result.scalar_one() + 1
    return f"ORD-{today}-{count:04d}"


def _order_out(o: DisassemblyOrder) -> OrderOut:
    return OrderOut(
        id=o.id, order_key=o.order_key,
        part_id=o.part_id,
        part_name=o.part.name if o.part else "",
        vehicle_id=o.vehicle_id,
        vehicle_key=o.vehicle.vehicle_key if o.vehicle else "",
        vehicle_desc=f"{o.vehicle.brand} {o.vehicle.model} {o.vehicle.year}" if o.vehicle else "",
        branch_id=o.branch_id,
        branch_name=o.branch.name if o.branch else "",
        status=o.status.value,
        priority=o.priority.value,
        instructions=o.instructions,
        created_by_id=o.created_by_id,
        created_by_name=o.created_by.full_name if o.created_by else "",
        assigned_to_id=o.assigned_to_id,
        assigned_to_name=o.assigned_to.full_name if o.assigned_to else None,
        assigned_at=o.assigned_at,
        started_at=o.started_at,
        completed_at=o.completed_at,
        completion_notes=o.completion_notes,
        created_at=o.created_at,
        minutes_ago=o.minutes_ago,
    )


def _order_opts():
    return [
        selectinload(DisassemblyOrder.part),
        selectinload(DisassemblyOrder.vehicle),
        selectinload(DisassemblyOrder.branch),
        selectinload(DisassemblyOrder.created_by),
        selectinload(DisassemblyOrder.assigned_to),
    ]


# ─── GET /disassembly-orders ──────────────────────────────────────────────────
@router.get("", response_model=list[OrderOut])
async def list_orders(
    db:           DbSession,
    current_user: CurrentUser,
    status:       str | None = None,
    branch_id:    uuid.UUID | None = None,
):
    stmt = select(DisassemblyOrder).options(*_order_opts())

    if status:
        stmt = stmt.where(DisassemblyOrder.status == status)
    if branch_id:
        stmt = stmt.where(DisassemblyOrder.branch_id == branch_id)
    else:
        # Mecánicos y ayudantes solo ven su sucursal
        from app.models.user import UserRole
        if current_user.role in [UserRole.mechanic, UserRole.helper]:
            stmt = stmt.where(DisassemblyOrder.branch_id == current_user.branch_id)

    # Ordenar: urgentes primero, luego por fecha
    stmt = stmt.order_by(
        DisassemblyOrder.priority.desc(),
        DisassemblyOrder.created_at.desc(),
    )

    orders = (await db.execute(stmt)).scalars().all()
    return [_order_out(o) for o in orders]


# ─── POST /disassembly-orders ─────────────────────────────────────────────────
@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(body: OrderCreate, db: DbSession, current_user: CurrentUser):
    part = await db.get(Part, body.part_id)
    if not part:
        raise HTTPException(status_code=404, detail="Pieza no encontrada")

    order_key = await _next_order_key(db)

    order = DisassemblyOrder(
        order_key=order_key,
        part_id=body.part_id,
        vehicle_id=part.vehicle_id,
        branch_id=body.branch_id,
        priority=OrderPriority(body.priority),
        instructions=body.instructions,
        created_by_id=current_user.id,
        status=OrderStatus.pending,
    )
    db.add(order)

    # Actualizar estado de la pieza
    part.status = PartStatus.dismounting
    db.add(PartStatusHistory(
        part_id=part.id,
        previous_status=PartStatus.in_vehicle,
        new_status=PartStatus.dismounting,
        changed_by_id=current_user.id,
    ))

    await db.commit()
    await db.refresh(order)

    result = await db.execute(
        select(DisassemblyOrder).options(*_order_opts()).where(DisassemblyOrder.id == order.id)
    )
    order_out = _order_out(result.scalar_one())

    # ── Enviar notificación a mecánicos y ayudantes de la sucursal ──────────
    try:
        from app.core.firebase import send_notification
        from app.models.user import UserRole

        # Obtener tokens FCM de mecánicos y ayudantes de esa sucursal
        mechanics = await db.execute(
            select(User).where(
                User.branch_id == body.branch_id,
                User.role.in_([UserRole.mechanic, UserRole.helper]),
                User.is_active.is_(True),
                User.fcm_token.isnot(None),
            )
        )
        tokens = [u.fcm_token for u in mechanics.scalars().all()]

        if tokens:
            is_urgent = body.priority == "urgent"
            await send_notification(
                fcm_tokens=tokens,
                title="🔧 Nueva orden de desmonte" + (" 🚨 URGENTE" if is_urgent else ""),
                body=f"{part.name} — {order_key}",
                data={
                    "order_id": str(order.id),
                    "order_key": order_key,
                    "type": "new_order",
                },
                is_urgent=is_urgent,
            )
    except Exception as e:
        print(f"Error enviando notificación: {e}")
        # No interrumpir el flujo si falla la notificación

    return order_out


# ─── POST /disassembly-orders/{id}/take ───────────────────────────────────────
@router.post("/{order_id}/take", response_model=OrderOut)
async def take_order(order_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(DisassemblyOrder).options(*_order_opts()).where(DisassemblyOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if order.status != OrderStatus.pending:
        raise HTTPException(status_code=400, detail="La orden ya fue tomada")

    order.status      = OrderStatus.taken
    order.assigned_to_id = current_user.id
    order.assigned_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(order)

    result = await db.execute(
        select(DisassemblyOrder).options(*_order_opts()).where(DisassemblyOrder.id == order.id)
    )
    return _order_out(result.scalar_one())


# ─── POST /disassembly-orders/{id}/start ──────────────────────────────────────
@router.post("/{order_id}/start", response_model=OrderOut)
async def start_order(order_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(DisassemblyOrder).options(*_order_opts()).where(DisassemblyOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if order.status != OrderStatus.taken:
        raise HTTPException(status_code=400, detail="La orden debe estar tomada para iniciar")

    order.status     = OrderStatus.in_progress
    order.started_at = datetime.now(timezone.utc)

    await db.commit()
    result = await db.execute(
        select(DisassemblyOrder).options(*_order_opts()).where(DisassemblyOrder.id == order.id)
    )
    return _order_out(result.scalar_one())


# ─── POST /disassembly-orders/{id}/complete ───────────────────────────────────
@router.post("/{order_id}/complete", response_model=OrderOut)
async def complete_order(order_id: uuid.UUID, body: CompleteOrderBody, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(DisassemblyOrder).options(*_order_opts()).where(DisassemblyOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    order.status          = OrderStatus.completed
    order.completed_at    = datetime.now(timezone.utc)
    order.completion_notes = body.completion_notes

    # Actualizar estado de la pieza a in_stock
    part = await db.get(Part, order.part_id)
    if part:
        prev = part.status
        part.status = PartStatus.in_stock
        db.add(PartStatusHistory(
            part_id=part.id,
            previous_status=prev,
            new_status=PartStatus.in_stock,
            reason=body.completion_notes,
            changed_by_id=current_user.id,
        ))

    await db.commit()
    result = await db.execute(
        select(DisassemblyOrder).options(*_order_opts()).where(DisassemblyOrder.id == order.id)
    )
    return _order_out(result.scalar_one())


# ─── POST /disassembly-orders/{id}/cancel ────────────────────────────────────
@router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(order_id: uuid.UUID, body: CancelOrderBody, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(DisassemblyOrder).options(*_order_opts()).where(DisassemblyOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    order.status       = OrderStatus.cancelled
    order.cancelled_at = datetime.now(timezone.utc)
    order.cancel_reason = body.reason

    # Revertir estado de la pieza
    part = await db.get(Part, order.part_id)
    if part and part.status == PartStatus.dismounting:
        part.status = PartStatus.in_vehicle

    await db.commit()
    result = await db.execute(
        select(DisassemblyOrder).options(*_order_opts()).where(DisassemblyOrder.id == order.id)
    )
    return _order_out(result.scalar_one())