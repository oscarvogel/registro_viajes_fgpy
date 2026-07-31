-- Consultas de solo lectura para verificar la migracion de evidencia OCR
-- de combustible. Lee el esquema, los indices, la FK y la convencion del
-- proveedor INTERNO (buscado por nombre, no por id hardcodeado).

-- 1) Estructura basica de la tabla
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'combustible_imagenes';

-- 2) Columnas con tipo y nullability
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'combustible_imagenes'
ORDER BY ORDINAL_POSITION;

-- 3) Indices (PK, FK index, UNIQUE, expires_at)
SELECT INDEX_NAME,
       NON_UNIQUE,
       COUNT(*) AS column_count,
       MIN(SEQ_IN_INDEX) AS first_position,
       MAX(SEQ_IN_INDEX) AS last_position,
       GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'combustible_imagenes'
GROUP BY INDEX_NAME, NON_UNIQUE
ORDER BY INDEX_NAME;

-- 4) Foreign keys
SELECT CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'combustible_imagenes'
  AND REFERENCED_TABLE_NAME IS NOT NULL;

-- 5) Convencion del proyecto: debe existir al menos un proveedor con
-- razon_social que contenga 'INTERNO' (case-insensitive). El id lo
-- asigna la DB; el backend lo resuelve por nombre con
-- get_internal_provider_id() (ver backend/models.py, issue #16).
-- Esta consulta debe devolver al menos una fila. Documentar el id
-- resultante en el README del deploy para referencia operativa.
SELECT id, razon_social, activo, observaciones
FROM proveedor
WHERE LOWER(razon_social) LIKE '%interno%';
