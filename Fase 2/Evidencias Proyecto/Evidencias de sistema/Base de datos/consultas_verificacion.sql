-- =====================================================================
-- LogiSLA - Consultas de verificación de la base de datos
-- Comprueban el esquema, los datos de prueba y el resultado de auditar
-- la planilla envios_julio_2026.csv (103 guías).
--
-- Uso (con LogiSLA abierto y la planilla de julio ya auditada):
--   psql -h 127.0.0.1 -p 5433 -U postgres -d logisla -f consultas_verificacion.sql -o resultado_verificacion.txt
-- =====================================================================

\encoding UTF8
\pset footer off

\qecho '1. Versión del esquema (Alembic): debe ser 0002'
SELECT version_num AS version_esquema FROM alembic_version;

\qecho ''
\qecho '2. Registros por tabla'
SELECT 'empresas' AS tabla, count(*) AS registros FROM empresas
UNION ALL SELECT 'transportistas', count(*) FROM transportistas
UNION ALL SELECT 'reglas_sla', count(*) FROM reglas_sla
UNION ALL SELECT 'lotes_auditoria', count(*) FROM lotes_auditoria
UNION ALL SELECT 'envios', count(*) FROM envios;

\qecho ''
\qecho '3. Reglas SLA activas por transportista'
SELECT t.nombre AS transportista,
       s.horas_habiles_maximas AS plazo_horas_habiles,
       s.multa_por_incumplimiento AS multa_por_guia
FROM reglas_sla s
JOIN transportistas t ON t.id = s.transportista_id
WHERE s.activa
ORDER BY t.nombre;

\qecho ''
\qecho '4. Lotes auditados'
SELECT l.nombre_archivo, e.nombre AS empresa, l.estado, l.total_filas,
       to_char(l.fecha_corte, 'DD-MM-YYYY HH24:MI') AS fecha_corte
FROM lotes_auditoria l
JOIN empresas e ON e.id = l.empresa_id
ORDER BY l.fecha_creacion;

-- Las consultas 5 a 8 usan el lote más reciente de la planilla de julio.
\qecho ''
\qecho '5. Resultado de las guías (planilla de julio)'
WITH lote AS (
    SELECT id FROM lotes_auditoria
    WHERE nombre_archivo = 'envios_julio_2026.csv'
    ORDER BY fecha_creacion DESC LIMIT 1
)
SELECT resultado, count(*) AS guias, coalesce(sum(monto_multa), 0) AS multas
FROM envios
WHERE lote_auditoria_id = (SELECT id FROM lote)
GROUP BY resultado
ORDER BY guias DESC;

\qecho ''
\qecho '6. Cumplimiento y total por reclamar (planilla de julio)'
WITH lote AS (
    SELECT id FROM lotes_auditoria
    WHERE nombre_archivo = 'envios_julio_2026.csv'
    ORDER BY fecha_creacion DESC LIMIT 1
)
SELECT count(*) FILTER (WHERE resultado IN ('CUMPLIDO', 'INCUMPLIDO')) AS guias_auditables,
       count(*) FILTER (WHERE resultado = 'INCUMPLIDO') AS fuera_de_plazo,
       round(100.0 * count(*) FILTER (WHERE resultado = 'CUMPLIDO')
             / nullif(count(*) FILTER (WHERE resultado IN ('CUMPLIDO', 'INCUMPLIDO')), 0), 1)
           AS cumplimiento_pct,
       coalesce(sum(monto_multa), 0) AS total_por_reclamar
FROM envios
WHERE lote_auditoria_id = (SELECT id FROM lote);

\qecho ''
\qecho '7. Multas por transportista (planilla de julio)'
WITH lote AS (
    SELECT id FROM lotes_auditoria
    WHERE nombre_archivo = 'envios_julio_2026.csv'
    ORDER BY fecha_creacion DESC LIMIT 1
)
SELECT t.nombre AS transportista,
       count(*) AS guias_fuera_de_plazo,
       sum(e.monto_multa) AS multas
FROM envios e
JOIN transportistas t ON t.id = e.transportista_id
WHERE e.lote_auditoria_id = (SELECT id FROM lote) AND e.resultado = 'INCUMPLIDO'
GROUP BY t.nombre
ORDER BY multas DESC;

\qecho ''
\qecho '8. Justificación de una guía: LSA-2026J0022 (Blue Express)'
WITH lote AS (
    SELECT id FROM lotes_auditoria
    WHERE nombre_archivo = 'envios_julio_2026.csv'
    ORDER BY fecha_creacion DESC LIMIT 1
)
SELECT numero_guia,
       to_char(fecha_despacho, 'DD-MM-YYYY HH24:MI') AS despacho,
       to_char(fecha_limite, 'DD-MM-YYYY HH24:MI') AS fecha_limite,
       to_char(fecha_entrega, 'DD-MM-YYYY HH24:MI') AS entrega,
       round(horas_habiles_transcurridas::numeric, 2) AS horas_habiles,
       round(horas_atraso::numeric, 2) AS horas_atraso,
       monto_multa, resultado
FROM envios
WHERE lote_auditoria_id = (SELECT id FROM lote) AND numero_guia = 'LSA-2026J0022';

\qecho ''
\qecho '9. Integridad referencial: las tres cifras deben ser 0'
SELECT
    (SELECT count(*) FROM envios e
      WHERE NOT EXISTS (SELECT 1 FROM lotes_auditoria l WHERE l.id = e.lote_auditoria_id))
        AS envios_sin_lote,
    (SELECT count(*) FROM envios
      WHERE resultado = 'INCUMPLIDO' AND (monto_multa IS NULL OR monto_multa <= 0))
        AS incumplidas_sin_multa,
    (SELECT count(*) FROM envios
      WHERE resultado IN ('CUMPLIDO', 'EN_TRANSITO', 'VENCIDA_SIN_ENTREGA') AND coalesce(monto_multa, 0) > 0)
        AS multas_indebidas;
