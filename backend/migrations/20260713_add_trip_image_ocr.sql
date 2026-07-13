-- Migracion revisable para MySQL. No ejecutar sin inspeccion y backup previos.
-- Es idempotente y conserva el COLUMN_TYPE real de tablero_produccion.cliente_id.

DELIMITER $$

DROP PROCEDURE IF EXISTS migrate_trip_image_ocr$$
CREATE PROCEDURE migrate_trip_image_ocr()
BEGIN
    DECLARE cliente_column_type TEXT;
    DECLARE cliente_is_nullable VARCHAR(3);
    DECLARE fk_exists INT DEFAULT 0;
    DECLARE named_index_exists INT DEFAULT 0;
    DECLARE named_index_correct INT DEFAULT 0;
    DECLARE exact_index_exists INT DEFAULT 0;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'tablero_produccion'
          AND COLUMN_NAME = 'pesaje_unico'
    ) THEN
        ALTER TABLE tablero_produccion
            ADD COLUMN pesaje_unico TINYINT(1) NOT NULL DEFAULT 0;
    END IF;

    SELECT COLUMN_TYPE, IS_NULLABLE
      INTO cliente_column_type, cliente_is_nullable
      FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'tablero_produccion'
       AND COLUMN_NAME = 'cliente_id'
     LIMIT 1;

    IF cliente_column_type IS NOT NULL AND cliente_is_nullable = 'NO' THEN
        SET @alter_cliente_sql = CONCAT(
            'ALTER TABLE tablero_produccion MODIFY COLUMN cliente_id ',
            cliente_column_type,
            ' NULL'
        );
        PREPARE alter_cliente_stmt FROM @alter_cliente_sql;
        EXECUTE alter_cliente_stmt;
        DEALLOCATE PREPARE alter_cliente_stmt;
    END IF;

    CREATE TABLE IF NOT EXISTS viaje_imagenes (
        id INT NOT NULL AUTO_INCREMENT,
        viaje_id INT NOT NULL,
        storage_path VARCHAR(500) NOT NULL,
        original_name VARCHAR(255) NOT NULL,
        mime_type VARCHAR(100) NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        token_hash VARCHAR(64) NOT NULL,
        created_at DATETIME NOT NULL,
        expires_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        KEY ix_viaje_imagenes_viaje_id (viaje_id),
        KEY ix_viaje_imagenes_sha256 (sha256),
        KEY ix_viaje_imagenes_expires_at (expires_at),
        UNIQUE KEY uq_viaje_imagenes_token_hash (token_hash),
        CONSTRAINT fk_viaje_imagenes_viaje
            FOREIGN KEY (viaje_id) REFERENCES tablero_produccion (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    SELECT COUNT(*), COALESCE(MAX(index_columns = 'expires_at' AND non_unique = 1), 0)
      INTO named_index_exists, named_index_correct
      FROM (
          SELECT INDEX_NAME, NON_UNIQUE AS non_unique,
                 GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
            FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = 'viaje_imagenes'
           GROUP BY INDEX_NAME, NON_UNIQUE
      ) AS index_definitions
     WHERE INDEX_NAME = 'ix_viaje_imagenes_expires_at';
    IF named_index_exists > 0 AND named_index_correct = 0 THEN
        ALTER TABLE viaje_imagenes
            DROP INDEX ix_viaje_imagenes_expires_at;
    END IF;

    SELECT COUNT(*) INTO exact_index_exists
      FROM (
          SELECT NON_UNIQUE,
                 GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
            FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = 'viaje_imagenes'
           GROUP BY INDEX_NAME, NON_UNIQUE
      ) AS index_definitions
     WHERE index_columns = 'expires_at'
       AND NON_UNIQUE = 1;
    IF exact_index_exists = 0 THEN
        ALTER TABLE viaje_imagenes
            ADD INDEX ix_viaje_imagenes_expires_at (expires_at);
    END IF;

    SELECT COUNT(*), COALESCE(MAX(index_columns = 'token_hash' AND non_unique = 0), 0)
      INTO named_index_exists, named_index_correct
      FROM (
          SELECT INDEX_NAME, NON_UNIQUE AS non_unique,
                 GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
            FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = 'viaje_imagenes'
           GROUP BY INDEX_NAME, NON_UNIQUE
      ) AS index_definitions
     WHERE INDEX_NAME = 'uq_viaje_imagenes_token_hash';
    IF named_index_exists > 0 AND named_index_correct = 0 THEN
        ALTER TABLE viaje_imagenes
            DROP INDEX uq_viaje_imagenes_token_hash;
    END IF;

    SELECT COUNT(*) INTO exact_index_exists
      FROM (
          SELECT NON_UNIQUE,
                 GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
            FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = 'viaje_imagenes'
           GROUP BY INDEX_NAME, NON_UNIQUE
      ) AS index_definitions
     WHERE index_columns = 'token_hash'
       AND NON_UNIQUE = 0;
    IF exact_index_exists = 0 THEN
        ALTER TABLE viaje_imagenes
            ADD UNIQUE INDEX uq_viaje_imagenes_token_hash (token_hash);
    END IF;

    SELECT COUNT(*) INTO fk_exists
      FROM information_schema.KEY_COLUMN_USAGE
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'viaje_imagenes'
       AND COLUMN_NAME = 'viaje_id'
       AND REFERENCED_TABLE_NAME = 'tablero_produccion'
       AND REFERENCED_COLUMN_NAME = 'id';
    IF fk_exists = 0 THEN
        ALTER TABLE viaje_imagenes
            ADD CONSTRAINT fk_viaje_imagenes_viaje
            FOREIGN KEY (viaje_id) REFERENCES tablero_produccion (id);
    END IF;
END$$

CALL migrate_trip_image_ocr()$$
DROP PROCEDURE migrate_trip_image_ocr$$

DELIMITER ;
