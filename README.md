# LogiSLA: Auditoría Inteligente de SLA de Transporte

LogiSLA es una plataforma SaaS orientada a empresas de e-commerce y retail que busca resolver un problema crítico de la logística: auditar de forma automática y sistemática el cumplimiento de los Acuerdos de Nivel de Servicio (SLA) de los transportistas.

El sistema recibe un archivo masivo de envíos, calcula en horas hábiles qué guías incumplieron el plazo pactado y cuánto corresponde reclamar en multas. En el Sprint 4 se incorpora IA generativa para redactar automáticamente la carta de reclamo y el resumen ejecutivo.

Proyecto de título Capstone · Ingeniería en Informática · Duoc UC · 2026.

---

## 📍 Estado del proyecto (cierre de la Fase 2, semana 12)

| Sprint | Fechas | Alcance | Estado |
|---|---|---|---|
| 1 | Semanas 1 a 6 | Modelo de datos (5 tablas), API de carga y reconocimiento automático de columnas | ✅ Completado |
| 2 | Semanas 7 y 8 | Motor de auditoría: horas hábiles, feriados chilenos y multas | ✅ Completado |
| 3 | Semanas 9 y 10 | Consultas, dashboard y tabla de guías | ✅ Completado |
| 4 | 28 oct al 9 nov | IA generativa, gráficos, PostgreSQL con Alembic, Docker y pruebas del frontend | ⏳ Por iniciar |
| 5 | 10 al 16 nov | CI/CD, pruebas E2E, despliegue en Cloud Run e informe final | ⏳ Por iniciar |

- **17 de noviembre (semana 15):** proyecto terminado y funcionando.
- **1 de diciembre (semana 17):** defensa ante la comisión.

---

## ⚙️ Funcionalidades disponibles

* **Carga de archivos CSV y Excel:** reconoce automáticamente las columnas aunque tengan nombres distintos (por ejemplo, «N° Guía», «Numero de Guia» o «tracking_number»). Si faltan columnas obligatorias, rechaza el archivo indicando cuáles, sin escribir datos en la base.
* **Motor de auditoría propio:** desarrollado por el equipo en Python con Pandas y Workalendar. Calcula el tiempo de tránsito en horas hábiles (lunes a viernes, de 09:00 a 18:00), descuenta fines de semana y feriados chilenos, y aplica la multa fija por guía definida en la regla SLA de cada transportista. Es determinístico y está cubierto por pruebas automatizadas.
* **Dashboard:** listado de lotes, monto por reclamar, franja de cumplimiento, desglose por transportista y tabla de guías con filtros, búsqueda, paginación y descarga de incumplimientos en CSV.

## 🤖 IA generativa (Sprint 4)

El módulo de IA usará la API de Claude (Anthropic) para redactar la carta de reclamo por transportista y el resumen ejecutivo del lote, a partir de los datos ya calculados por el motor. La IA solo redactará texto: las cifras y el anexo de guías y multas los genera siempre el sistema. Si la API falla o demora, el documento se generará con una plantilla de respaldo.

---

## 🛠️ Stack tecnológico

* **Frontend:** Next.js 16 (App Router), React 19, TypeScript y Tailwind CSS.
* **Backend y API:** Python, FastAPI, Pandas, Workalendar y SQLAlchemy.
* **Base de datos:** SQLite en desarrollo local y PostgreSQL 16 con migraciones Alembic para el despliegue (Sprint 4).
* **Calidad:** PyTest en el backend (38 pruebas automatizadas); node:test para el frontend (Sprint 4) y Playwright para las pruebas E2E (Sprint 5).
* **Nube (Sprint 5):** Google Cloud Platform: Cloud Run (contenedores Docker), Cloud SQL y Secret Manager, con CI/CD en GitHub Actions.
* **IA (Sprint 4):** API de Claude (Anthropic).

---

## 🚀 Cómo ejecutarlo

El código está en `Fase 2/Evidencias Proyecto/Evidencias de sistema/Aplicación/`. En Windows, basta con hacer doble clic en `iniciar.bat`. Requisitos: Python 3.10 a 3.14 y Node.js 20.9 o superior.

---

## 📁 Estructura del repositorio

* `Fase 1/`: planificación del proyecto.
* `Fase 2/`: desarrollo. Contiene la guía de avance, los diarios de reflexión, el código, la base de datos, las evidencias ágiles y la presentación.
* `Fase 3/`: cierre (se completa al finalizar el proyecto).

---

## 👥 Equipo de desarrollo

Proyecto desarrollado con metodología Scrum en 5 sprints a lo largo de 15 semanas:

* **Sebastián Acuña:** desarrollador backend y GCP. Responsable del motor de auditoría, el modelo de datos, el módulo de IA generativa (API de Claude) y el despliegue con CI/CD en Google Cloud.
* **José Salvatierra:** desarrollador frontend y UX. Responsable de la interfaz en Next.js, el módulo de carga, el dashboard, la exportación de reportes y las pruebas E2E.
