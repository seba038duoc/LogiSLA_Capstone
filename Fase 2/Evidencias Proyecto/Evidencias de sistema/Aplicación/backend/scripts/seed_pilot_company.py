"""
Crea una Empresa de prueba (si no existe) e imprime su ID, para poder probar
la carga sin tener aún gestión de empresas ni login. Es idempotente: si ya
existe una empresa con ese RUT (o con ese nombre, si no se indica RUT), no la
duplica. Crea las tablas si la base de datos todavía está vacía.

Uso:
    python scripts/seed_pilot_company.py
    python scripts/seed_pilot_company.py "Mi Empresa Piloto" "76.111.222-3"
"""
import sys

from app.database import Base, SesionLocal, motor
from app import models  # noqa: F401  (registra las tablas en Base.metadata)
from app.models import Empresa

if __name__ == "__main__":
    nombre = sys.argv[1] if len(sys.argv) > 1 else "Retail Piloto SpA"
    rut = sys.argv[2] if len(sys.argv) > 2 else None

    Base.metadata.create_all(bind=motor)
    db = SesionLocal()
    filtro = Empresa.rut == rut if rut else Empresa.nombre == nombre
    empresa = db.query(Empresa).filter(filtro).first()
    if not empresa:
        empresa = Empresa(nombre=nombre, rut=rut)
        db.add(empresa)
        db.commit()
        db.refresh(empresa)
    print(f"empresa_id={empresa.id}")
    db.close()
