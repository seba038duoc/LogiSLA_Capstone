"""
Crea una Empresa de prueba y devuelve su ID, para poder probar la carga
sin tener aún un endpoint/login de gestión de empresas (queda para otro
sprint). Uso:

    python scripts/seed_pilot_company.py
    # o con nombre propio:
    python scripts/seed_pilot_company.py "Mi Empresa Piloto" "76.111.222-3"
"""
import sys

from app.database import SesionLocal
from app.models import Empresa

if __name__ == "__main__":
    nombre = sys.argv[1] if len(sys.argv) > 1 else "Retail Piloto SpA"
    rut = sys.argv[2] if len(sys.argv) > 2 else None

    db = SesionLocal()
    empresa = Empresa(nombre=nombre, rut=rut)
    db.add(empresa)
    db.commit()
    db.refresh(empresa)
    print(f"company_id={empresa.id}")
    db.close()
