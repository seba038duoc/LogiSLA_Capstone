#!/usr/bin/env bash
# =============================================================================
# Despliegue de LogiSLA en Google Cloud Run (HU-28) con los secretos en
# Secret Manager (HU-23).
#
# Se ejecuta en Google Cloud Shell (la terminal del navegador de Google Cloud,
# que ya trae gcloud), desde la carpeta Aplicacion:
#     bash deploy/desplegar_cloud_run.sh
#
# Qué hace:
#   1. Activa las APIs necesarias (Cloud Run, Cloud Build, Artifact Registry
#      y Secret Manager).
#   2. Guarda en Secret Manager la URL de la base de datos y las claves de la
#      IA (las pide por teclado sin mostrarlas; nunca quedan en el código).
#   3. Despliega el backend en Cloud Run, que lee los secretos al arrancar.
#   4. Compila el frontend con la dirección del backend y lo despliega.
#   5. Autoriza al frontend en el CORS del backend y muestra las direcciones.
#
# Se puede volver a ejecutar para publicar una versión nueva: reutiliza los
# secretos que ya existen (pregunta si se quieren cambiar).
# =============================================================================
set -euo pipefail

PROYECTO="${PROYECTO:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
REPOSITORIO="logisla"
BACKEND="logisla-backend"
FRONTEND="logisla-frontend"

if [[ -z "$PROYECTO" ]]; then
  echo "No hay un proyecto de Google Cloud seleccionado."
  echo "Ejecute: gcloud config set project ID_DEL_PROYECTO"
  exit 1
fi
echo "Proyecto: $PROYECTO | Región: $REGION"

# --- 1. APIs ---------------------------------------------------------------
echo "> Activando las APIs (la primera vez tarda un par de minutos)..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com --quiet

NUMERO=$(gcloud projects describe "$PROYECTO" --format='value(projectNumber)')
CUENTA_SERVICIO="${NUMERO}-compute@developer.gserviceaccount.com"

# --- 2. Secretos -----------------------------------------------------------
# guardar_secreto NOMBRE "Descripción" obligatorio(si|no)
guardar_secreto() {
  local nombre="$1" descripcion="$2" obligatorio="$3" valor=""
  if gcloud secrets describe "$nombre" --quiet > /dev/null 2>&1; then
    read -r -p "  El secreto $nombre ya existe. ¿Cambiarlo? (s/N): " cambiar
    [[ "$cambiar" =~ ^[sS]$ ]] || return 0
  fi
  read -r -s -p "  $descripcion: " valor
  echo
  if [[ -z "$valor" ]]; then
    if [[ "$obligatorio" == "si" ]]; then
      echo "  Este dato es obligatorio."
      exit 1
    fi
    echo "  (se omite)"
    return 0
  fi
  if gcloud secrets describe "$nombre" --quiet > /dev/null 2>&1; then
    printf '%s' "$valor" | gcloud secrets versions add "$nombre" --data-file=- --quiet
  else
    printf '%s' "$valor" | gcloud secrets create "$nombre" --data-file=- \
      --replication-policy=automatic --quiet
  fi
  # La cuenta con la que corre Cloud Run puede leer el secreto (y nada más).
  gcloud secrets add-iam-policy-binding "$nombre" \
    --member="serviceAccount:${CUENTA_SERVICIO}" \
    --role="roles/secretmanager.secretAccessor" --quiet > /dev/null
}

echo "> Secretos en Secret Manager (lo que escriba no se muestra en pantalla)"
guardar_secreto logisla-database-url \
  "URL de PostgreSQL (Neon: postgresql://usuario:clave@host/neondb?sslmode=require)" si
guardar_secreto logisla-gemini-api-key "Clave de Gemini (Enter para omitir)" no
guardar_secreto logisla-anthropic-api-key "Clave de Claude (Enter para omitir)" no

# Solo se conectan los secretos que existen.
SECRETOS="DATABASE_URL=logisla-database-url:latest"
if gcloud secrets describe logisla-gemini-api-key --quiet > /dev/null 2>&1; then
  SECRETOS="$SECRETOS,GEMINI_API_KEY=logisla-gemini-api-key:latest"
fi
if gcloud secrets describe logisla-anthropic-api-key --quiet > /dev/null 2>&1; then
  SECRETOS="$SECRETOS,ANTHROPIC_API_KEY=logisla-anthropic-api-key:latest"
fi

# --- 3. Backend ------------------------------------------------------------
echo "> Desplegando el backend (Cloud Build compila la imagen desde backend/Dockerfile)..."
gcloud run deploy "$BACKEND" --source backend --region "$REGION" \
  --allow-unauthenticated --set-secrets "$SECRETOS" \
  --set-env-vars "CARGAR_DATOS_PRUEBA=1" \
  --memory 512Mi --min-instances 0 --max-instances 2 --quiet
URL_BACKEND=$(gcloud run services describe "$BACKEND" --region "$REGION" \
  --format='value(status.url)')
echo "  Backend: $URL_BACKEND"

# --- 4. Frontend -----------------------------------------------------------
if ! gcloud artifacts repositories describe "$REPOSITORIO" --location "$REGION" \
  --quiet > /dev/null 2>&1; then
  gcloud artifacts repositories create "$REPOSITORIO" --repository-format=docker \
    --location "$REGION" --description="Imágenes de LogiSLA" --quiet
fi
IMAGEN="${REGION}-docker.pkg.dev/${PROYECTO}/${REPOSITORIO}/frontend:latest"

echo "> Compilando el frontend con la dirección del backend..."
gcloud builds submit frontend --config deploy/cloudbuild-frontend.yaml \
  --substitutions "_API_URL=${URL_BACKEND},_IMAGEN=${IMAGEN}" --quiet

echo "> Desplegando el frontend..."
gcloud run deploy "$FRONTEND" --image "$IMAGEN" --region "$REGION" \
  --allow-unauthenticated --memory 512Mi --min-instances 0 --max-instances 2 --quiet
URL_FRONTEND=$(gcloud run services describe "$FRONTEND" --region "$REGION" \
  --format='value(status.url)')

# --- 5. CORS ---------------------------------------------------------------
echo "> Autorizando al frontend en el backend (CORS)..."
gcloud run services update "$BACKEND" --region "$REGION" \
  --update-env-vars "ALLOWED_ORIGINS=${URL_FRONTEND}" --quiet > /dev/null

echo
echo "============================================================"
echo "  LogiSLA está publicado en Google Cloud Run"
echo "  Aplicación: $URL_FRONTEND"
echo "  API:        $URL_BACKEND  (estado: $URL_BACKEND/health)"
echo "============================================================"
