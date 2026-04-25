import hashlib
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.core.config import settings
from app.core.security import verify_password, decode_token, create_token_pair, create_access_token
from app.core.deps import get_db, CurrentUser
from app.models.user import User, RefreshToken
from app.schemas.auth import (
    LoginRequest, LoginResponse, RefreshRequest, RefreshResponse,
    LogoutRequest, RecoverRequest, MessageResponse, UserOut, BranchOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_token(token: str) -> str:
    """SHA-256 del token — nunca guardamos el token raw."""
    return hashlib.sha256(token.encode()).hexdigest()


def _user_to_out(user: User) -> UserOut:
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


# ─── POST /auth/login ─────────────────────────────────────────────────────────
@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    # Buscar usuario por email (eager load branch)
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(User)
        .options(selectinload(User.branch))
        .where(User.email == body.email.lower().strip())
        .where(User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta está desactivada. Contacta al administrador.",
        )

    # Generar tokens
    tokens = create_token_pair(
        user_id=str(user.id),
        role=user.role.value,
        branch_id=str(user.branch_id),
    )

    # Guardar refresh token hasheado
    rt = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(tokens["refresh_token"]),
        device_info=body.device_id,
        expires_at=datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        ),
    )
    db.add(rt)

    # Actualizar last_login_at
    user.last_login_at = datetime.now(timezone.utc)

    await db.commit()

    return LoginResponse(
        **tokens,
        user=_user_to_out(user),
    )


# ─── POST /auth/refresh ───────────────────────────────────────────────────────
@router.post("/refresh", response_model=RefreshResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    token_hash = _hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()

    if not rt or not rt.is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido o expirado")

    # Cargar usuario para obtener rol y branch
    from sqlalchemy.orm import selectinload
    user_result = await db.execute(
        select(User).options(selectinload(User.branch)).where(User.id == rt.user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no disponible")

    new_access = create_access_token({
        "sub":       str(user.id),
        "role":      user.role.value,
        "branch_id": str(user.branch_id),
    })

    return RefreshResponse(
        access_token=new_access,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ─── POST /auth/logout ────────────────────────────────────────────────────────
@router.post("/logout", response_model=MessageResponse)
async def logout(
    body: LogoutRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    token_hash = _hash_token(body.refresh_token)
    now = datetime.now(timezone.utc)

    if body.all_devices:
        # Revocar todos los refresh tokens del usuario
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == current_user.id)
            .where(RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
    else:
        # Revocar solo este token
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .values(revoked_at=now)
        )

    await db.commit()
    return MessageResponse(message="Sesión cerrada correctamente")


# ─── POST /auth/recover ───────────────────────────────────────────────────────
@router.post("/recover", response_model=MessageResponse)
async def recover(body: RecoverRequest, db: AsyncSession = Depends(get_db)):
    # Siempre retorna 200 para no revelar si el email existe
    result = await db.execute(
        select(User).where(User.email == body.email.lower().strip())
    )
    user = result.scalar_one_or_none()

    if user and user.is_active:
        # TODO: enviar correo con token de recuperación
        # await email_service.send_recovery_email(user)
        pass

    return MessageResponse(message="Si el correo existe, recibirás instrucciones en breve.")