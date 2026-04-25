from fastapi import APIRouter
from app.api.v1.endpoints import auth, parts, users, vehicles, orders, sales

api_router = APIRouter(prefix="/v1")
api_router.include_router(auth.router)
api_router.include_router(parts.router)
api_router.include_router(users.router)
api_router.include_router(vehicles.router)
api_router.include_router(orders.router)
api_router.include_router(sales.router)