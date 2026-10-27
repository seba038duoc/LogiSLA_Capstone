"""
Siembra transportistas chilenos conocidos con una ReglaSLA activa cada
uno, para que el motor de auditoría (Sprint 2) tenga contra qué comparar
al calcular incumplimientos. Sigue el mismo patrón que
seed_pilot_company.py: se corre a mano una vez por base de datos nueva
(es idempotente — si el transportista o su regla ya existen, no los
duplica).

Uso:
    python scripts/seed_carriers_and_rules.py
"""
from app.database import Base, SesionLocal, motor
from app.models import Transportista, ReglaSLA

# (nombre, horas_habiles_maximas_sla, multa_por_incumplimiento_clp)
TRANSPORTISTAS_POR_DEFECTO = [
    ("Chilexpress", 48, 15000),
    ("Starken", 60, 12000),
    ("Correos de Chile", 72, 10000),
    ("Blue Express", 48, 15000),
]

if __name__ == "__main__":
    # Crea las tablas si la base de datos todavía está vacía (primera ejecución).
    Base.metadata.create_all(bind=motor)
    db = SesionLocal()
    sembrados = []

    for nombre, horas_maximas, multa in TRANSPORTISTAS_POR_DEFECTO:
        transportista = db.query(Transportista).filter(Transportista.nombre == nombre).first()
        if not transportista:
            transportista = Transportista(nombre=nombre)
            db.add(transportista)
            db.flush()

        regla_existente = (
            db.query(ReglaSLA)
            .filter(ReglaSLA.transportista_id == transportista.id, ReglaSLA.activa.is_(True))
            .first()
        )
        if not regla_existente:
            db.add(ReglaSLA(
                transportista_id=transportista.id,
                tipo_servicio=None,
                horas_habiles_maximas=horas_maximas,
                multa_por_incumplimiento=multa,
                activa=True,
            ))
        sembrados.append(f"{nombre} ({horas_maximas}h, ${multa})")

    db.commit()
    db.close()
    print("Transportistas y reglas SLA sembrados:")
    for linea in sembrados:
        print(f"  - {linea}")
