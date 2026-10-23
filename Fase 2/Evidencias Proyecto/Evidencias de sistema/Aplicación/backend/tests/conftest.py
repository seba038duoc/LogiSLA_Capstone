"""
Fixtures compartidas para los tests de integración.

Usamos SQLite en memoria en vez de levantar un Postgres real: es lo
suficientemente compatible para probar la lógica de la API sin depender
de infraestructura externa en CI.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, obtener_bd
from app.models import Empresa
from app.main import app


@pytest.fixture()
def sesion_bd():
    motor = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SesionDePrueba = sessionmaker(autocommit=False, autoflush=False, bind=motor)
    Base.metadata.create_all(bind=motor)

    sesion = SesionDePrueba()
    try:
        yield sesion
    finally:
        sesion.close()


@pytest.fixture()
def cliente(sesion_bd):
    def sobreescribir_obtener_bd():
        try:
            yield sesion_bd
        finally:
            pass

    app.dependency_overrides[obtener_bd] = sobreescribir_obtener_bd
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def empresa_ejemplo(sesion_bd):
    empresa = Empresa(nombre="Retail Demo SpA", rut="76.123.456-7")
    sesion_bd.add(empresa)
    sesion_bd.commit()
    sesion_bd.refresh(empresa)
    return empresa
