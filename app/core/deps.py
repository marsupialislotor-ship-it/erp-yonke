from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Annotated
from app.core.security import decode_token
from app.db.database import get_db
from app.models.user import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de tipo incorrecto",
        )

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")

    return user


# ─── GUARDS DE ROL ────────────────────────────────────────────────────────────
def require_roles(*roles: UserRole):
    """
    Dependency factory para proteger endpoints por rol.
    Uso:
        @router.post("/users", dependencies=[Depends(require_roles(UserRole.owner, UserRole.admin))])
    """
    async def _guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rol requerido: {', '.join(r.value for r in roles)}",
            )
        return current_user
    return _guard


# ─── ALIASES COMUNES ──────────────────────────────────────────────────────────
CurrentUser = Annotated[User, Depends(get_current_user)]

OwnerOrAdmin = Annotated[
    User,
    Depends(require_roles(UserRole.owner, UserRole.admin)),
]

OwnerAdminSupervisor = Annotated[
    User,
    Depends(require_roles(UserRole.owner, UserRole.admin, UserRole.supervisor)),
]

CanSell = Annotated[
    User,
    Depends(require_roles(UserRole.owner, UserRole.admin, UserRole.seller)),
]

CanOperate = Annotated[
    User,
    Depends(require_roles(UserRole.mechanic, UserRole.helper)),
]

DbSession = Annotated[AsyncSession, Depends(get_db)]