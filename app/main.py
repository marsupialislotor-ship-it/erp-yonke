from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.api.v1.router import api_router
from functools import lru_cache
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── LIFESPAN ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 Iniciando {settings.app_name} v{settings.app_version} [{settings.app_env}]")

    # init_db solo en desarrollo local — en Supabase usar migraciones manuales
    if settings.is_development and "supabase" not in settings.database_url:
        from app.db.database import init_db
        await init_db()
        logger.info("✅ Tablas verificadas/creadas")
    else:
        logger.info("✅ Usando base de datos existente")

    yield

    logger.info("👋 Cerrando servidor...")


# ─── APP ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API del sistema ERP para deshuesadero (yonke)",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── MIDDLEWARE: request timing ───────────────────────────────────────────────
@app.middleware("http")
async def add_process_time(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    ms = round((time.time() - start) * 1000, 1)
    response.headers["X-Process-Time"] = f"{ms}ms"
    if ms > 500:
        logger.warning(f"🐢 Respuesta lenta: {request.method} {request.url.path} — {ms}ms")
    return response

# ─── EXCEPTION HANDLERS ───────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Error no manejado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor" if settings.is_production else str(exc)},
    )

# ─── ROUTERS ──────────────────────────────────────────────────────────────────
app.include_router(api_router)

# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["sistema"])
async def health():
    return {
        "status":  "ok",
        "version": settings.app_version,
        "env":     settings.app_env,
    }

@app.get("/", tags=["sistema"])
async def root():
    return {
        "app":     settings.app_name,
        "version": settings.app_version,
        "docs":    "/docs" if not settings.is_production else "disabled",
    }