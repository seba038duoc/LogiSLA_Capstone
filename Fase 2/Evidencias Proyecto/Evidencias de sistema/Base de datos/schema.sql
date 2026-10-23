-- =============================================================================
-- LogiSLA · Modelo de datos para PostgreSQL 16
-- Capstone Duoc UC · Fase 2
--
-- Contenido:
--   1. Creación de tipos y tablas (empresas, transportistas, reglas_sla,
--      lotes_auditoria, envios), tal como las define app/models.py.
--   2. Índices de apoyo para las consultas del dashboard.
--   3. Datos de prueba (empresa piloto, 4 transportistas con su regla SLA,
--      1 lote y 6 envíos).
--   4. Consultas de verificación.
--
-- Uso (desde una terminal con PostgreSQL 16):
--   createdb logisla
--   psql -d logisla -f schema.sql
--
-- Notas:
--   * gen_random_uuid() viene incluida en PostgreSQL 13 o superior, no
--     requiere extensiones.
--   * El script es re-ejecutable: borra y vuelve a crear las tablas.
--     Eliminar la sección "0. Limpieza" si no se desea ese comportamiento.
--   * Los resultados de la auditoría (incumplio_sla, horas_atraso,
--     monto_multa) quedan en NULL tras la ingesta y los completa el motor de
--     auditoría. Aquí se cargan ya calculados para poder verificar el modelo.
-- =============================================================================

SET client_encoding = 'UTF8';

-- -----------------------------------------------------------------------------
-- 0. Limpieza
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS envios            CASCADE;
DROP TABLE IF EXISTS lotes_auditoria   CASCADE;
DROP TABLE IF EXISTS reglas_sla        CASCADE;
DROP TABLE IF EXISTS transportistas    CASCADE;
DROP TABLE IF EXISTS empresas          CASCADE;
DROP TYPE  IF EXISTS estado_lote;

-- -----------------------------------------------------------------------------
-- 1. Tipos y tablas
-- -----------------------------------------------------------------------------

-- Estado de un lote de auditoría (EstadoLote en app/models.py)
CREATE TYPE estado_lote AS ENUM ('PENDIENTE', 'PROCESANDO', 'COMPLETADO', 'FALLIDO');

-- Clientes que cargan archivos de envíos
CREATE TABLE empresas (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre          VARCHAR(255) NOT NULL,
    rut             VARCHAR(20)  UNIQUE,
    fecha_creacion  TIMESTAMPTZ  DEFAULT now()
);

-- Catálogo de transportistas
CREATE TABLE transportistas (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre          VARCHAR(255) NOT NULL UNIQUE,
    fecha_creacion  TIMESTAMPTZ  DEFAULT now()
);

-- Regla SLA de un transportista: plazo máximo en horas hábiles y multa fija
CREATE TABLE reglas_sla (
    id                        UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    transportista_id          UUID             NOT NULL REFERENCES transportistas (id),
    tipo_servicio             VARCHAR(100),
    horas_habiles_maximas     INTEGER          NOT NULL CHECK (horas_habiles_maximas > 0),
    multa_por_incumplimiento  DOUBLE PRECISION NOT NULL CHECK (multa_por_incumplimiento >= 0),
    activa                    BOOLEAN          DEFAULT TRUE,
    fecha_creacion            TIMESTAMPTZ      DEFAULT now()
);

-- Un archivo cargado por una empresa y su estado de procesamiento
CREATE TABLE lotes_auditoria (
    id                       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id               UUID         NOT NULL REFERENCES empresas (id),
    nombre_archivo           VARCHAR(500) NOT NULL,
    estado                   estado_lote  NOT NULL DEFAULT 'PENDIENTE',
    total_filas              INTEGER      NOT NULL DEFAULT 0 CHECK (total_filas >= 0),
    mapeo_columnas           JSON,
    advertencias_sin_mapear  JSON,
    mensaje_error            TEXT,
    fecha_creacion           TIMESTAMPTZ  DEFAULT now(),
    fecha_procesado          TIMESTAMPTZ
);

-- Una guía de despacho. Los tres últimos campos de resultado los completa el
-- motor de auditoría; transportista_id es opcional porque se resuelve al auditar.
CREATE TABLE envios (
    id                             UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    lote_auditoria_id              UUID             NOT NULL REFERENCES lotes_auditoria (id) ON DELETE CASCADE,
    transportista_id               UUID             REFERENCES transportistas (id),
    nombre_transportista_original  VARCHAR(255),
    numero_guia                    VARCHAR(100)     NOT NULL,
    fecha_despacho                 TIMESTAMPTZ      NOT NULL,
    fecha_entrega                  TIMESTAMPTZ,
    destino                        VARCHAR(255),
    valor_declarado                DOUBLE PRECISION,
    incumplio_sla                  BOOLEAN,
    horas_atraso                   DOUBLE PRECISION,
    monto_multa                    DOUBLE PRECISION,
    fecha_creacion                 TIMESTAMPTZ      DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 2. Índices de apoyo (consultas del dashboard y búsqueda por guía)
-- -----------------------------------------------------------------------------
CREATE INDEX idx_reglas_sla_transportista  ON reglas_sla (transportista_id) WHERE activa;
CREATE INDEX idx_lotes_empresa             ON lotes_auditoria (empresa_id);
CREATE INDEX idx_envios_lote               ON envios (lote_auditoria_id);
CREATE INDEX idx_envios_transportista      ON envios (transportista_id);
CREATE INDEX idx_envios_numero_guia        ON envios (numero_guia);

-- -----------------------------------------------------------------------------
-- 3. Datos de prueba
-- -----------------------------------------------------------------------------

-- Empresa piloto
INSERT INTO empresas (id, nombre, rut) VALUES
    ('00000000-0000-0000-0000-0000000000e1', 'Retail Piloto SpA', NULL);

-- Transportistas chilenos conocidos
INSERT INTO transportistas (id, nombre) VALUES
    ('00000000-0000-0000-0000-0000000000a1', 'Chilexpress'),
    ('00000000-0000-0000-0000-0000000000a2', 'Starken'),
    ('00000000-0000-0000-0000-0000000000a3', 'Correos de Chile'),
    ('00000000-0000-0000-0000-0000000000a4', 'Blue Express');

-- Una regla SLA activa por transportista (horas hábiles máximas, multa fija en CLP)
INSERT INTO reglas_sla (transportista_id, tipo_servicio, horas_habiles_maximas, multa_por_incumplimiento, activa) VALUES
    ('00000000-0000-0000-0000-0000000000a1', NULL, 48, 15000, TRUE),
    ('00000000-0000-0000-0000-0000000000a2', NULL, 60, 12000, TRUE),
    ('00000000-0000-0000-0000-0000000000a3', NULL, 72, 10000, TRUE),
    ('00000000-0000-0000-0000-0000000000a4', NULL, 48, 15000, TRUE);

-- Un lote ya auditado, con 6 envíos
INSERT INTO lotes_auditoria
    (id, empresa_id, nombre_archivo, estado, total_filas, mapeo_columnas, fecha_procesado)
VALUES
    ('00000000-0000-0000-0000-0000000000b1',
     '00000000-0000-0000-0000-0000000000e1',
     'envios_prueba.csv', 'COMPLETADO', 6,
     '{"N° Guía": "numero_guia", "Transportista": "transportista", "Fecha Despacho": "fecha_despacho", "Fecha Entrega": "fecha_entrega", "Destino": "destino", "Valor Declarado": "valor_declarado"}',
     '2026-09-16 10:00:00-03');

-- Jornada hábil: lunes a viernes, 09:00 a 18:00 (9 horas por día).
-- Horas de atraso = horas hábiles de tránsito - horas hábiles máximas de la regla.
INSERT INTO envios
    (id, lote_auditoria_id, transportista_id, nombre_transportista_original, numero_guia,
     fecha_despacho, fecha_entrega, destino, valor_declarado, incumplio_sla, horas_atraso, monto_multa)
VALUES
    -- 1. Chilexpress: 27 h hábiles (límite 48) -> cumple
    ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-0000000000b1',
     '00000000-0000-0000-0000-0000000000a1', 'Chilexpress', 'LSA-202600001',
     '2026-09-07 09:00:00-03', '2026-09-09 18:00:00-03', 'La Serena', 56119, FALSE, 0, 0),
    -- 2. Chilexpress: 54 h hábiles (límite 48) -> incumple, 6 h de atraso
    ('00000000-0000-0000-0000-000000000102', '00000000-0000-0000-0000-0000000000b1',
     '00000000-0000-0000-0000-0000000000a1', 'Chilexpress', 'LSA-202600002',
     '2026-09-07 09:00:00-03', '2026-09-14 18:00:00-03', 'Valparaíso', 110105, TRUE, 6, 15000),
    -- 3. Starken: 63 h hábiles (límite 60) -> incumple, 3 h de atraso
    ('00000000-0000-0000-0000-000000000103', '00000000-0000-0000-0000-0000000000b1',
     '00000000-0000-0000-0000-0000000000a2', 'Starken', 'LSA-202600003',
     '2026-09-07 09:00:00-03', '2026-09-15 18:00:00-03', 'Concepción', 84500, TRUE, 3, 12000),
    -- 4. Blue Express: 15 h hábiles (límite 48) -> cumple
    ('00000000-0000-0000-0000-000000000104', '00000000-0000-0000-0000-0000000000b1',
     '00000000-0000-0000-0000-0000000000a4', 'Blue Express', 'LSA-202600004',
     '2026-09-11 15:00:00-03', '2026-09-15 12:00:00-03', 'Temuco', 62017, FALSE, 0, 0),
    -- 5. Correos de Chile: sin fecha de entrega -> no se audita
    ('00000000-0000-0000-0000-000000000105', '00000000-0000-0000-0000-0000000000b1',
     '00000000-0000-0000-0000-0000000000a3', 'Correos de Chile', 'LSA-202600005',
     '2026-09-10 09:00:00-03', NULL, 'Antofagasta', 45300, NULL, NULL, NULL),
    -- 6. Transportista sin regla SLA registrada -> no se audita
    ('00000000-0000-0000-0000-000000000106', '00000000-0000-0000-0000-0000000000b1',
     NULL, 'Transportes Rápidos Ltda', 'LSA-202600006',
     '2026-09-09 09:00:00-03', '2026-09-11 18:00:00-03', 'Iquique', 73200, NULL, NULL, NULL);

-- -----------------------------------------------------------------------------
-- 4. Consultas de verificación
--    Resultados esperados con los datos de prueba de este script.
-- -----------------------------------------------------------------------------

-- 4.1 Filas por tabla
--     Esperado: empresas 1 · transportistas 4 · reglas_sla 4 · lotes_auditoria 1 · envios 6
SELECT 'empresas' AS tabla, count(*) AS filas FROM empresas
UNION ALL SELECT 'transportistas',   count(*) FROM transportistas
UNION ALL SELECT 'reglas_sla',       count(*) FROM reglas_sla
UNION ALL SELECT 'lotes_auditoria',  count(*) FROM lotes_auditoria
UNION ALL SELECT 'envios',           count(*) FROM envios;

-- 4.2 Cada transportista tiene exactamente una regla SLA activa
--     Esperado: 0 filas
SELECT t.nombre, count(r.id) AS reglas_activas
FROM transportistas t
LEFT JOIN reglas_sla r ON r.transportista_id = t.id AND r.activa
GROUP BY t.nombre
HAVING count(r.id) <> 1;

-- 4.3 Integridad referencial: envíos cuyo lote no existe
--     Esperado: 0 filas
SELECT e.id
FROM envios e
LEFT JOIN lotes_auditoria l ON l.id = e.lote_auditoria_id
WHERE l.id IS NULL;

-- 4.4 Resumen del lote
--     Esperado: total_envios 6 · auditados 4 · incumplimientos 2 · multa_total 27000
SELECT l.nombre_archivo,
       l.estado,
       count(e.id)                                     AS total_envios,
       count(e.incumplio_sla)                          AS auditados,
       count(*) FILTER (WHERE e.incumplio_sla)         AS incumplimientos,
       coalesce(sum(e.monto_multa), 0)                 AS multa_total
FROM lotes_auditoria l
JOIN envios e ON e.lote_auditoria_id = l.id
GROUP BY l.id, l.nombre_archivo, l.estado;

-- 4.5 Cumplimiento y multa por transportista
--     Esperado: Chilexpress 2 auditados, 1 incumple, 15000 · Starken 1 auditado, 1 incumple, 12000
--               Blue Express 1 auditado, 0 incumple, 0 · Correos de Chile 0 auditados
SELECT t.nombre                                        AS transportista,
       count(e.id)                                     AS envios,
       count(e.incumplio_sla)                          AS auditados,
       count(*) FILTER (WHERE e.incumplio_sla)         AS incumplimientos,
       coalesce(sum(e.monto_multa), 0)                 AS multa_total
FROM transportistas t
LEFT JOIN envios e ON e.transportista_id = t.id
GROUP BY t.nombre
ORDER BY multa_total DESC, t.nombre;

-- 4.6 Envíos que no se auditaron y el motivo
--     Esperado: LSA-202600005 (sin fecha de entrega) y LSA-202600006 (sin regla SLA)
SELECT numero_guia,
       nombre_transportista_original,
       CASE
           WHEN fecha_entrega IS NULL    THEN 'Sin fecha de entrega'
           WHEN transportista_id IS NULL THEN 'Transportista sin regla SLA'
       END AS motivo
FROM envios
WHERE incumplio_sla IS NULL
ORDER BY numero_guia;

-- 4.7 Coherencia del resultado: la multa solo existe si incumplió el SLA
--     Esperado: 0 filas
SELECT numero_guia, incumplio_sla, horas_atraso, monto_multa
FROM envios
WHERE (incumplio_sla IS TRUE  AND (horas_atraso <= 0 OR monto_multa <= 0))
   OR (incumplio_sla IS FALSE AND (horas_atraso <> 0 OR monto_multa <> 0));

-- 4.8 Guías repetidas dentro de un mismo lote
--     Esperado: 0 filas
SELECT lote_auditoria_id, numero_guia, count(*) AS repeticiones
FROM envios
GROUP BY lote_auditoria_id, numero_guia
HAVING count(*) > 1;
