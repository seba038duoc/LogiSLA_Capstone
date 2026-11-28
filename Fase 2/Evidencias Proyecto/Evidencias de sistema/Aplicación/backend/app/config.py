"""
Configuración de la aplicación LogiSLA.

Lee la conexión a la base de datos desde una variable de entorno para no
hardcodear credenciales. En desarrollo local, usar el docker-compose.yml
incluido (levanta un Postgres en localhost:5432) y copiar .env.example a .env.

Nota: el NOMBRE de la variable de entorno (DATABASE_URL, MAX_UPLOAD_SIZE_MB)
se deja en inglés a propósito, aunque las constantes de Python que la leen
ahora estén en español — .bat, docker-compose.yml y .env.example ya usan
esos nombres, y cambiarlos rompería el arranque en todos esos archivos.
"""

import os


def normalizar_url_base_datos(url: str) -> str:
    """
    Los proveedores de PostgreSQL en la nube (por ejemplo Neon o Heroku)
    entregan la URL como "postgres://..." o "postgresql://...", sin indicar el
    driver. SQLAlchemy 2.1 usa en ese caso psycopg (versión 3), que LogiSLA no
    instala: se fija el driver psycopg2, que es el de requirements.txt.
    """
    url = url.strip()
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg2://" + url[len(prefijo) :]
    return url


URL_BASE_DATOS = normalizar_url_base_datos(
    os.getenv("DATABASE_URL", "postgresql+psycopg2://logisla:logisla@localhost:5432/logisla")
)

# Tamaño máximo de archivo aceptado en la carga masiva (MB). El enunciado
# habla de archivos de 10.000+ filas; 25 MB cubre eso con margen para CSV/XLSX.
TAMANO_MAXIMO_CARGA_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "25"))
