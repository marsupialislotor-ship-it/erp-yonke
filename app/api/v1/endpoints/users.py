import uuid
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, EmailStr
from app.core.deps import CurrentUser, DbSession, OwnerOrAdmin
from app.core.security import hash_password
from app.models.user import User, UserRole, Branch
from app.schemas.auth import UserOut, BranchOut

router = APIRouter(prefix="/users", tags=["usuarios"])


# ─── SCHEMAS ──────────────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    email:     EmailStr
    password:  str
    full_name: str
    phone:     str | None = None
    role:      UserRole
    branch_id: uuid.UUID


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone:     str | None = None
    role:      UserRole | None = None
    branch_id: uuid.UUID | None = None
    is_active: bool | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password:     str


class PaginatedUsers(BaseModel):
    total: int
    page:  int
    limit: int
    items: list[UserOut]


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        phone=user.phone,
        initials=user.initials,
        dashboard_config=user.dashboard_config,
        branch=BranchOut(
            id=user.branch.id,
            name=user.branch.name,
            code=user.branch.code,
            is_headquarters=user.branch.is_headquarters,
        ),
    )


# ─── GET /users/me ────────────────────────────────────────────────────────────
@router.get("/me", response_model=UserOut)
async def get_me(current_user: CurrentUser, db: DbSession):
    result = await db.execute(
        select(User).options(selectinload(User.branch)).where(User.id == current_user.id)
    )
    user = result.scalar_one()
    return _user_out(user)


# ─── GET /users ───────────────────────────────────────────────────────────────
@router.get("", response_model=PaginatedUsers, dependencies=[])
async def list_users(
    db:           DbSession,
    current_user: OwnerOrAdmin,
    branch_id:    uuid.UUID | None = None,
    role:         UserRole | None = None,
    q:            str | None = None,
    page:         int = Query(1, ge=1),
    limit:        int = Query(50, ge=1, le=200),
):
    stmt = (
        select(User)
        .options(selectinload(User.branch))
        .where(User.deleted_at.is_(None))
    )
    if branch_id:
        stmt = stmt.where(User.branch_id == branch_id)
    if role:
        stmt = stmt.where(User.role == role)
    if q:
        stmt = stmt.where(User.full_name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    users = (await db.execute(stmt.order_by(User.full_name).offset((page-1)*limit).limit(limit))).scalars().all()

    return PaginatedUsers(total=total, page=page, limit=limit, items=[_user_out(u) for u in users])


# ─── POST /users ──────────────────────────────────────────────────────────────
@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, db: DbSession, current_user: OwnerOrAdmin):
    # Verificar email único
    exists = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo")

    # Verificar que la sucursal existe
    branch = await db.get(Branch, body.branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    user = User(
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        phone=body.phone,
        role=body.role,
        branch_id=body.branch_id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user, ["branch"])
    await db.commit()
    return _user_out(user)


# ─── PATCH /users/{id} ────────────────────────────────────────────────────────
@router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: uuid.UUID, body: UserUpdate, db: DbSession, current_user: OwnerOrAdmin):
    result = await db.execute(
        select(User).options(selectinload(User.branch)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user, ["branch"])
    return _user_out(user)


# ─── POST /users/{id}/change-password ────────────────────────────────────────
@router.post("/{user_id}/change-password")
async def change_password(user_id: uuid.UUID, body: PasswordChange, db: DbSession, current_user: CurrentUser):
    from app.core.security import verify_password
    # Solo el propio usuario o admin puede cambiar contraseña
    if current_user.id != user_id and current_user.role not in [UserRole.owner, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Sin permiso")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if current_user.id == user_id:
        if not verify_password(body.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")

    user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"message": "Contraseña actualizada"}