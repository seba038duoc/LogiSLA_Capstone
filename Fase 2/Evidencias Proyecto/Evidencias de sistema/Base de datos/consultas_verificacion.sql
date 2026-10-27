-- =============================================================================
-- LogiSLA · Consultas de verificación para PostgreSQL 16
-- Ejecutar después de schema.sql y datos_prueba.sql:
--   psql -U logisla -d logisla -f consultas_verificacion.sql
--
-- Cada consulta indica el resultado esperado con los datos de prueba.
-- =============================================================================

\echo '1. Cantidad de filas por tabla (esperado: 1 empresa, 4 transportistas, 4 reglas, 1 lote, 60 envíos)'
SELECT 'empresas' AS tabla, COUNT(*) AS filas FROM empresas
UNION ALL SELECT 'transportistas', COUNT(*) FROM transportistas
UNION ALL SELECT 'reglas_sla', COUNT(*) FROM reglas_sla
UNION ALL SELECT 'lotes_auditoria', COUNT(*) FROM lotes_auditoria
UNION ALL SELECT 'envios', COUNT(*) FROM envios;

\echo '2. Integridad referencial: envíos sin lote o con transportista inexistente (esperado: 0 y 0)'
SELECT
    (SELECT COUNT(*) FROM envios e LEFT JOIN lotes_auditoria l ON l.id = e.lote_auditoria_id WHERE l.id IS NULL) AS envios_sin_lote,
    (SELECT COUNT(*) FROM envios e LEFT JOIN transportistas t ON t.id = e.transportista_id
      WHERE e.transportista_id IS NOT NULL AND t.id IS NULL) AS envios_con_transportista_invalido;

\echo '3. Regla SLA activa de cada transportista (esperado: 4 filas, una por transportista)'
SELECT t.nombre AS transportista, r.horas_habiles_maximas, r.multa_por_incumplimiento, r.activa
FROM transportistas t
JOIN reglas_sla r ON r.transportista_id = t.id AND r.activa
ORDER BY t.nombre;

\echo '4. Clasificación de las guías del lote (esperado: 36 en plazo, 13 fuera de plazo, 11 en tránsito)'
SELECT
    CASE
        WHEN e.fecha_entrega IS NULL THEN 'EN_TRANSITO'
        WHEN e.incumplio_sla THEN 'FUERA_DE_PLAZO'
        WHEN e.incumplio_sla = FALSE THEN 'EN_PLAZO'
        ELSE 'SIN_REGLA'
    END AS resultado,
    COUNT(*) AS guias
FROM envios e
WHERE e.lote_auditoria_id = '00000000-0000-4000-8000-000000000201'
GROUP BY 1
ORDER BY 1;

\echo '5. Resumen del lote (esperado: 49 auditadas, 13 fuera de plazo, 73,5 % de cumplimiento, $170.000)'
SELECT
    COUNT(*) FILTER (WHERE incumplio_sla IS NOT NULL)                         AS guias_auditadas,
    COUNT(*) FILTER (WHERE incumplio_sla)                                     AS fuera_de_plazo,
    ROUND(100.0 * COUNT(*) FILTER (WHERE incumplio_sla = FALSE)
          / NULLIF(COUNT(*) FILTER (WHERE incumplio_sla IS NOT NULL), 0), 1)  AS cumplimiento_pct,
    COALESCE(SUM(monto_multa), 0)                                             AS multa_total
FROM envios
WHERE lote_auditoria_id = '00000000-0000-4000-8000-000000000201';

\echo '6. Desglose por transportista (esperado: Starken 5 / $60.000, Chilexpress 4 / $60.000, Blue Express 2 / $30.000, Correos de Chile 2 / $20.000)'
SELECT
    t.nombre                                      AS transportista,
    COUNT(*)                                      AS guias,
    COUNT(*) FILTER (WHERE e.incumplio_sla)       AS fuera_de_plazo,
    COALESCE(SUM(e.monto_multa), 0)               AS multa
FROM envios e
JOIN transportistas t ON t.id = e.transportista_id
WHERE e.lote_auditoria_id = '00000000-0000-4000-8000-000000000201'
GROUP BY t.nombre
ORDER BY multa DESC, t.nombre;

\echo '7. Coherencia del cálculo: multa y atraso según la regla SLA (esperado: 0 filas inconsistentes)'
SELECT e.numero_guia, t.nombre, e.incumplio_sla, e.horas_atraso, e.monto_multa
FROM envios e
JOIN transportistas t ON t.id = e.transportista_id
JOIN reglas_sla r ON r.transportista_id = t.id AND r.activa
WHERE e.incumplio_sla IS NOT NULL
  AND (
        (e.incumplio_sla       AND (e.horas_atraso <= 0 OR e.monto_multa <> r.multa_por_incumplimiento))
     OR (NOT e.incumplio_sla   AND (e.horas_atraso <> 0 OR e.monto_multa <> 0))
  );

\echo '8. Guías en tránsito no deben tener resultado (esperado: 0)'
SELECT COUNT(*) AS en_transito_con_resultado
FROM envios
WHERE fecha_entrega IS NULL
  AND (incumplio_sla IS NOT NULL OR horas_atraso IS NOT NULL OR monto_multa IS NOT NULL);

\echo '9. Restricciones únicas: RUT de empresa y nombre de transportista duplicados (esperado: ERROR por clave duplicada)'
\set ON_ERROR_STOP off
INSERT INTO transportistas (nombre) VALUES ('Starken');
INSERT INTO empresas (nombre, rut) VALUES ('Duplicada SpA', '76.987.654-3');
\set ON_ERROR_STOP on

\echo '10. Guías fuera de plazo con mayor atraso (detalle para la carta de reclamo)'
SELECT e.numero_guia, t.nombre AS transportista, e.destino, e.horas_atraso, e.monto_multa
FROM envios e
JOIN transportistas t ON t.id = e.transportista_id
WHERE e.incumplio_sla
ORDER BY e.horas_atraso DESC, e.numero_guia
LIMIT 5;
