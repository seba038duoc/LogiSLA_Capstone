# Imagen del backend de LogiSLA (API FastAPI + motor de auditoría).
# Se usa en docker compose (docker-compose.yml de la carpeta Aplicacion) y en
# Google Cloud Run (deploy/desplegar_cloud_run.sh).
FROM python:3.13-slim

# Sin archivos .pyc y con la salida de Python sin búfer (los registros se ven al tiro).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Primero solo las dependencias: Docker reutiliza esta capa si no cambian.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Luego el código (ver .dockerignore: no se copian .env, bases SQLite ni el .venv).
COPY . .

# Usuario sin privilegios para correr la aplicación.
RUN useradd --create-home logisla && chown -R logisla /app
USER logisla

# Cloud Run define PORT (8080); en local se usa 8000.
ENV PORT=8000
EXPOSE 8000

# Migra la base, carga datos de prueba si se pide y levanta uvicorn.
CMD ["python", "scripts/arrancar_contenedor.py"]
