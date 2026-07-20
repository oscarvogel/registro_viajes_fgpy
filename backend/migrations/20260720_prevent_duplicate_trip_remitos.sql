-- Impide remitos duplicados incluso ante dos solicitudes simultaneas.
-- Revisar y hacer backup antes de ejecutar. La migracion se detiene sin
-- modificar filas duplicadas para que la depuracion sea una decision explicita.

DELIMITER $$

DROP PROCEDURE IF EXISTS prevent_duplicate_trip_remitos$$
CREATE PROCEDURE prevent_duplicate_trip_remitos()
BEGIN
    DECLARE duplicate_groups INT DEFAULT 0;
    DECLARE exact_unique_exists INT DEFAULT 0;

    -- MySQL permite multiples NULL en un indice unico. Los vacios representan
    -- "sin remito" y deben conservar esa misma semantica.
    UPDATE tablero_produccion
       SET remito_proveedor = NULLIF(TRIM(remito_proveedor), ''),
           remito_fgpy = NULLIF(TRIM(remito_fgpy), '');

    SELECT COUNT(*) INTO duplicate_groups
      FROM (
          SELECT remito_proveedor
            FROM tablero_produccion
           WHERE remito_proveedor IS NOT NULL
           GROUP BY remito_proveedor
          HAVING COUNT(*) > 1
      ) AS duplicate_provider_remitos;

    IF duplicate_groups > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Migracion detenida: hay remitos de proveedor duplicados; depurelos antes de crear el indice unico';
    END IF;

    SELECT COUNT(*) INTO duplicate_groups
      FROM (
          SELECT remito_fgpy
            FROM tablero_produccion
           WHERE remito_fgpy IS NOT NULL
           GROUP BY remito_fgpy
          HAVING COUNT(*) > 1
      ) AS duplicate_fgpy_remitos;

    IF duplicate_groups > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Migracion detenida: hay remitos FGPY duplicados; depurelos antes de crear el indice unico';
    END IF;

    SELECT COUNT(*) INTO exact_unique_exists
      FROM (
          SELECT NON_UNIQUE,
                 GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
            FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = 'tablero_produccion'
           GROUP BY INDEX_NAME, NON_UNIQUE
      ) AS index_definitions
     WHERE index_columns = 'remito_proveedor'
       AND NON_UNIQUE = 0;
    IF exact_unique_exists = 0 THEN
        ALTER TABLE tablero_produccion
            ADD UNIQUE INDEX uq_tablero_produccion_remito_proveedor (remito_proveedor);
    END IF;

    SELECT COUNT(*) INTO exact_unique_exists
      FROM (
          SELECT NON_UNIQUE,
                 GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
            FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = 'tablero_produccion'
           GROUP BY INDEX_NAME, NON_UNIQUE
      ) AS index_definitions
     WHERE index_columns = 'remito_fgpy'
       AND NON_UNIQUE = 0;
    IF exact_unique_exists = 0 THEN
        ALTER TABLE tablero_produccion
            ADD UNIQUE INDEX uq_tablero_produccion_remito_fgpy (remito_fgpy);
    END IF;
END$$

CALL prevent_duplicate_trip_remitos()$$
DROP PROCEDURE prevent_duplicate_trip_remitos$$

DELIMITER ;
