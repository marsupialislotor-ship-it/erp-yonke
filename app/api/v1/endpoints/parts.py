import uuid
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from app.core.deps import CurrentUser, DbSession
from app.models.inventory import Part, PartCondition, PartStatus, Vehicle
from app.schemas.inventory import (
    PaginatedParts, PartListItem, PartDetail, PartCreate, PartUpdate, PartConditionOut,
)

router = APIRouter(prefix="/parts", tags=["inventario"])


# ─── GET /parts ───────────────────────────────────────────────────────────────
@router.get("", response_model=PaginatedParts)
async def list_parts(
    db:           DbSession,
    current_user: CurrentUser,
    q:            str | None = Query(None, description="Búsqueda libre"),
    brand:        str | None = None,
    model:        str | None = None,
    year:         int | None = None,
    condition_id: uuid.UUID | None = None,
    status:       str | None = None,
    branch_id:    uuid.UUID | None = None,
    price_min:    float | None = None,
    price_max:    float | None = None,
    page:         int = Query(1, ge=1),
    limit:        int = Query(24, ge=1, le=100),
):
    stmt = (
        select(Part)
        .options(
            selectinload(Part.condition),
            selectinload(Part.media),
            selectinload(Part.branch),
            selectinload(Part.vehicle),
        )
        .where(Part.deleted_at.is_(None))
    )

    # Si no se especifica status, mostrar solo piezas disponibles
    if not status:
        stmt = stmt.where(Part.status.in_(['in_vehicle', 'in_stock']))

    # Filtros
    if q:
        stmt = stmt.where(or_(
            Part.name.ilike(f"%{q}%"),
            Part.brand.ilike(f"%{q}%"),
            Part.model.ilike(f"%{q}%"),
            Part.part_key.ilike(f"%{q}%"),
        ))
    if brand:
        stmt = stmt.where(Part.brand.ilike(f"%{brand}%"))
    if model:
        stmt = stmt.where(Part.model.ilike(f"%{model}%"))
    if year:
        stmt = stmt.where(Part.year_from <= year, Part.year_to >= year)
    if condition_id:
        stmt = stmt.where(Part.condition_id == condition_id)
    if status:
        stmt = stmt.where(Part.status == status)
    if price_min is not None:
        stmt = stmt.where(Part.sale_price >= price_min)
    if price_max is not None:
        stmt = stmt.where(Part.sale_price <= price_max)
    if branch_id:
        stmt = stmt.where(Part.branch_id == branch_id)

    # Total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Paginación
    stmt = stmt.order_by(Part.created_at.desc()).offset((page - 1) * limit).limit(limit)
    parts = (await db.execute(stmt)).scalars().all()

    items = [_part_to_list_item(p) for p in parts]
    return PaginatedParts(total=total, page=page, limit=limit, items=items)


# ─── GET /parts/{id} ──────────────────────────────────────────────────────────
@router.get("/{part_id}", response_model=PartDetail)
async def get_part(part_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    part = await _get_part_or_404(db, part_id)
    return _part_to_detail(part)


# ─── GET /parts/qr/{part_key} ─────────────────────────────────────────────────
@router.get("/qr/{part_key}", response_model=dict)
async def get_part_by_qr(part_key: str, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(Part)
        .options(selectinload(Part.condition), selectinload(Part.media),
                 selectinload(Part.branch), selectinload(Part.vehicle))
        .where(Part.part_key == part_key.upper())
        .where(Part.deleted_at.is_(None))
    )
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Pieza no encontrada")
    return {"part": _part_to_detail(part)}

# ─── POST /parts ──────────────────────────────────────────────────────────────
@router.post("", response_model=PartDetail, status_code=status.HTTP_201_CREATED)
async def create_part(body: PartCreate, db: DbSession, current_user: CurrentUser):
    vehicle = await db.get(Vehicle, body.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    count_result = await db.execute(
        select(func.count()).where(Part.vehicle_id == body.vehicle_id)
    )
    part_count = count_result.scalar_one() + 1
    part_key = f"{vehicle.vehicle_key}-P{part_count:03d}"

    part = Part(
        part_key=part_key,
        vehicle_id=body.vehicle_id,
        branch_id=body.branch_id,
        name=body.name,
        brand=body.brand,
        model=body.model,
        year_from=body.year_from,
        year_to=body.year_to,
        specifications=body.specifications,
        observations=body.observations,
        condition_id=body.condition_id,
        sale_price=body.sale_price,
        has_warranty=body.has_warranty,
        warranty_days=body.warranty_days,
        status=PartStatus.in_vehicle,
        registered_by_id=current_user.id,
    )
    db.add(part)
    await db.flush()
    await db.refresh(part, ["condition", "media", "branch", "vehicle"])
    await db.commit()
    return _part_to_detail(part)

# ─── POST /parts/{id}/media ───────────────────────────────────────────────────
class PartMediaCreate(BaseModel):
    storage_path: str      # URL pública de Supabase Storage
    is_main:      bool = False
    sort_order:   int = 0

@router.post("/{part_id}/media", response_model=PartDetail, status_code=status.HTTP_201_CREATED)
async def add_part_media(
    part_id: uuid.UUID,
    body: PartMediaCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    part = await _get_part_or_404(db, part_id)

    # Si es la primera foto, marcarla como principal automáticamente
    existing_count = await db.execute(
        select(func.count()).where(
            select(func.count())
            .where(Part.id == part_id)
            .correlate()
        )
    )
    
    from app.models.inventory import PartMedia, MediaType
    
    # Contar fotos existentes
    media_count = await db.execute(
        select(func.count()).select_from(PartMedia).where(PartMedia.part_id == part_id)
    )
    count = media_count.scalar_one()
    is_main = body.is_main or count == 0  # primera foto = principal

    media = PartMedia(
        part_id=part_id,
        media_type=MediaType.photo,
        storage_path=body.storage_path,
        is_main=is_main,
        sort_order=body.sort_order if body.sort_order else count,
    )
    db.add(media)
    await db.commit()
    await db.refresh(part, ["condition", "media", "branch", "vehicle"])
    return _part_to_detail(part)

# ─── PATCH /parts/{id} ────────────────────────────────────────────────────────
@router.patch("/{part_id}", response_model=PartDetail)
async def update_part(
    part_id: uuid.UUID, body: PartUpdate,
    db: DbSession, current_user: CurrentUser
):
    part = await _get_part_or_404(db, part_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(part, field, value)
    await db.commit()
    await db.refresh(part, ["condition", "media", "branch", "vehicle"])
    return _part_to_detail(part)


# ─── GET /conditions ──────────────────────────────────────────────────────────
@router.get("/conditions/all", response_model=list[PartConditionOut], tags=["catálogos"])
async def list_conditions(db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(PartCondition)
        .where(PartCondition.is_active.is_(True))
        .order_by(PartCondition.sort_order)
    )
    return result.scalars().all()


# ─── HELPERS ──────────────────────────────────────────────────────────────────
async def _get_part_or_404(db: DbSession, part_id: uuid.UUID) -> Part:
    result = await db.execute(
        select(Part)
        .options(selectinload(Part.condition), selectinload(Part.media),
                 selectinload(Part.branch), selectinload(Part.vehicle))
        .where(Part.id == part_id)
        .where(Part.deleted_at.is_(None))
    )
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Pieza no encontrada")
    return part


def _part_to_list_item(p: Part) -> PartListItem:
    return PartListItem(
        id=p.id,
        part_key=p.part_key,
        vehicle_id=p.vehicle_id,
        branch_id=p.branch_id,
        branch_name=p.branch.name if p.branch else "",
        name=p.name,
        brand=p.brand,
        model=p.model,
        year_from=p.year_from,
        year_to=p.year_to,
        condition=p.condition.name if p.condition else None,
        status=p.status.value,
        sale_price=float(p.sale_price),
        main_photo_url=p.main_photo_url,
        has_video=any(m.media_type.value == "video" for m in p.media),
        vehicle_key=p.vehicle.vehicle_key if p.vehicle else None,
    )


def _part_to_detail(p: Part) -> PartDetail:
    from app.schemas.inventory import PartMediaOut, PartConditionOut
    return PartDetail(
        id=p.id,
        part_key=p.part_key,
        vehicle_id=p.vehicle_id,
        branch_id=p.branch_id,
        branch_name=p.branch.name if p.branch else "",
        name=p.name,
        brand=p.brand,
        model=p.model,
        year_from=p.year_from,
        year_to=p.year_to,
        specifications=p.specifications,
        observations=p.observations,
        condition=PartConditionOut(
            id=p.condition.id,
            name=p.condition.name,
            description=p.condition.description,
            sort_order=p.condition.sort_order,
        ) if p.condition else None,
        status=p.status.value,
        sale_price=float(p.sale_price),
        has_warranty=p.has_warranty,
        warranty_days=p.warranty_days,
        media=[
            PartMediaOut(
                id=m.id,
                media_type=m.media_type.value,
                storage_path=m.storage_path,
                thumbnail_path=m.thumbnail_path,
                is_main=m.is_main,
                sort_order=m.sort_order,
                display_url=m.thumbnail_path or m.storage_path,
            )
            for m in sorted(p.media, key=lambda x: x.sort_order)
        ],
        main_photo_url=p.main_photo_url,
        vehicle_key=p.vehicle.vehicle_key if p.vehicle else None,
        created_at=p.created_at,
    )