-- =====================================================================
-- LogiSLA - Datos de prueba (los mismos que carga iniciar.bat con
-- scripts/seed_carriers_and_rules.py y scripts/seed_pilot_company.py).
--
-- Uso (después de schema.sql):
--   psql -U postgres -d logisla -f datos_prueba.sql
-- Se puede ejecutar más de una vez: no duplica registros.
-- Los lotes y las guías no se cargan aquí: se crean al subir una planilla
-- (envios_piloto.csv o envios_julio_2026.csv) desde la aplicación.
-- =====================================================================

-- Empresa piloto (simulada).
INSERT INTO empresas (id, nombre)
SELECT gen_random_uuid(), 'Retail Piloto SpA'
WHERE NOT EXISTS (SELECT 1 FROM empresas WHERE nombre = 'Retail Piloto SpA');

-- Transportistas.
INSERT INTO transportistas (id, nombre) VALUES
    (gen_random_uuid(), 'Chilexpress'),
    (gen_random_uuid(), 'Starken'),
    (gen_random_uuid(), 'Correos de Chile'),
    (gen_random_uuid(), 'Blue Express')
ON CONFLICT (nombre) DO NOTHING;

-- Reglas SLA activas: plazo en horas hábiles y multa por guía fuera de plazo.
INSERT INTO reglas_sla (id, transportista_id, tipo_servicio, horas_habiles_maximas,
                        multa_por_incumplimiento, activa)
SELECT gen_random_uuid(), t.id, NULL, r.horas, r.multa, TRUE
FROM (VALUES
        ('Chilexpress',      48, 15000),
        ('Starken',          60, 12000),
        ('Correos de Chile', 72, 10000),
        ('Blue Express',     48, 15000)
     ) AS r (nombre, horas, multa)
JOIN transportistas t ON t.nombre = r.nombre
WHERE NOT EXISTS (
    SELECT 1 FROM reglas_sla s WHERE s.transportista_id = t.id AND s.activa
);
