"""Punto de entrada de la API LogiSLA."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, motor
from app.routers import audit_batches, empresas

registrador = logging.getLogger(__name__)


@asynccontextmanager
async def ciclo_vida(app: FastAPI):
    """
    Crea las tablas si no existen, al levantar el server real. En tests
    esto NO corre contra Postgres: los tests arman su propia BD SQLite en
    conftest.py, así que un error de conexión acá solo se registra como
    warning y no tumba la app. En producción (Sprint 4) esto se reemplaza
    por migraciones Alembic para tener control de versiones del esquema.
    """
    try:
        Base.metadata.create_all(bind=motor)
    except Exception as exc:  # pragma: no cover
        registrador.warning("No se pudo conectar a la base de datos al iniciar: %s", exc)
    yield


app = FastAPI(
    title="LogiSLA API",
    description="Auditoría inteligente de SLA de transporte",
    version="0.1.0",
    lifespan=ciclo_vida,
)

# El frontend (Next.js) corre en otro origen (localhost:3000 en dev, otro
# dominio en Cloud Run en el Sprint 5), así que el navegador
# necesita estos headers CORS o bloquea las llamadas fetch(). En dev
# dejamos localhost:3000/3001 fijos; ALLOWED_ORIGINS permite agregar el
# dominio real de producción sin tocar código.
origenes_por_defecto = (
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:3001,http://127.0.0.1:3001"
)
origenes_permitidos = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", origenes_por_defecto).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audit_batches.router)
app.include_router(empresas.router)


@app.get("/health")
def verificar_salud():
    return {"status": "ok"}
