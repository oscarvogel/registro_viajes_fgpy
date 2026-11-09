-- Agrega la lectura de km/horas del camion a los viajes normales.
-- Migracion idempotente: solo altera si la columna no existe.
-- Revisar y hacer backup antes de ejecutar (ver README).
-- Aplicar ANTES de desplegar el backend nuevo: este selecciona las columnas.

DELIMITER $$

DROP PROCEDURE IF EXISTS migrate_lectura_camion$$
CREATE PROCEDURE migrate_lectura_camion()
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'tablero_produccion'
           AND COLUMN_NAME = 'lectura_camion'
    ) THEN
        ALTER TABLE tablero_produccion
            ADD COLUMN lectura_camion DECIMAL(10, 2) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'tablero_produccion'
           AND COLUMN_NAME = 'unidad_lectura'
    ) THEN
        ALTER TABLE tablero_produccion
            ADD COLUMN unidad_lectura VARCHAR(3) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'equipos'
           AND COLUMN_NAME = 'unidad_hr_km'
    ) THEN
        ALTER TABLE equipos
            ADD COLUMN unidad_hr_km VARCHAR(3) NOT NULL DEFAULT 'km';
    END IF;
END$$

CALL migrate_lectura_camion()$$
DROP PROCEDURE migrate_lectura_camion$$

DELIMITER ;
