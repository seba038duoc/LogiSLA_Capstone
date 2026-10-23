# LogiSLA — Backend (Sprint 1: Ingesta y Base Backend)

Motor de ingesta de LogiSLA: recibe archivos CSV/Excel de envíos, mapea
automáticamente las columnas a un modelo de datos estándar, y guarda las
guías en base de datos a la espera del motor de auditoría (Sprint 2).

Este entregable cubre completo el Sprint 1 reorganizado: **modelado de
datos + API de ingesta + mapeo manual de respaldo + pruebas unitarias e
integración** (el testing que antes vivía en un "Sprint de Calidad"
separado ahora se escribe junto con cada módulo). Todo el flujo fue
probado de punta a punta contra un Postgres real y contra el frontend
real corriendo en el navegador — no solo contra los tests (ver más abajo).

## Estructura

```
app/
  main.py             # arranque de FastAPI + CORS
  config.py           # variables de entorno
  database.py         # engine SQLAlchemy, sesión
  models.py           # companies, carriers, sla_rules, audit_batches, shipments
  column_mapping.py   # mapeo automático de columnas (la lógica "inteligente" del sprint)
  schemas.py          # respuestas de la API (Pydantic)
  routers/
    audit_batches.py  # POST /upload, POST /upload/confirm, GET /{batch_id}
tests/
  test_column_mapping.py   # unitarios: distintas variantes de headers reales
  test_upload_endpoint.py  # integración: carga completa + mapeo manual vía API
sample_data/
  envios_piloto.csv                    # 60 guías, headers estándar (auto-mapeo OK)
  envios_headers_no_reconocidos.csv    # headers "raros" (dispara MAPPING_FAILED)
scripts/
  seed_pilot_company.py  # crea una Company de prueba y devuelve su ID
```

## Cómo correrlo

1. Instalar dependencias:
   ```
   pip install -r requirements.txt
   ```

2. Levantar Postgres local (o usar tu propia instancia y ajustar `.env`):
   ```
   cp .env.example .env
   docker compose up -d
   ```
   Si no tienes Docker a mano, también sirve un Postgres instalado
   directo en el sistema (`apt install postgresql`) — así es como se
   probó este entregable en el sandbox donde se generó (ver más abajo).

3. Levantar la API:
   ```
   uvicorn app.main:app --reload
   ```
   Docs interactivas en `http://localhost:8000/docs`.

4. Correr las pruebas (no necesitan Postgres, usan SQLite en memoria):
   ```
   pytest -v
   ```
   Deben pasar 14/14.

## Cómo probar la carga de un archivo

Primero hay que crear una `Company` (no hay endpoint todavía porque el
login/gestión de empresas queda para otro sprint):

```
python scripts/seed_pilot_company.py "Retail Piloto SpA" "76.987.654-3"
# imprime: company_id=<uuid>
```

Carga con mapeo automático:
```
curl -X POST "http://localhost:8000/api/v1/audit-batches/upload?company_id=<ID>" \
  -F "file=@sample_data/envios_piloto.csv"
```

Si el mapeo automático falla (`status: MAPPING_FAILED`), confirmarlo a mano:
```
curl -X POST "http://localhost:8000/api/v1/audit-batches/upload/confirm?company_id=<ID>" \
  -F "file=@sample_data/envios_headers_no_reconocidos.csv" \
  -F 'column_mapping={"guide_number":"Codigo Interno","carrier_name":"Empresa de Reparto","dispatch_date":"Dia de Salida"}'
```

## Mapeo automático de columnas

`app/column_mapping.py` reconoce variantes comunes de headers en español
e inglés (ej. "N° Guía", "Numero de Guia", "tracking_number" → todos
mapean a `guide_number`) y descarta conectores ("de", "del", "la") al
normalizar. Si no logra mapear un campo obligatorio (`guide_number`,
`carrier_name`, `dispatch_date`), `POST /upload` devuelve
`status: "MAPPING_FAILED"` **sin tocar la base de datos**, junto con
`available_headers` (los headers reales del archivo) para que el
frontend arme un formulario de mapeo manual.

Campos obligatorios: `guide_number`, `carrier_name`, `dispatch_date`.
Campos opcionales: `delivery_date`, `destination`, `declared_value`.

### Confirmar un mapeo manual — `POST /upload/confirm`

Recibe el mismo archivo otra vez más un campo de formulario
`column_mapping` (JSON `{"campo_interno": "header_del_archivo"}`).
Valida que:
- estén los 3 campos obligatorios,
- cada header mapeado exista realmente en el archivo,

y si algo falla devuelve 400 con el detalle, sin crear el batch. Si todo
está bien, crea el `AuditBatch` igual que `/upload`, marcando
`manual_mapping = true` para trazabilidad (si muchos batches terminan
así, es señal de ampliar el diccionario de sinónimos).

## CORS (para el frontend)

`app/main.py` agrega `CORSMiddleware` permitiendo `http://localhost:3000`
por defecto (donde corre el frontend Next.js en dev). Para producción,
seteá la variable de entorno `ALLOWED_ORIGINS` con el dominio real,
separado por comas:
```
ALLOWED_ORIGINS=https://logisla.miapp.com,https://logisla-staging.miapp.com
```

## Probado contra Postgres real (no solo SQLite de test)

Además de los 14 tests (que usan SQLite en memoria para no depender de
infraestructura), este flujo se probó de punta a punta contra un
Postgres real corriendo localmente:

1. Se levantó Postgres 16 y se creó el rol/base `logisla` (igual a lo
   que define `docker-compose.yml`).
2. Se arrancó la API real (`uvicorn`), que creó las 5 tablas solo al
   iniciar.
3. Se creó una `Company` piloto (`scripts/seed_pilot_company.py`).
4. Se subió `sample_data/envios_piloto.csv` (60 guías con transportistas
   chilenos reales — Chilexpress, Starken, Blue Express, Correos de
   Chile — algunas sin `delivery_date` simulando guías en tránsito) vía
   `POST /upload` → **200 OK, batch creado con 60 filas**.
5. Se verificó directo en Postgres (`psql`) que las 60 filas quedaron
   con los tipos correctos (fechas, montos) y que `is_sla_breached`
   quedó `NULL` en todas (correcto: eso lo llena el Sprint 2).
6. Se subió `sample_data/envios_headers_no_reconocidos.csv` (headers que
   el auto-mapeo no reconoce a propósito) → `MAPPING_FAILED` sin tocar
   la BD, y luego se confirmó manualmente vía `/upload/confirm` →
   **200 OK**, y quedó en Postgres con `manual_mapping = true`.
7. Se repitieron los pasos 4 y 6 **desde el navegador**, contra el
   frontend Next.js real (`../logisla-frontend`) sirviendo en
   `localhost:3000` y este backend en `localhost:8000` — incluyendo el
   formulario de mapeo manual completo (seleccionar columnas desde los
   `<select>`, confirmar, ver el resumen del batch creado). Sin errores
   de consola ni de CORS.

Esto confirma que el flujo funciona en condiciones reales, no solo con
los mocks/SQLite de los tests automatizados.

## Qué queda fuera de este sprint (a propósito)

- Cálculo de SLA / multas (`is_sla_breached`, `delay_business_hours`,
  `penalty_amount` quedan `NULL`) → Sprint 2, motor de auditoría con
  Pandas + Workalendar.
- Autenticación / gestión de empresas y usuarios (por eso `company_id`
  se crea a mano con el script de seed, no hay login todavía).
- Migraciones con Alembic (por ahora `create_all` en el startup) → Sprint 4.

## Checklist del Sprint 1

- [x] Modelo de datos (`companies`, `carriers`, `sla_rules`, `audit_batches`, `shipments`)
- [x] Endpoint de carga CSV/Excel con mapeo automático de columnas
- [x] Endpoint de confirmación manual de mapeo (`/upload/confirm`)
- [x] Pruebas unitarias del mapeo (6 casos, headers reales variados)
- [x] Pruebas de integración de ambos endpoints (14 casos en total)
- [x] Frontend Next.js conectado (ver `../logisla-frontend`) — carga +
      formulario de mapeo manual cuando el auto-mapeo falla
- [x] Probado contra Postgres real (no solo SQLite de test) — ver sección arriba
- [ ] Reemplazar el `company_id` a mano por lo que salga del login/gestión de empresas (otro sprint)
