# LogiSLA: Auditoría Inteligente de SLA de Transporte

LogiSLA es una plataforma para empresas de e-commerce y retail que audita automáticamente si los transportistas cumplen los Acuerdos de Nivel de Servicio (SLA) pactados en sus contratos.

El sistema recibe la planilla de envíos de un período, calcula en horas hábiles qué guías se entregaron fuera de plazo y cuánto corresponde reclamar en multas. Además, con IA generativa redacta la carta de reclamo para cada transportista y un resumen ejecutivo del lote.

Proyecto de título Capstone · Ingeniería en Informática · Duoc UC · 2026.

**Aplicación en línea:** https://logisla-frontend.onrender.com (al estar en un plan gratuito, la primera carga puede tardar cerca de un minuto).

---

## 📍 Estado del proyecto

| Sprint | Fechas | Alcance | Estado |
|---|---|---|---|
| 1 | Semanas 1 a 6 | Modelo de datos (5 tablas), API de carga y reconocimiento automático de columnas | ✅ Completado |
| 2 | Semanas 7 y 8 | Motor de auditoría: horas hábiles, feriados chilenos y multas | ✅ Completado |
| 3 | Semanas 9 y 10 | Consultas, dashboard y tabla de guías | ✅ Completado |
| 4 | 28 de octubre al 9 de noviembre | IA generativa (carta de reclamo y resumen ejecutivo, con plantilla de respaldo), gráficos por transportista, PostgreSQL con migraciones Alembic y Docker | ✅ Completado |
| 5 | 10 al 16 de noviembre | CI/CD con GitHub Actions, pruebas E2E con Playwright, despliegue en la nube (Render y Neon) y auditoría justificada guía por guía | ✅ Completado |

* **17 de noviembre:** proyecto terminado y funcionando. Ese día se verificó el pipeline de GitHub Actions completo (6 etapas aprobadas) y la aplicación publicada en Render, con la base de datos en Neon, auditando la planilla piloto con el mismo resultado que en local: $170.000 en 13 guías fuera de plazo.
* **25 de noviembre:** IA activa con Claude como proveedor principal y nueva tipografía, más legible en pantalla y en proyector, a pedido del docente guía.
* **1 de diciembre:** defensa ante la Comisión Evaluadora.

### Ajustes respecto de la planificación inicial

* **Nube sin costo:** Google Cloud Run exige una cuenta de facturación con tarjeta de crédito, así que la aplicación se publica con las mismas imágenes Docker en **Render**, con la base PostgreSQL en **Neon**, ambos en planes gratuitos. Las claves se guardan cifradas en Render, fuera del repositorio. El despliegue en Cloud Run con Secret Manager queda preparado como alternativa (`deploy/desplegar_cloud_run.sh`).
* **IA generativa:** la API de Gemini no ofreció cuota gratuita a las cuentas del equipo, por lo que la IA funciona con **Claude** (Anthropic) mediante créditos prepagados de bajo costo. Gemini queda como alternativa, y una plantilla fija asegura que la carta se genere aunque ninguna IA responda.
* **Planificación:** el Sprint 3 quedó sobrecomprometido, por lo que la IA y los gráficos pasaron al Sprint 4, y CI/CD y la nube al Sprint 5, sin cambiar la fecha de entrega.

---

## ⚙️ Funcionalidades

* **Carga de archivos CSV y Excel:** reconoce automáticamente las columnas aunque tengan nombres distintos (por ejemplo, «N° Guía», «Numero de Guia» o «tracking_number»). Si faltan columnas obligatorias, rechaza el archivo e indica cuáles faltan, sin guardar datos.
* **Motor de auditoría propio:** desarrollado por el equipo en Python con Pandas y Workalendar. Calcula el tiempo de tránsito en horas hábiles (lunes a viernes, de 09:00 a 18:00), descuenta los fines de semana y los feriados de Chile, y aplica la multa fija por guía definida en la regla SLA de cada transportista. Es determinístico y está cubierto por pruebas automatizadas.
* **Auditoría justificada guía por guía:** cada guía indica si la encomienda llegó o no, su **fecha límite** (despacho más las horas hábiles del SLA), las horas hábiles usadas frente a las permitidas, los fines de semana y feriados que no se contaron, y una explicación de su resultado.
* **Fecha de corte y guías sin entrega:** cada auditoría registra su fecha de corte. Una guía sin entrega cuyo plazo ya venció queda como **«vencida sin entrega»**: es una alerta para pedir el comprobante al transportista y no lleva multa, porque no hay prueba de cuándo llegó. Si el plazo aún no vence, queda «en tránsito».
* **Control de calidad de los datos:** las guías con entrega anterior al despacho, con fechas posteriores al corte o con número de guía repetido se marcan como «datos a revisar», con su motivo, y no se multan. Una guía repetida se audita una sola vez.
* **Criterios visibles e informe de auditoría:** el detalle del lote muestra los criterios aplicados (fecha de corte, jornada hábil, feriados del período y reglas de clasificación). Se puede descargar el detalle completo en CSV y generar un **informe de auditoría** listo para imprimir o guardar como PDF.
* **Gráficos por transportista:** multa por reclamar y atraso promedio de las guías fuera de plazo.
* **Dashboard:** portada con accesos rápidos, listado de lotes, monto por reclamar, franja de cumplimiento, desglose por transportista y tabla de guías con filtros, búsqueda, paginación y descarga de incumplimientos en CSV.

## 🤖 IA generativa: carta de reclamo y resumen ejecutivo

Desde el detalle de un lote auditado se generan dos documentos:

* **Resumen ejecutivo** para la gerencia: resultado general, transportistas que concentran las multas y una recomendación.
* **Carta de reclamo** para el transportista seleccionado, con anexo guía por guía.

Ambos siguen las mismas reglas:

* **Proveedores con respaldo automático:** redacta **Claude** (Anthropic, modelo `claude-haiku-5-5`). Si no responde o su texto no pasa la revisión de cifras, se intenta con **Google Gemini**, siempre que tenga clave y cuota. El orden se define con `IA_PRINCIPAL`. La pantalla indica qué IA redactó el texto y, si se usó un respaldo, el motivo. Las llamadas a los proveedores están aisladas en `backend/app/ia_proveedores.py`.
* **La IA solo redacta.** Las cifras las calcula el motor de auditoría. A la IA se le envía solo un resumen agregado (cantidad de guías, montos, plazo y período), nunca números de guía, destinos ni datos de clientes.
* **Control de cifras:** el sistema revisa la respuesta. Si no incluye el monto total y la cantidad de guías exactos, o menciona un monto que el sistema no calculó, la descarta.
* **Gasto acotado:** la IA se llama solo al presionar el botón, el mensaje enviado es breve y la longitud de la respuesta está limitada.
* **Plantilla de respaldo:** si ninguna IA entrega un texto válido (sin claves, sin conexión o sin saldo), la carta se genera con una plantilla fija y la pantalla informa el motivo.
* **Encabezado, firma y anexo guía por guía** de la carta los arma siempre el sistema con los datos de la base.

Las claves se configuran en `backend/.env`, archivo excluido de Git (la plantilla está en `backend/.env.example`):

```
ANTHROPIC_API_KEY=su_clave_de_platform.claude.com
IA_PRINCIPAL=claude
GEMINI_API_KEY=su_clave_de_aistudio.google.com   (opcional)
```

Para comprobarlas: `backend\.venv\Scripts\python.exe backend\scripts\probar_ia.py`.

---

## 🛠️ Stack tecnológico

* **Frontend:** Next.js 16 (App Router), React 19, TypeScript y Tailwind CSS.
* **Backend y API:** Python, FastAPI, Pandas, Workalendar y SQLAlchemy.
* **Base de datos:** PostgreSQL 16, con el esquema versionado en migraciones de Alembic. `iniciar.bat` crea, enciende y apaga su propio PostgreSQL en versión portable, sin instalación ni permisos de administrador. SQLite queda solo como modo de emergencia (`iniciar.bat --sqlite`).
* **IA generativa:** Claude Haiku 5.5 (Anthropic) como proveedor principal y Google Gemini como alternativa, ambos mediante su API REST con la biblioteca estándar de Python.
* **Calidad:** 168 pruebas automatizadas. 131 del backend y del lanzador con PyTest (96 % de cobertura), que se ejecutan sobre SQLite y sobre PostgreSQL 16 con las IA simuladas; 32 pruebas unitarias del frontend con el ejecutor de pruebas de Node.js; y 5 pruebas E2E con Playwright, que recorren la aplicación en un navegador real. El código se formatea con Black (Python) y Prettier (TypeScript y CSS).
* **Contenedores:** Dockerfile del backend y del frontend, y `docker-compose.yml` con PostgreSQL, backend y frontend.
* **Nube:** despliegue en Render con un Blueprint (`render.yaml`, en la raíz del repositorio) que construye las imágenes Docker del backend y del frontend; base de datos en Neon. Las claves no están en el repositorio: Render las guarda cifradas y las entrega como variables de entorno.
* **CI/CD con GitHub Actions:** en cada cambio se ejecutan las pruebas del backend en SQLite y en PostgreSQL (incluidas las migraciones), las pruebas unitarias y la compilación de producción del frontend, las pruebas E2E y la construcción de las imágenes Docker, que se levantan con docker compose para auditar la planilla piloto dentro de los contenedores. Si todo se aprueba en la rama principal, se publica el paquete de la aplicación.

---

## 🚀 Cómo ejecutarlo

Requisitos: Windows, Python 3.10 a 3.14, Node.js 20.9 o superior y PostgreSQL 16. Para PostgreSQL basta el zip oficial de binarios ([enterprisedb.com/download-postgresql-binaries](https://www.enterprisedb.com/download-postgresql-binaries)) descomprimido en `C:\LogiSLA\pgsql`; también sirve un PostgreSQL ya instalado.

1. Hacer doble clic en `iniciar.bat`, dentro de la carpeta de la aplicación.
2. La primera vez se instalan las dependencias, lo que toma unos minutos; después arranca en menos de un minuto.
3. Cuando la ventana muestra «LogiSLA está funcionando», se abre el navegador. Para detenerlo, basta con cerrar esa ventana.

Al arrancar, LogiSLA enciende PostgreSQL, aplica las migraciones de Alembic, elige puertos libres, carga una empresa y reglas SLA de prueba, y deja el backend y el frontend en una sola ventana. Al cerrarla se detiene todo, incluido PostgreSQL. Para probar, la portada ofrece descargar una planilla de ejemplo (`envios_piloto.csv`).

**Con Docker** (requiere Docker Desktop), desde la carpeta de la aplicación:

```
docker compose up --build
```

Levanta PostgreSQL 16, el backend y el frontend en contenedores; la aplicación queda disponible en http://localhost:3000. Las claves de la IA se leen de `backend/.env`.

**En la nube (Render y Neon):** ver `deploy/LEEME_RENDER.txt`. Alternativa con Google Cloud Run: `deploy/LEEME_CLOUD_RUN.txt`.

**Pruebas del backend** (desde la carpeta `backend`):

```
.venv\Scripts\python.exe -m pytest -v
```

**Pruebas unitarias del frontend** (desde la carpeta `frontend`):

```
npm test
```

**Pruebas E2E** (con LogiSLA en ejecución, desde la carpeta `e2e`; la primera vez se descarga el navegador):

```
npm install
npx playwright install chromium
npm test
```

---

## 📁 Estructura del repositorio

* `Fase 1/`: definición y planificación del proyecto.
* `Fase 2/`: desarrollo. Contiene la guía de desarrollo, el informe final, los diarios de reflexión, las evidencias ágiles, la presentación y la versión final de la aplicación y de la base de datos (`Fase 2/Evidencias Proyecto/Evidencias de sistema/`).
* `Fase 3/`: cierre. Contiene los diarios de reflexión de la Fase 3 y la presentación final.

---

## 👥 Equipo de desarrollo

Proyecto desarrollado con metodología Scrum en 5 sprints a lo largo de 15 semanas:

* **Sebastián Acuña:** Scrum Master y desarrollador backend. Responsable del motor de auditoría, el modelo de datos, el módulo de IA generativa y la operación con CI/CD, Docker y la nube.
* **José Salvatierra:** Product Owner y desarrollador frontend y UX. Responsable de la interfaz en Next.js, el módulo de carga, el dashboard, los reportes y las pruebas E2E.

Docente guía: Félix Cifuentes.
