"""
Configuración de SQLAlchemy: motor, sesión y Base declarativa.

obtener_bd() se usa como dependencia de FastAPI para inyectar una sesión
por request y garantizar que siempre se cierre, incluso si la request falla.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import URL_BASE_DATOS

# pool_pre_ping evita errores por conexiones muertas cuando Cloud SQL
# recicla conexiones inactivas (relevante para el Sprint 4 en GCP).
#
# check_same_thread=False solo aplica si la URL es SQLite (útil para
# correr una demo local rápida sin instalar Postgres): SQLite por defecto
# no permite usar una conexión desde un thread distinto al que la abrió,
# y FastAPI atiende cada request en su propio thread.
argumentos_conexion = {"check_same_thread": False} if URL_BASE_DATOS.startswith("sqlite") else {}
motor = create_engine(URL_BASE_DATOS, pool_pre_ping=True, connect_args=argumentos_conexion)
SesionLocal = sessionmaker(autocommit=False, autoflush=False, bind=motor)
Base = declarative_base()


def obtener_bd():
    db = SesionLocal()
    try:
        yield db
    finally:
        db.close()
