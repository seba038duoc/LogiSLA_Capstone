"""
GET /api/v1/ia/estado
    Dice qué proveedores de IA generativa están configurados (por defecto,
    Gemini como principal y Claude como respaldo) y qué modelo usa cada uno. Sirve para
    revisar la instalación antes de una demo. Nunca devuelve las claves,
    solo si existen.
"""

from fastapi import APIRouter

from app import ia_proveedores
from app.schemas import EstadoIASalida, EstadoProveedorIA

router = APIRouter(prefix="/api/v1/ia", tags=["ia"])


@router.get("/estado", response_model=EstadoIASalida)
def estado_ia():
    """GET /api/v1/ia/estado: proveedores configurados y sus modelos (nunca las claves)."""
    config = ia_proveedores.obtener_configuracion()
    proveedores = [
        EstadoProveedorIA(
            nombre=p.nombre,
            papel="principal" if i == 0 else "respaldo",
            configurado=p.configurada,
            modelo=p.modelo,
        )
        for i, p in enumerate(config.en_orden)
    ]
    primero = next((p for p in config.en_orden if p.configurada), None)
    return EstadoIASalida(
        configurada=config.configurada,
        proveedor=primero.nombre if primero else None,
        modelo=primero.modelo if primero else None,
        proveedores=proveedores,
    )
