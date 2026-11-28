"""
Fixtures compartidas para los tests de integración.

Por defecto cada prueba usa una base SQLite en memoria: es rápida y no
necesita instalar nada.

Si se define TEST_DATABASE_URL, las mismas pruebas corren sobre esa base
(PostgreSQL en la integración continua de GitHub Actions). Cada prueba crea
las tablas al empezar y las borra al terminar. Ejemplo:
    TEST_DATABASE_URL=postgresql+psycopg2://logisla:logisla@localhost:5432/logisla_test
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, obtener_bd
from app.models import Empresa
from app.main import app

URL_BASE_PRUEBAS = os.getenv("TEST_DATABASE_URL")


@pytest.fixture()
def sesion_bd():
    if URL_BASE_PRUEBAS:
        motor = create_engine(URL_BASE_PRUEBAS)
        Base.metadata.drop_all(bind=motor)  # por si quedó algo de una ejecución anterior
    else:
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
        if URL_BASE_PRUEBAS:
            Base.metadata.drop_all(bind=motor)
        motor.dispose()


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
