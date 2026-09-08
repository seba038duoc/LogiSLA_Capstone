# LogiSLA: Auditoría Inteligente de SLA de Transporte

LogiSLA es una plataforma SaaS orientada a empresas de e-commerce y retail que busca resolver un dolor crítico en la logística: auditar de forma automática y sistemática el cumplimiento de los Acuerdos de Nivel de Servicio (SLA) de los transportistas. 

Mediante el procesamiento masivo de datos y la aplicación de **Inteligencia Artificial Generativa**, el sistema detecta atrasos, calcula multas contractuales y genera automáticamente los documentos de reclamo.

---

## 🤖 Integración de Inteligencia Artificial (IA Generativa)
Este proyecto va más allá del procesamiento tradicional de datos al incorporar un **Módulo de IA Generativa de vanguardia** como pieza clave del valor entregado al usuario

Para cumplir con los más altos estándares de exigencia técnica, el sistema integra la **API de Claude (Anthropic)**, la cual se encarga de:
* **Generación automatizada de documentos:** La IA redacta cartas de reclamo formales y resúmenes ejecutivos de alto nivel basados en los datos duros procesados por el motor.
* **Traducción de datos a lenguaje de negocios:** Toma miles de registros de envíos atrasados y los convierte en un informe estructurado, listo para ser enviado a empresas como Chilexpress o Starken.
* Este enfoque demuestra la capacidad del equipo para orquestar motores determinísticos (cálculo matemático) con modelos probabilísticos (IA) en una misma arquitectura de software.

---

## ⚙️ Características Principales

* **Motor de Auditoría Propio:** Un algoritmo 100% construido por el equipo en Python (Pandas y Workalendar) que calcula tiempos de tránsito efectivos, descontando fines de semana y feriados chilenos mediante procesamiento vectorizado.
* **Ingesta Masiva de Datos:** Capacidad para procesar archivos CSV y Excel de gran volumen (10.000+ filas) con un sistema inteligente de mapeo de columnas y procesamiento asíncrono en segundo plano.
* **Motor de Reglas SLA Dinámico:** Resolución de conflictos de contratos mediante especificidad (ej. Carrier + Zona Origen + Zona Destino), calculando multas exactas o dejándolas pendientes de facturación si falta el costo de flete.
* **Dashboard Interactivo:** Panel de control con métricas clave (KPIs), gráficos interactivos (Recharts) y tablas filtrables por "semáforo" de cumplimiento.

---

## 🛠️ Stack Tecnológico

El proyecto utiliza una arquitectura moderna alojada íntegramente en la nube de Google:

* **Frontend & UX:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Shadcn/ui, Recharts.
* **Backend & API:** Python (FastAPI), Pandas (vectorizado), Workalendar, SQLAlchemy.
* **Inteligencia Artificial:** API Claude (Anthropic) para generación de reportes.
* **Base de Datos:** PostgreSQL.
* **Infraestructura Cloud (GCP):** Cloud Run (contenedores Docker), Cloud SQL, Cloud Storage, Secret Manager.
* **CI/CD & Calidad:** GitHub Actions para despliegue automatizado, testeado con PyTest (Backend), Jest/RTL y Playwright (Frontend E2E).

---

## 👥 Equipo de Desarrollo (Capstone Duoc UC)

Este proyecto está pensado para ser desarrollado en un plazo de 12 semanas (6 Sprints), dividido en responsabilidades claras:

* **Sebastián Acuña** – Desarrollador Backend & GCP: Responsable del motor de auditoría en Python, modelado en PostgreSQL, integración de la IA Generativa (API Claude) y despliegue CI/CD en Google Cloud.
* **José Salvatierra** – Desarrollador Frontend & UX: Responsable de la interfaz en Next.js, mapeo de datos, dashboard de KPIs, exportación de reportes y pruebas End-to-End.