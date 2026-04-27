# ══════════════════════════════════════════════════════════════════════════════
# CAMBIO 1: backend/app/schemas/inventory.py
# Reemplaza la clase VehicleCreate con esta versión
# ══════════════════════════════════════════════════════════════════════════════

# class VehicleCreate(BaseModel):
#     branch_id:         UUID
#     brand:             str
#     model:             str
#     year:              int
#     color:             str | None = None
#     purchase_origin:   str        = "private"   # default: particular
#     purchase_cost:     float      = 0.0          # default: 0
#     purchase_date:     datetime   | None = None  # default: hoy
#     general_condition: str | None = None
#     notes:             str | None = None
#     seller_name:       str | None = None
#     seller_phone:      str | None = None


# ══════════════════════════════════════════════════════════════════════════════
# CAMBIO 2: backend/app/api/v1/endpoints/vehicles.py
# Reemplaza el archivo completo con este contenido
# ══════════════════════════════════════════════════════════════════════════════

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from app.core.deps import CurrentUser, DbSession
from app.models.inventory import Vehicle, VehicleStatus, VehiclePhoto, Part, PurchaseOrigin
from app.schemas.inventory import VehicleCreate, VehicleOut

router = APIRouter(prefix="/vehicles", tags=["vehículos"])


# ─── SCHEMAS LOCALES ──────────────────────────────────────────────────────────
class VehicleDetail(BaseModel):
    id:                uuid.UUID
    vehicle_key:       str
    branch_id:         uuid.UUID
    branch_name:       str = ""
    brand:             str
    model:             str
    year:              int
    color:             str | None = None
    status:            str
    purchase_origin:   str
    purchase_cost:     float
    purchase_date:     datetime
    general_condition: str | None = None
    notes:             str | None = None
    seller_name:       str | None = None
    seller_phone:      str | None = None
    parts_count:       int = 0
    created_at:        datetime

    model_config = {"from_attributes": True}


class PaginatedVehicles(BaseModel):
    total: int
    page:  int
    limit: int
    items: list[VehicleOut]


async def _next_vehicle_key(db, branch_code: str = "VEH") -> str:
    year = datetime.now().year
    result = await db.execute(
        select(func.count(Vehicle.id))
        .where(func.extract("year", Vehicle.created_at) == year)
    )
    count = result.scalar_one() + 1
    return f"VEH-{year}-{count:04d}"


# ─── GET /vehicles ────────────────────────────────────────────────────────────
@router.get("", response_model=PaginatedVehicles)
async def list_vehicles(
    db:           DbSession,
    current_user: CurrentUser,
    branch_id:    uuid.UUID | None = None,
    status:       str | None = None,
    q:            str | None = None,
    page:         int = Query(1, ge=1),
    limit:        int = Query(20, ge=1, le=100),
):
    from sqlalchemy import or_
    stmt = select(Vehicle).options(selectinload(Vehicle.branch))

    if branch_id:
        stmt = stmt.where(Vehicle.branch_id == branch_id)
    if status:
        stmt = stmt.where(Vehicle.status == status)
    if q:
        stmt = stmt.where(or_(
            Vehicle.brand.ilike(f"%{q}%"),
            Vehicle.model.ilike(f"%{q}%"),
            Vehicle.vehicle_key.ilike(f"%{q}%"),
        ))

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()

    vehicles = (await db.execute(
        stmt.order_by(Vehicle.created_at.desc()).offset((page-1)*limit).limit(limit)
    )).scalars().all()

    items = [VehicleOut(
        id=v.id, vehicle_key=v.vehicle_key, branch_id=v.branch_id,
        brand=v.brand, model=v.model, year=v.year, color=v.color,
        status=v.status.value,
        purchase_cost=float(v.purchase_cost),
        purchase_date=v.purchase_date,
        notes=v.notes, created_at=v.created_at,
    ) for v in vehicles]

    return PaginatedVehicles(total=total, page=page, limit=limit, items=items)


# ─── POST /vehicles ───────────────────────────────────────────────────────────
@router.post("", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
async def create_vehicle(body: VehicleCreate, db: DbSession, current_user: CurrentUser):
    vehicle_key = await _next_vehicle_key(db)

    # Campos opcionales con defaults
    purchase_origin = PurchaseOrigin(body.purchase_origin) if body.purchase_origin else PurchaseOrigin.private
    purchase_cost   = body.purchase_cost if body.purchase_cost is not None else 0.0
    purchase_date   = body.purchase_date if body.purchase_date else datetime.now(timezone.utc)

    vehicle = Vehicle(
        vehicle_key=vehicle_key,
        branch_id=body.branch_id,
        brand=body.brand,
        model=body.model,
        year=body.year,
        color=body.color,
        purchase_origin=purchase_origin,
        purchase_cost=purchase_cost,
        purchase_date=purchase_date,
        status=VehicleStatus.complete,
        general_condition=body.general_condition,
        notes=body.notes,
        seller_name=body.seller_name,
        seller_phone=body.seller_phone,
        registered_by_id=current_user.id,
    )
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)

    return VehicleOut(
        id=vehicle.id, vehicle_key=vehicle.vehicle_key, branch_id=vehicle.branch_id,
        brand=vehicle.brand, model=vehicle.model, year=vehicle.year, color=vehicle.color,
        status=vehicle.status.value,
        purchase_cost=float(vehicle.purchase_cost),
        purchase_date=vehicle.purchase_date,
        notes=vehicle.notes, created_at=vehicle.created_at,
    )


# ─── GET /vehicles/{id} ───────────────────────────────────────────────────────
@router.get("/{vehicle_id}", response_model=VehicleDetail)
async def get_vehicle(vehicle_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(Vehicle)
        .options(selectinload(Vehicle.branch), selectinload(Vehicle.parts))
        .where(Vehicle.id == vehicle_id)
    )
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    return VehicleDetail(
        id=vehicle.id, vehicle_key=vehicle.vehicle_key,
        branch_id=vehicle.branch_id,
        branch_name=vehicle.branch.name if vehicle.branch else "",
        brand=vehicle.brand, model=vehicle.model, year=vehicle.year,
        color=vehicle.color, status=vehicle.status.value,
        purchase_origin=vehicle.purchase_origin.value,
        purchase_cost=float(vehicle.purchase_cost),
        purchase_date=vehicle.purchase_date,
        general_condition=vehicle.general_condition,
        notes=vehicle.notes, seller_name=vehicle.seller_name,
        seller_phone=vehicle.seller_phone,
        parts_count=len(vehicle.parts),
        created_at=vehicle.created_at,
    )


# ─── GET /vehicles/qr/{key} ───────────────────────────────────────────────────
@router.get("/qr/{vehicle_key}", response_model=dict)
async def get_vehicle_by_qr(vehicle_key: str, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(Vehicle)
        .options(selectinload(Vehicle.branch))
        .where(Vehicle.vehicle_key == vehicle_key.upper())
    )
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    return {
        "vehicle": VehicleDetail(
            id=vehicle.id, vehicle_key=vehicle.vehicle_key,
            branch_id=vehicle.branch_id,
            branch_name=vehicle.branch.name if vehicle.branch else "",
            brand=vehicle.brand, model=vehicle.model, year=vehicle.year,
            color=vehicle.color, status=vehicle.status.value,
            purchase_origin=vehicle.purchase_origin.value,
            purchase_cost=float(vehicle.purchase_cost),
            purchase_date=vehicle.purchase_date,
            general_condition=vehicle.general_condition,
            notes=vehicle.notes, seller_name=vehicle.seller_name,
            seller_phone=vehicle.seller_phone,
            parts_count=0, created_at=vehicle.created_at,
        )
    }