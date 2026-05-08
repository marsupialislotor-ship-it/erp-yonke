import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text
from pydantic import BaseModel
from app.core.deps import CurrentUser, DbSession
from app.models.user import User, UserRole

router = APIRouter(prefix="/permissions", tags=["permisos"])


# ─── SCHEMAS ──────────────────────────────────────────────────────────────────
class PermissionOut(BaseModel):
    code:        str
    label:       str
    category:    str
    description: str | None = None


class RolePermissionOut(BaseModel):
    role:            str
    permission_code: str
    is_enabled:      bool


class UserPermissionOut(BaseModel):
    user_id:         str
    permission_code: str
    is_enabled:      bool


class UpdateRolePermission(BaseModel):
    is_enabled: bool


class UpdateUserPermission(BaseModel):
    is_enabled: bool


class UserPermissionsOut(BaseModel):
    user_id:     str
    user_name:   str
    role:        str
    permissions: dict[str, bool]  # code -> effective value


# ─── GET /permissions ─────────────────────────────────────────────────────────
@router.get("", response_model=list[PermissionOut])
async def list_permissions(db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        text("SELECT code, label, category, description FROM permissions ORDER BY category, label")
    )
    return [PermissionOut(**dict(row._mapping)) for row in result]


# ─── GET /permissions/roles ───────────────────────────────────────────────────
@router.get("/roles", response_model=dict)
async def get_role_permissions(db: DbSession, current_user: CurrentUser):
    """
    Devuelve permisos agrupados por rol.
    { "seller": {"crear_cotizacion": true, ...}, ... }
    """
    result = await db.execute(
        text("SELECT role, permission_code, is_enabled FROM role_permissions ORDER BY role, permission_code")
    )
    rows = result.fetchall()

    out: dict = {}
    for row in rows:
        role = row.role
        if role not in out:
            out[role] = {}
        out[role][row.permission_code] = row.is_enabled
    return out


# ─── PATCH /permissions/roles/{role}/{code} ───────────────────────────────────
@router.patch("/roles/{role}/{code}", response_model=RolePermissionOut)
async def update_role_permission(
    role: str,
    code: str,
    body: UpdateRolePermission,
    db: DbSession,
    current_user: CurrentUser,
):
    # Solo owner puede cambiar permisos de roles
    if current_user.role != UserRole.owner:
        raise HTTPException(status_code=403, detail="Solo el dueño puede modificar permisos de roles")

    await db.execute(
        text("""
            INSERT INTO role_permissions (role, permission_code, is_enabled, updated_by, updated_at)
            VALUES (:role, :code, :enabled, :user_id, NOW())
            ON CONFLICT (role, permission_code)
            DO UPDATE SET is_enabled = :enabled, updated_by = :user_id, updated_at = NOW()
        """),
        {"role": role, "code": code, "enabled": body.is_enabled, "user_id": str(current_user.id)}
    )
    await db.commit()

    return RolePermissionOut(role=role, permission_code=code, is_enabled=body.is_enabled)


# ─── GET /permissions/users/{user_id} ────────────────────────────────────────
@router.get("/users/{user_id}", response_model=UserPermissionsOut)
async def get_user_permissions(
    user_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Permisos base del rol
    role_result = await db.execute(
        text("SELECT permission_code, is_enabled FROM role_permissions WHERE role = :role"),
        {"role": user.role.value}
    )
    role_perms = {row.permission_code: row.is_enabled for row in role_result}

    # Excepciones del usuario
    user_result = await db.execute(
        text("SELECT permission_code, is_enabled FROM user_permissions WHERE user_id = :uid"),
        {"uid": str(user_id)}
    )
    user_perms = {row.permission_code: row.is_enabled for row in user_result}

    # Combinar: permisos de rol + excepciones del usuario
    effective = {**role_perms, **user_perms}

    return UserPermissionsOut(
        user_id=str(user_id),
        user_name=user.full_name,
        role=user.role.value,
        permissions=effective,
    )


# ─── PATCH /permissions/users/{user_id}/{code} ───────────────────────────────
@router.patch("/users/{user_id}/{code}", response_model=UserPermissionOut)
async def update_user_permission(
    user_id: uuid.UUID,
    code: str,
    body: UpdateUserPermission,
    db: DbSession,
    current_user: CurrentUser,
):
    if current_user.role not in [UserRole.owner, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Sin permiso para modificar permisos de usuarios")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    await db.execute(
        text("""
            INSERT INTO user_permissions (user_id, permission_code, is_enabled, granted_by)
            VALUES (:uid, :code, :enabled, :granted_by)
            ON CONFLICT (user_id, permission_code)
            DO UPDATE SET is_enabled = :enabled, granted_by = :granted_by
        """),
        {
            "uid": str(user_id),
            "code": code,
            "enabled": body.is_enabled,
            "granted_by": str(current_user.id),
        }
    )
    await db.commit()

    return UserPermissionOut(
        user_id=str(user_id),
        permission_code=code,
        is_enabled=body.is_enabled,
    )


# ─── DELETE /permissions/users/{user_id}/{code} ───────────────────────────────
@router.delete("/permissions/users/{user_id}/{code}")
async def delete_user_permission(
    user_id: uuid.UUID,
    code: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Elimina la excepción del usuario — vuelve al permiso del rol"""
    if current_user.role not in [UserRole.owner, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Sin permiso")

    await db.execute(
        text("DELETE FROM user_permissions WHERE user_id = :uid AND permission_code = :code"),
        {"uid": str(user_id), "code": code}
    )
    await db.commit()
    return {"message": "Permiso personalizado eliminado — ahora aplica el del rol"}