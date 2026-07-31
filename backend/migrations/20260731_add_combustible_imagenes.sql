-- Migracion revisable para MySQL. No ejecutar sin inspeccion y backup previos.
-- Es idempotente: aplicada dos veces produce el mismo estado.
--
-- Esta migracion:
--   1) Crea la tabla combustible_imagenes con FK a movimientocombustible(id).
--   2) Crea los indices (PK, FK index, ix_expires_at, uq_token_hash).
--   3) Inserta el proveedor INTERNO FORESTAL PARAGUAY (id auto, no pisa id=1).
--      El id lo asigna la DB; el backend lo resuelve por nombre con
--      get_internal_provider_id() (ver backend/models.py, issue #16).
--      El id=1 historico (PROVEEDOR GENERICO, presente en 815 movimientos
--      de combustible previos) NO se toca.
--
-- El script de verificacion (read-only) chequea que la tabla existe, que
-- los indices/FK son correctos, y que existe un proveedor con
-- razon_social conteniendo 'INTERNO' (case-insensitive).

DELIMITER $$

DROP PROCEDURE IF EXISTS migrate_combustible_imagenes$$
CREATE PROCEDURE migrate_combustible_imagenes()
BEGIN
    DECLARE fk_exists INT DEFAULT 0;
    DECLARE named_index_exists INT DEFAULT 0;
    DECLARE named_index_correct INT DEFAULT 0;
    DECLARE exact_index_exists INT DEFAULT 0;
    DECLARE unique_named_exists INT DEFAULT 0;
    DECLARE unique_named_correct INT DEFAULT 0;
    DECLARE unique_exact_exists INT DEFAULT 0;
    DECLARE duplicate_token_groups INT DEFAULT 0;
    DECLARE interno_count INT DEFAULT 0;

    -- 1) Insert idempotente del proveedor INTERNO. La columna razon_social
    -- tiene UNIQUE; INSERT IGNORE salta el duplicado sin error si ya existe.
    INSERT IGNORE INTO proveedor (razon_social, activo, observaciones)
    VALUES ('INTERNO FORESTAL PARAGUAY', 1,
            'Reservado para movimientos internos de combustible (OCR). Creado por migracion 20260731_add_combustible_imagenes.sql.');

    -- 2) Tabla de evidencia
    CREATE TABLE IF NOT EXISTS combustible_imagenes (
        id INT NOT NULL AUTO_INCREMENT,
        movimiento_id INT NOT NULL,
        storage_path VARCHAR(500) NOT NULL,
        original_name VARCHAR(255) NOT NULL,
        mime_type VARCHAR(100) NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        token_hash VARCHAR(64) NOT NULL,
        created_at DATETIME NOT NULL,
        expires_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        KEY ix_combustible_imagenes_movimiento_id (movimiento_id),
        KEY ix_combustible_imagenes_sha256 (sha256),
        KEY ix_combustible_imagenes_expires_at (expires_at),
        UNIQUE KEY uq_combustible_imagenes_token_hash (token_hash),
        CONSTRAINT fk_combustible_imagenes_movimiento
            FOREIGN KEY (movimiento_id) REFERENCES movimientocombustible (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    -- 3) Idempotencia del indice expires_at (mismo patron que trip_image_ocr).
    SELECT COUNT(*), COALESCE(MAX(index_columns = 'expires_at' AND non_unique = 1), 0)
      INTO named_index_exists, named_index_correct
      FROM (
          SELECT INDEX_NAME, NON_UNIQUE AS non_unique,
                 GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
            FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = 'combustible_imagenes'
           GROUP BY INDEX_NAME, NON_UNIQUE
      ) AS index_definitions
     WHERE INDEX_NAME = 'ix_combustible_imagenes_expires_at';
    IF named_index_exists > 0 AND named_index_correct = 0 THEN
        ALTER TABLE combustible_imagenes
            DROP INDEX ix_combustible_imagenes_expires_at;
    END IF;

    SELECT COUNT(*) INTO exact_index_exists
      FROM (
          SELECT NON_UNIQUE,
                 GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
            FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = 'combustible_imagenes'
           GROUP BY INDEX_NAME, NON_UNIQUE
      ) AS index_definitions
     WHERE index_columns = 'expires_at'
       AND NON_UNIQUE = 1;
    IF exact_index_exists = 0 THEN
        ALTER TABLE combustible_imagenes
            ADD INDEX ix_combustible_imagenes_expires_at (expires_at);
    END IF;

    -- 4) Antes de crear el UNIQUE sobre token_hash, verificar duplicados.
    IF EXISTS (
        SELECT 1
          FROM information_schema.TABLES
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'combustible_imagenes'
    ) THEN
        SELECT COUNT(*) INTO duplicate_token_groups
          FROM (
              SELECT token_hash
               FROM combustible_imagenes
               WHERE token_hash IS NOT NULL
               GROUP BY token_hash
              HAVING COUNT(*) > 1
          ) AS duplicate_tokens;

        IF duplicate_token_groups > 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Migracion detenida: combustible_imagenes contiene token_hash duplicados; depure los duplicados antes de crear el indice unico';
        END IF;
    END IF;

    -- 5) Idempotencia del UNIQUE token_hash.
    SELECT COUNT(*), COALESCE(MAX(index_columns = 'token_hash' AND non_unique = 0), 0)
      INTO unique_named_exists, unique_named_correct
      FROM (
          SELECT INDEX_NAME, NON_UNIQUE AS non_unique,
                 GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
            FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = 'combustible_imagenes'
           GROUP BY INDEX_NAME, NON_UNIQUE
      ) AS index_definitions
     WHERE INDEX_NAME = 'uq_combustible_imagenes_token_hash';
    IF unique_named_exists > 0 AND unique_named_correct = 0 THEN
        ALTER TABLE combustible_imagenes
            DROP INDEX uq_combustible_imagenes_token_hash;
    END IF;

    SELECT COUNT(*) INTO unique_exact_exists
      FROM (
          SELECT NON_UNIQUE,
                 GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS index_columns
            FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = 'combustible_imagenes'
           GROUP BY INDEX_NAME, NON_UNIQUE
      ) AS index_definitions
     WHERE index_columns = 'token_hash'
       AND NON_UNIQUE = 0;
    IF unique_exact_exists = 0 THEN
        ALTER TABLE combustible_imagenes
            ADD UNIQUE INDEX uq_combustible_imagenes_token_hash (token_hash);
    END IF;

    -- 6) Re-chequear la FK por si una corrida previa quedo sin ella.
    SELECT COUNT(*) INTO fk_exists
      FROM information_schema.KEY_COLUMN_USAGE
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'combustible_imagenes'
       AND COLUMN_NAME = 'movimiento_id'
       AND REFERENCED_TABLE_NAME = 'movimientocombustible'
       AND REFERENCED_COLUMN_NAME = 'id';
    IF fk_exists = 0 THEN
        ALTER TABLE combustible_imagenes
            ADD CONSTRAINT fk_combustible_imagenes_movimiento
            FOREIGN KEY (movimiento_id) REFERENCES movimientocombustible (id);
    END IF;

    -- 7) Validar la convencion: debe existir un proveedor con
    -- razon_social que contenga 'INTERNO' (case-insensitive).
    SELECT COUNT(*) INTO interno_count
      FROM proveedor
     WHERE LOWER(razon_social) LIKE '%interno%';
    IF interno_count = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Migracion incompleta: no quedo ningun proveedor con razon_social conteniendo INTERNO. Revisar el INSERT IGNORE de arriba.';
    END IF;
END$$

CALL migrate_combustible_imagenes()$$
DROP PROCEDURE migrate_combustible_imagenes$$

DELIMITER ;
