-- =====================================================================
-- LogiSLA - Esquema de la base de datos (PostgreSQL 16)
-- Versión final del proyecto: migraciones Alembic 0001 (esquema inicial)
-- y 0002 (justificación de la auditoría).
--
-- En la aplicación, este esquema lo crea Alembic automáticamente al abrir
-- iniciar.bat. Este archivo sirve como evidencia y para crearlo a mano:
--   psql -U postgres -d logisla -f schema.sql
-- =====================================================================

-- Estados posibles de un lote de auditoría.
CREATE TYPE estadolote AS ENUM ('PENDIENTE', 'PROCESANDO', 'COMPLETADO', 'FALLIDO');

-- Empresa cliente que audita a sus transportistas.
CREATE TABLE empresas (
    id              UUID         NOT NULL,
    nombre          VARCHAR(255) NOT NULL,
    rut             VARCHAR(20),
    fecha_creacion  TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT empresas_pkey PRIMARY KEY (id),
    CONSTRAINT empresas_rut_key UNIQUE (rut)
);

-- Empresa de transporte o courier (Chilexpress, Starken, etc.).
CREATE TABLE transportistas (
    id              UUID         NOT NULL,
    nombre          VARCHAR(255) NOT NULL,
    fecha_creacion  TIMESTAMPTZ  DEFAULT now(),
    CONSTRAINT transportistas_pkey PRIMARY KEY (id),
    CONSTRAINT transportistas_nombre_key UNIQUE (nombre)
);

-- Archivo de envíos cargado y su estado de auditoría.
CREATE TABLE lotes_auditoria (
    id                       UUID         NOT NULL,
    empresa_id               UUID         NOT NULL,
    nombre_archivo           VARCHAR(500) NOT NULL,
    estado                   estadolote   NOT NULL,
    total_filas              INTEGER      NOT NULL,
    mapeo_columnas           JSON,          -- columna del archivo -> campo de LogiSLA
    advertencias_sin_mapear  JSON,          -- columnas del archivo que no se usaron
    mensaje_error            TEXT,
    fecha_creacion           TIMESTAMPTZ  DEFAULT now(),
    fecha_procesado          TIMESTAMPTZ,
    fecha_corte              TIMESTAMPTZ,   -- 0002: momento de la auditoría
    CONSTRAINT lotes_auditoria_pkey PRIMARY KEY (id),
    CONSTRAINT lotes_auditoria_empresa_id_fkey
        FOREIGN KEY (empresa_id) REFERENCES empresas (id)
);

-- Plazo en horas hábiles y multa por guía pactados con un transportista.
CREATE TABLE reglas_sla (
    id                        UUID             NOT NULL,
    transportista_id          UUID             NOT NULL,
    tipo_servicio             VARCHAR(100),
    horas_habiles_maximas     INTEGER          NOT NULL,
    multa_por_incumplimiento  DOUBLE PRECISION NOT NULL,
    activa                    BOOLEAN,
    fecha_creacion            TIMESTAMPTZ      DEFAULT now(),
    CONSTRAINT reglas_sla_pkey PRIMARY KEY (id),
    CONSTRAINT reglas_sla_transportista_id_fkey
        FOREIGN KEY (transportista_id) REFERENCES transportistas (id)
);

-- Una guía del archivo y su resultado de auditoría.
CREATE TABLE envios (
    id                             UUID             NOT NULL,
    lote_auditoria_id              UUID             NOT NULL,
    transportista_id               UUID,            -- nulo si el transportista no existe
    nombre_transportista_original  VARCHAR(255),    -- tal como venía en el archivo
    numero_guia                    VARCHAR(100)     NOT NULL,
    fecha_despacho                 TIMESTAMPTZ      NOT NULL,
    fecha_entrega                  TIMESTAMPTZ,     -- nulo si no registra entrega
    destino                        VARCHAR(255),
    valor_declarado                DOUBLE PRECISION,
    -- Calculados por el motor de auditoría:
    incumplio_sla                  BOOLEAN,
    horas_atraso                   DOUBLE PRECISION,
    monto_multa                    DOUBLE PRECISION,
    fecha_creacion                 TIMESTAMPTZ      DEFAULT now(),
    -- Justificación de la auditoría (migración 0002):
    resultado                      VARCHAR(30),     -- CUMPLIDO, INCUMPLIDO, EN_TRANSITO,
                                                    -- VENCIDA_SIN_ENTREGA, SIN_REGLA o DATOS_INVALIDOS
    fecha_limite                   TIMESTAMPTZ,     -- vencimiento del plazo SLA
    horas_habiles_transcurridas    DOUBLE PRECISION, -- hasta la entrega o hasta la fecha de corte
    observacion                    TEXT,            -- por qué los datos no permiten auditarla
    CONSTRAINT envios_pkey PRIMARY KEY (id),
    CONSTRAINT envios_lote_auditoria_id_fkey
        FOREIGN KEY (lote_auditoria_id) REFERENCES lotes_auditoria (id),
    CONSTRAINT envios_transportista_id_fkey
        FOREIGN KEY (transportista_id) REFERENCES transportistas (id)
);

-- Control de versiones del esquema (Alembic).
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO alembic_version (version_num) VALUES ('0002');
