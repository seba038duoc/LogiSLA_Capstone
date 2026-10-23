"""
GET /api/v1/empresas
    Lista las empresas registradas, para que el frontend ofrezca un
    selector en vez de pedir que el usuario pegue un UUID a mano.

    Mientras no exista login (queda para otro sprint) esto devuelve todas
    las empresas. Cuando haya autenticación, este endpoint debe devolver
    solo la(s) empresa(s) del usuario autenticado.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import obtener_bd
from app.models import Empresa
from app.schemas import EmpresaSalida

router = APIRouter(prefix="/api/v1/empresas", tags=["empresas"])


@router.get("", response_model=list[EmpresaSalida])
def listar_empresas(db: Session = Depends(obtener_bd)):
    return db.query(Empresa).order_by(Empresa.nombre).all()
