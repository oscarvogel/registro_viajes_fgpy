-- Verificacion de solo lectura de la migracion de lectura de camion.
-- Debe mostrar: lectura_camion nullable DECIMAL, unidad_lectura nullable VARCHAR,
-- unidad_hr_km NOT NULL DEFAULT 'km', y cero filas con lectura no nula.

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COALESCE(COLUMN_DEFAULT, '<NULL>') AS default_value
  FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA = DATABASE()
   AND TABLE_NAME = 'tablero_produccion'
   AND COLUMN_NAME IN ('lectura_camion', 'unidad_lectura')
 ORDER BY COLUMN_NAME;

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COALESCE(COLUMN_DEFAULT, '<NULL>') AS default_value
  FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA = DATABASE()
   AND TABLE_NAME = 'equipos'
   AND COLUMN_NAME = 'unidad_hr_km';

SELECT COUNT(*) AS filas_con_lectura
  FROM tablero_produccion
 WHERE lectura_camion IS NOT NULL;

SELECT COUNT(*) AS equipos_sin_unidad
  FROM equipos
 WHERE unidad_hr_km IS NULL OR unidad_hr_km NOT IN ('km', 'hs');
