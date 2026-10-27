-- =============================================================================
-- LogiSLA · Esquema de base de datos para PostgreSQL 16
-- Proyecto de título Capstone · Duoc UC · Fase 2
--
-- Equivale al modelo SQLAlchemy de backend/app/models.py (mismos nombres de
-- tablas, columnas, tipos, claves y restricciones), de modo que la API
-- funciona igual sobre una base creada con este script. Agrega índices sobre
-- las claves foráneas para las consultas del dashboard.
--
-- Uso:
--   psql -U logisla -d logisla -f schema.sql
--
-- El script es re-ejecutable: elimina y vuelve a crear los objetos.
-- En el Sprint 4 este esquema pasa a administrarse con migraciones Alembic.
-- =============================================================================

BEGIN;

DROP TABLE IF EXISTS envios CASCADE;
DROP TABLE IF EXISTS lotes_auditoria CASCADE;
DROP TABLE IF EXISTS reglas_sla CASCADE;
DROP TABLE IF EXISTS transportistas CASCADE;
DROP TABLE IF EXISTS empresas CASCADE;
DROP TYPE IF EXISTS estadolote;

-- Estado de un lote de auditoría (EstadoLote en models.py).
--   PENDIENTE  : archivo cargado, aún no auditado
--   PROCESANDO : reservado para procesamiento asíncrono futuro
--   COMPLETADO : el motor de auditoría ya corrió sobre el lote
--   FALLIDO    : reservado para errores de procesamiento
CREATE TYPE estadolote AS ENUM ('PENDIENTE', 'PROCESANDO', 'COMPLETADO', 'FALLIDO');

-- -----------------------------------------------------------------------------
-- empresas: clientes que cargan archivos de envíos
-- -----------------------------------------------------------------------------
CREATE TABLE empresas (
    id              UUID         NOT NULL DEFAULT gen_random_uuid(),
    nombre          VARCHAR(255) NOT NULL,
    rut             VARCHAR(20),
    fecha_creacion  TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT empresas_pkey PRIMARY KEY (id),
    CONSTRAINT empresas_rut_key UNIQUE (rut)
);
COMMENT ON TABLE  empresas     IS 'Clientes de LogiSLA que cargan archivos de envíos.';
COMMENT ON COLUMN empresas.rut IS 'RUT de la empresa; único y opcional.';

-- -----------------------------------------------------------------------------
-- transportistas: catálogo de transportistas
-- -----------------------------------------------------------------------------
CREATE TABLE transportistas (
    id              UUID         NOT NULL DEFAULT gen_random_uuid(),
    nombre          VARCHAR(255) NOT NULL,
    fecha_creacion  TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT transportistas_pkey PRIMARY KEY (id),
    CONSTRAINT transportistas_nombre_key UNIQUE (nombre)
);
COMMENT ON TABLE transportistas IS 'Catálogo de transportistas (Chilexpress, Starken, etc.).';

-- -----------------------------------------------------------------------------
-- reglas_sla: plazo en horas hábiles y multa fija por guía de cada transportista
-- -----------------------------------------------------------------------------
CREATE TABLE reglas_sla (
    id                        UUID             NOT NULL DEFAULT gen_random_uuid(),
    transportista_id          UUID             NOT NULL,
    tipo_servicio             VARCHAR(100),
    horas_habiles_maximas     INTEGER          NOT NULL,
    multa_por_incumplimiento  DOUBLE PRECISION NOT NULL,
    activa                    BOOLEAN          DEFAULT TRUE,
    fecha_creacion            TIMESTAMPTZ      DEFAULT now(),
    CONSTRAINT reglas_sla_pkey PRIMARY KEY (id),
    CONSTRAINT reglas_sla_transportista_id_fkey
        FOREIGN KEY (transportista_id) REFERENCES transportistas (id)
);
COMMENT ON TABLE  reglas_sla               IS 'Plazo máximo en horas hábiles (lun-vie 09:00-18:00, sin feriados) y multa fija por guía incumplida.';
COMMENT ON COLUMN reglas_sla.tipo_servicio IS 'Opcional. Los archivos de envío no traen tipo de servicio, por lo que el motor usa la regla general (tipo_servicio NULL) de cada transportista.';

-- -----------------------------------------------------------------------------
-- lotes_auditoria: un archivo cargado y su estado
-- -----------------------------------------------------------------------------
CREATE TABLE lotes_auditoria (
    id                       UUID         NOT NULL DEFAULT gen_random_uuid(),
    empresa_id               UUID         NOT NULL,
    nombre_archivo           VARCHAR(500) NOT NULL,
    estado                   estadolote   NOT NULL DEFAULT 'PENDIENTE',
    total_filas              INTEGER      NOT NULL DEFAULT 0,
    mapeo_columnas           JSON,
    advertencias_sin_mapear  JSON,
    mensaje_error            TEXT,
    fecha_creacion           TIMESTAMPTZ  DEFAULT now(),
    fecha_procesado          TIMESTAMPTZ,
    CONSTRAINT lotes_auditoria_pkey PRIMARY KEY (id),
    CONSTRAINT lotes_auditoria_empresa_id_fkey
        FOREIGN KEY (empresa_id) REFERENCES empresas (id)
);
COMMENT ON TABLE  lotes_auditoria                IS 'Un archivo CSV/Excel cargado por una empresa y su estado de auditoría.';
COMMENT ON COLUMN lotes_auditoria.mapeo_columnas IS 'Columnas del archivo reconocidas automáticamente (campo interno -> encabezado), para trazabilidad.';

-- -----------------------------------------------------------------------------
-- envios: una guía de despacho
-- -----------------------------------------------------------------------------
CREATE TABLE envios (
    id                             UUID             NOT NULL DEFAULT gen_random_uuid(),
    lote_auditoria_id              UUID             NOT NULL,
    transportista_id               UUID,
    nombre_transportista_original  VARCHAR(255),
    numero_guia                    VARCHAR(100)     NOT NULL,
    fecha_despacho                 TIMESTAMPTZ      NOT NULL,
    fecha_entrega                  TIMESTAMPTZ,
    destino                        VARCHAR(255),
    valor_declarado                DOUBLE PRECISION,
    incumplio_sla                  BOOLEAN,
    horas_atraso                   DOUBLE PRECISION,
    monto_multa                    DOUBLE PRECISION,
    fecha_creacion                 TIMESTAMPTZ      DEFAULT now(),
    CONSTRAINT envios_pkey PRIMARY KEY (id),
    CONSTRAINT envios_lote_auditoria_id_fkey
        FOREIGN KEY (lote_auditoria_id) REFERENCES lotes_auditoria (id),
    CONSTRAINT envios_transportista_id_fkey
        FOREIGN KEY (transportista_id) REFERENCES transportistas (id)
);
COMMENT ON TABLE  envios                  IS 'Guías de despacho de un lote. Los campos de resultado quedan NULL hasta que el motor audita el lote.';
COMMENT ON COLUMN envios.transportista_id IS 'Opcional: se resuelve al auditar, a partir de nombre_transportista_original.';
COMMENT ON COLUMN envios.fecha_entrega    IS 'NULL = guía en tránsito; no se audita.';
COMMENT ON COLUMN envios.incumplio_sla    IS 'Calculado por el motor de auditoría.';
COMMENT ON COLUMN envios.horas_atraso     IS 'Horas hábiles por sobre el plazo de la regla SLA (0 si cumple). Calculado por el motor.';
COMMENT ON COLUMN envios.monto_multa      IS 'Multa fija de la regla SLA si incumplió; 0 si cumple. Calculado por el motor.';

-- Índices sobre claves foráneas (consultas del dashboard por lote y transportista).
CREATE INDEX ix_reglas_sla_transportista_id ON reglas_sla (transportista_id);
CREATE INDEX ix_lotes_auditoria_empresa_id  ON lotes_auditoria (empresa_id);
CREATE INDEX ix_envios_lote_auditoria_id    ON envios (lote_auditoria_id);
CREATE INDEX ix_envios_transportista_id     ON envios (transportista_id);

COMMIT;
