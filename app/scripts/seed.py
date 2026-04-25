import asyncio
from sqlalchemy import select
from app.db.database import AsyncSessionLocal, init_db
from app.models.user import User, Branch, UserRole
from app.models.inventory import PartCondition
from app.core.security import hash_password


INITIAL_BRANCHES = [
    {"name": "Matriz",         "code": "MTZ", "is_headquarters": True},
    {"name": "Sucursal Norte", "code": "SN",  "is_headquarters": False},
    {"name": "Sucursal Sur",   "code": "SS",  "is_headquarters": False},
]

INITIAL_CONDITIONS = [
    {"name": "Sana",         "description": "Pieza en perfectas condiciones", "sort_order": 1},
    {"name": "Lámina",       "description": "Daño estético, funciona bien",   "sort_order": 2},
    {"name": "Con detalles", "description": "Detalles menores de funciona.",  "sort_order": 3},
    {"name": "Bote",         "description": "Solo para reciclar",             "sort_order": 4},
]

INITIAL_USER = {
    "email":     "dueno@yonke.com",
    "password":  "Yonke2025!",
    "full_name": "Carlos García",
    "role":      UserRole.owner,
}


async def seed():
    await init_db()

    async with AsyncSessionLocal() as db:
        # ── Sucursales ────────────────────────────────────────────────────
        branches = {}
        for b in INITIAL_BRANCHES:
            result = await db.execute(
                select(Branch).where(Branch.code == b["code"])
            )
            existing = result.scalar_one_or_none()
            if not existing:
                branch = Branch(**b)
                db.add(branch)
                await db.flush()
                branches[b["code"]] = branch
                print(f"✅ Sucursal: {b['name']}")
            else:
                branches[b["code"]] = existing
                print(f"⏭  Sucursal ya existe: {b['name']}")

        # ── Condiciones ───────────────────────────────────────────────────
        for c in INITIAL_CONDITIONS:
            result = await db.execute(
                select(PartCondition).where(PartCondition.name == c["name"])
            )
            existing = result.scalar_one_or_none()
            if not existing:
                db.add(PartCondition(**c))
                print(f"✅ Condición: {c['name']}")
            else:
                print(f"⏭  Condición ya existe: {c['name']}")

        # ── Usuario inicial ───────────────────────────────────────────────
        result = await db.execute(
            select(User).where(User.email == INITIAL_USER["email"])
        )
        existing_user = result.scalar_one_or_none()

        if not existing_user:
            matriz = branches.get("MTZ")
            if matriz:
                user = User(
                    email=INITIAL_USER["email"],
                    password_hash=hash_password(INITIAL_USER["password"]),
                    full_name=INITIAL_USER["full_name"],
                    role=INITIAL_USER["role"],
                    branch_id=matriz.id,
                )
                db.add(user)
                print(f"✅ Usuario: {INITIAL_USER['email']}")
        else:
            print(f"⏭  Usuario ya existe: {INITIAL_USER['email']}")

        await db.commit()

    print("\n🎉 Seed completado")
    print(f"   Login: {INITIAL_USER['email']}")
    print(f"   Pass:  {INITIAL_USER['password']}")


if __name__ == "__main__":
    asyncio.run(seed())