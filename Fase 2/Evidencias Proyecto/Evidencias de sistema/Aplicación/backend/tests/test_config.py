"""Pruebas de la lectura de la URL de la base de datos (app/config.py)."""

from app.config import normalizar_url_base_datos


def test_url_de_proveedores_en_la_nube_usa_psycopg2():
    for esquema in ("postgres://", "postgresql://"):
        url = f"{esquema}usuario:clave@ep-ejemplo.neon.tech/neondb?sslmode=require"
        assert normalizar_url_base_datos(url) == (
            "postgresql+psycopg2://usuario:clave@ep-ejemplo.neon.tech/neondb?sslmode=require"
        )


def test_urls_con_driver_o_sqlite_no_cambian():
    for url in (
        "postgresql+psycopg2://logisla:logisla@localhost:5432/logisla",
        "sqlite:///./logisla.db",
    ):
        assert normalizar_url_base_datos(f"  {url}\n") == url
