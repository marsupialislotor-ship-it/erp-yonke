"""
Seed de datos de prueba para desarrollo.
Crea vehículos, piezas, clientes y órdenes de ejemplo.

    cd backend
    python -m app.scripts.seed_data
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.db.database import AsyncSessionLocal, init_db
from app.models.user import User, Branch, UserRole
from app.models.inventory import (
    Vehicle, VehicleStatus, PurchaseOrigin,
    Part, PartStatus, PartCondition, PartMedia,
)
from app.models.orders import DisassemblyOrder, OrderStatus, OrderPriority
from app.models.sales import Customer, Sale, SaleStatus, SaleChannel, PaymentMethod
from app.core.security import hash_password


async def seed_data():
    async with AsyncSessionLocal() as db:
        # ── Obtener sucursales ────────────────────────────────────────────────
        branches = (await db.execute(select(Branch))).scalars().all()
        if not branches:
            print("❌ No hay sucursales. Corre primero: python -m app.scripts.seed")
            return

        matriz   = next((b for b in branches if b.code == "MTZ"), branches[0])
        norte    = next((b for b in branches if b.code == "SN"),  branches[0])

        # ── Obtener condiciones ───────────────────────────────────────────────
        conditions = (await db.execute(select(PartCondition))).scalars().all()
        if not conditions:
            print("❌ No hay condiciones. Corre primero: python -m app.scripts.seed")
            return
        sana     = next((c for c in conditions if c.name == "Sana"),    conditions[0])
        lamina   = next((c for c in conditions if c.name == "Lámina"),  conditions[0])
        bote     = next((c for c in conditions if c.name == "Bote"),    conditions[-1])

        # ── Obtener usuario dueño ─────────────────────────────────────────────
        owner = (await db.execute(
            select(User).where(User.email == "dueno@yonke.com")
        )).scalar_one_or_none()
        if not owner:
            print("❌ No hay usuario dueño. Corre primero: python -m app.scripts.seed")
            return

        # ── Crear usuarios de prueba ───────────────────────────────────────────
        users_data = [
            {"email": "vendedor@yonke.com",   "full_name": "Ana Vendedora",   "role": UserRole.seller,     "branch": matriz},
            {"email": "mecanico@yonke.com",   "full_name": "Pedro Mecánico",  "role": UserRole.mechanic,   "branch": norte},
            {"email": "ayudante@yonke.com",   "full_name": "Luis Ayudante",   "role": UserRole.helper,     "branch": norte},
            {"email": "supervisor@yonke.com", "full_name": "Roberto Supervisor","role": UserRole.supervisor,"branch": matriz},
            {"email": "admin@yonke.com",      "full_name": "María Admin",      "role": UserRole.admin,     "branch": matriz},
        ]
        created_users = {}
        for u in users_data:
            existing = (await db.execute(select(User).where(User.email == u["email"]))).scalar_one_or_none()
            if not existing:
                user = User(
                    email=u["email"], full_name=u["full_name"], role=u["role"],
                    branch_id=u["branch"].id, password_hash=hash_password("Yonke2025!"),
                )
                db.add(user)
                await db.flush()
                created_users[u["email"]] = user
                print(f"✅ Usuario: {u['email']}")
            else:
                created_users[u["email"]] = existing
                print(f"⏭  Usuario ya existe: {u['email']}")

        vendedor = created_users.get("vendedor@yonke.com")
        mecanico = created_users.get("mecanico@yonke.com")

        # ── Vehículos ─────────────────────────────────────────────────────────
        now = datetime.now(timezone.utc)
        vehicles_data = [
            {"key": "VEH-2025-0038", "brand": "Honda",      "model": "Civic",    "year": 2016, "branch": norte,  "cost": 45000},
            {"key": "VEH-2025-0040", "brand": "Toyota",     "model": "Corolla",  "year": 2019, "branch": matriz, "cost": 52000},
            {"key": "VEH-2025-0042", "brand": "Nissan",     "model": "Sentra",   "year": 2018, "branch": norte,  "cost": 38000},
            {"key": "VEH-2025-0035", "brand": "Volkswagen", "model": "Jetta",    "year": 2020, "branch": matriz, "cost": 61000},
            {"key": "VEH-2025-0030", "brand": "Chevrolet",  "model": "Aveo",     "year": 2017, "branch": norte,  "cost": 28000},
            {"key": "VEH-2025-0033", "brand": "Ford",       "model": "Focus",    "year": 2018, "branch": matriz, "cost": 35000},
        ]
        created_vehicles = {}
        for vd in vehicles_data:
            existing = (await db.execute(select(Vehicle).where(Vehicle.vehicle_key == vd["key"]))).scalar_one_or_none()
            if not existing:
                v = Vehicle(
                    vehicle_key=vd["key"], branch_id=vd["branch"].id,
                    brand=vd["brand"], model=vd["model"], year=vd["year"],
                    purchase_origin=PurchaseOrigin.auction,
                    purchase_cost=vd["cost"], purchase_date=now - timedelta(days=30),
                    status=VehicleStatus.dismantling,
                    registered_by_id=owner.id,
                )
                db.add(v)
                await db.flush()
                created_vehicles[vd["key"]] = v
                print(f"✅ Vehículo: {vd['key']} — {vd['brand']} {vd['model']} {vd['year']}")
            else:
                created_vehicles[vd["key"]] = existing
                print(f"⏭  Vehículo ya existe: {vd['key']}")

        # ── Piezas ────────────────────────────────────────────────────────────
        parts_data = [
            {"key": "VEH-2025-0042-P001", "veh": "VEH-2025-0042", "name": "Cofre delantero",          "price": 2500,  "cond": sana,   "status": PartStatus.in_stock,   "branch": norte},
            {"key": "VEH-2025-0038-P001", "veh": "VEH-2025-0038", "name": "Motor 1.8L",               "price": 14000, "cond": sana,   "status": PartStatus.in_vehicle, "branch": norte},
            {"key": "VEH-2025-0040-P001", "veh": "VEH-2025-0040", "name": "Puerta delantera izq.",    "price": 1800,  "cond": lamina, "status": PartStatus.in_stock,   "branch": matriz},
            {"key": "VEH-2025-0035-P001", "veh": "VEH-2025-0035", "name": "Faro delantero derecho",   "price": 3200,  "cond": sana,   "status": PartStatus.in_stock,   "branch": matriz},
            {"key": "VEH-2025-0030-P001", "veh": "VEH-2025-0030", "name": "Transmisión automática",   "price": 8500,  "cond": sana,   "status": PartStatus.in_stock,   "branch": norte},
            {"key": "VEH-2025-0042-P002", "veh": "VEH-2025-0042", "name": "Parabrisas delantero",     "price": 1200,  "cond": sana,   "status": PartStatus.in_stock,   "branch": norte},
            {"key": "VEH-2025-0038-P002", "veh": "VEH-2025-0038", "name": "Caja de velocidades",      "price": 6500,  "cond": sana,   "status": PartStatus.reserved,   "branch": norte},
            {"key": "VEH-2025-0033-P001", "veh": "VEH-2025-0033", "name": "Tablero completo",         "price": 4500,  "cond": sana,   "status": PartStatus.in_vehicle, "branch": matriz},
            {"key": "VEH-2025-0040-P002", "veh": "VEH-2025-0040", "name": "Cajuela completa",         "price": 2800,  "cond": bote,   "status": PartStatus.in_stock,   "branch": matriz},
            {"key": "VEH-2025-0035-P002", "veh": "VEH-2025-0035", "name": "Defensa delantera",        "price": 1500,  "cond": lamina, "status": PartStatus.in_stock,   "branch": matriz},
            {"key": "VEH-2025-0042-P003", "veh": "VEH-2025-0042", "name": "Espejo lateral derecho",   "price": 850,   "cond": sana,   "status": PartStatus.in_stock,   "branch": norte},
            {"key": "VEH-2025-0030-P002", "veh": "VEH-2025-0030", "name": "Alternador",               "price": 950,   "cond": sana,   "status": PartStatus.in_stock,   "branch": norte},
        ]
        created_parts = {}
        for pd in parts_data:
            existing = (await db.execute(select(Part).where(Part.part_key == pd["key"]))).scalar_one_or_none()
            if not existing:
                veh = created_vehicles.get(pd["veh"])
                if not veh:
                    continue
                brand, model = veh.brand, veh.model
                p = Part(
                    part_key=pd["key"], vehicle_id=veh.id,
                    branch_id=pd["branch"].id, name=pd["name"],
                    brand=brand, model=model,
                    year_from=veh.year - 1, year_to=veh.year + 2,
                    condition_id=pd["cond"].id,
                    status=pd["status"], sale_price=pd["price"],
                    registered_by_id=owner.id,
                )
                db.add(p)
                await db.flush()
                created_parts[pd["key"]] = p
                print(f"✅ Pieza: {pd['key']} — {pd['name']}")
            else:
                created_parts[pd["key"]] = existing
                print(f"⏭  Pieza ya existe: {pd['key']}")

        # ── Clientes ──────────────────────────────────────────────────────────
        customers_data = [
            {"name": "Taller García",          "phone": "442-123-4567", "type": "workshop", "frequent": True},
            {"name": "Roberto Hernández",       "phone": "442-987-6543", "type": "individual"},
            {"name": "Auto Partes del Norte",   "phone": "442-555-0101", "type": "dealer",   "frequent": True},
        ]
        created_customers = []
        for cd in customers_data:
            existing = (await db.execute(select(Customer).where(Customer.name == cd["name"]))).scalar_one_or_none()
            if not existing:
                c = Customer(
                    name=cd["name"], phone=cd["phone"],
                    customer_type=cd.get("type", "individual"),
                    is_frequent=cd.get("frequent", False),
                )
                db.add(c)
                await db.flush()
                created_customers.append(c)
                print(f"✅ Cliente: {cd['name']}")
            else:
                created_customers.append(existing)
                print(f"⏭  Cliente ya existe: {cd['name']}")

        # ── Órdenes de desmonte ───────────────────────────────────────────────
        p1 = created_parts.get("VEH-2025-0038-P001")  # Motor Honda — in_vehicle
        p2 = created_parts.get("VEH-2025-0033-P001")  # Tablero — in_vehicle
        orders_data = []
        if p1:
            orders_data.append({
                "key": "ORD-20250418-0016", "part": p1,
                "priority": OrderPriority.urgent,
                "instructions": "Con cuidado, cliente paga hoy.",
                "status": OrderStatus.pending,
            })
        if p2:
            orders_data.append({
                "key": "ORD-20250418-P015", "part": p2,
                "priority": OrderPriority.normal,
                "instructions": "Tomar fotos antes y después.",
                "status": OrderStatus.pending,
            })

        seller_user = vendedor or owner
        for od in orders_data:
            existing = (await db.execute(
                select(DisassemblyOrder).where(DisassemblyOrder.order_key == od["key"])
            )).scalar_one_or_none()
            if not existing:
                o = DisassemblyOrder(
                    order_key=od["key"], part_id=od["part"].id,
                    vehicle_id=od["part"].vehicle_id,
                    branch_id=od["part"].branch_id,
                    priority=od["priority"], instructions=od["instructions"],
                    status=od["status"], created_by_id=seller_user.id,
                )
                db.add(o)
                print(f"✅ Orden: {od['key']}")
            else:
                print(f"⏭  Orden ya existe: {od['key']}")

        # ── Venta de ejemplo ──────────────────────────────────────────────────
        existing_sale = (await db.execute(select(Sale).where(Sale.sale_key == "VTA-202504-0001"))).scalar_one_or_none()
        if not existing_sale and created_customers and created_parts:
            p_cofre = created_parts.get("VEH-2025-0042-P001")
            if p_cofre:
                sale = Sale(
                    sale_key="VTA-202504-0001",
                    branch_id=norte.id,
                    customer_id=created_customers[0].id,
                    seller_id=seller_user.id,
                    status=SaleStatus.delivered,
                    channel=SaleChannel.counter,
                    payment_method=PaymentMethod.cash,
                    total_amount=2500,
                    items=[{
                        "part_id":    str(p_cofre.id),
                        "part_key":   p_cofre.part_key,
                        "part_name":  p_cofre.name,
                        "brand":      p_cofre.brand,
                        "model":      p_cofre.model,
                        "unit_price": 2500,
                    }],
                )
                db.add(sale)
                p_cofre.status = PartStatus.sold
                print("✅ Venta de ejemplo: VTA-202504-0001")

        await db.commit()

    print("\n🎉 Datos de prueba creados exitosamente")
    print("   Usuarios:   vendedor / mecanico / ayudante / supervisor / admin")
    print("   Password:   Yonke2025!")
    print("   Vehículos:  6")
    print("   Piezas:     12")
    print("   Clientes:   3")


if __name__ == "__main__":
    asyncio.run(seed_data())