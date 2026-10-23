# LogiSLA — carga, auditoría y resultados (backend + frontend)

Esta carpeta ya está lista para correr en tu computador. Para verla:

1. Doble clic en **`iniciar.bat`**.
2. La primera vez va a tardar unos minutos (instala las dependencias de Python y Node).
3. Al final se abre tu navegador solo en `http://localhost:3000`, con la empresa de prueba ya elegida (no hay que pegar ningún ID).
4. Ve a **Cargar envíos**, sube un CSV/Excel, revisa las columnas detectadas y presiona **Auditar lote**.
5. Se abre el detalle del lote: multas por reclamar, cumplimiento por transportista y la tabla de guías (con filtros, búsqueda y descarga de incumplimientos en CSV). En **Lotes** quedan todos los lotes cargados.

Quedan dos ventanas de terminal abiertas (Backend y Frontend) mientras la uses — no las cierres hasta terminar.

## Requisitos

- Python **estable** entre 3.10 y 3.14 (recomendado 3.13). Las versiones alfa o beta, como 3.15.0a3, no sirven: las dependencias no se instalan.
- Node.js 18 o superior (`node --version`).

Si no los tenés, instalalos desde python.org y nodejs.org (elegí la opción "Add to PATH" durante la instalación de Python).

## Nota sobre la base de datos

Esta versión usa SQLite (un archivo `backend/logisla.db`) en vez de PostgreSQL, para que no tengas que instalar nada más — es la misma app, mismo código, solo cambia dónde vive el dato. Cuando el equipo despliegue de verdad (Sprint 4, GCP), ahí sí se usa PostgreSQL como está planeado en el proyecto.

Si en algún momento querés probarlo con PostgreSQL real, `backend/README.md` tiene las instrucciones (`docker-compose.yml` incluido).

## Archivos de prueba

`backend/sample_data/envios_piloto.csv` — 60 guías con headers normales (el mapeo automático los reconoce solo).
`backend/sample_data/envios_headers_no_reconocidos.csv` — headers raros, para probar el rechazo de la carga con el mensaje de columnas no reconocidas.

## Si algo falla

`iniciar.bat` revisa que Python y Node estén instalados y avisa con un
mensaje claro si falta alguno, en vez de fallar en silencio. Si aun así la
instalación del backend o del frontend falla, **queda un archivo
`install.log`** dentro de `backend\` o `frontend\` (según cuál haya
fallado) con el detalle completo del error — aunque la ventana se cierre
sola, ese archivo se queda ahí. Mandale ese archivo a Claude (o pegale el
contenido) para que te diga exactamente qué pasó.

Otros casos conocidos:

- Si tenés **más de un Python instalado** (por ejemplo el de Microsoft
  Store y el de python.org al mismo tiempo), el script ya usa siempre la
  ruta completa al Python de adentro del entorno virtual
  (`backend\.venv\Scripts\python.exe`) para evitar que se mezclen — pero
  si necesitás correr algo a mano en una terminal nueva, usá esa misma
  ruta completa en vez de escribir `python` o `pip` sueltos.
- Si abrís una terminal nueva para correr algo del backend a mano, acordate
  de setear primero `set DATABASE_URL=sqlite:///./logisla.db` (esa
  ventana no hereda la variable que sí tiene la que abrió el script).
- Si la carpeta está sincronizada con OneDrive y algo se ve "vacío" en el
  Explorador justo después de copiar o extraer archivos, primero refrescá
  la ventana (F5) antes de asumir que faltan.

## Tip: dónde extraer la carpeta

Si es posible, extraé/copiá esta carpeta dentro de tu carpeta **Documents**
de Windows en vez de Escritorio/OneDrive. Es la carpeta a la que Claude
tiene acceso directo desde esta sesión, así que si algo vuelve a fallar
puedo revisar los archivos (y el `install.log`) yo mismo sin que tengas que
copiar y pegar nada.

## Pantallas del frontend

| Ruta | Qué muestra |
| --- | --- |
| `/` | Lotes de la empresa activa, monto total por reclamar y cumplimiento de cada lote |
| `/cargar` | Carga del archivo (clic o arrastrar), columnas detectadas y botón para auditar |
| `/lotes/{id}` | Resultado del lote, desglose por transportista y tabla de guías |

La empresa activa se elige en la cabecera (aparece un selector si hay más de una).

## Reglas SLA de prueba

`iniciar.bat` carga los transportistas y plazos de `backend/scripts/seed_carriers_and_rules.py`
(Chilexpress, Starken, Correos de Chile, Blue Express). Las guías de un transportista sin regla
quedan como "sin regla SLA" y no se auditan.
