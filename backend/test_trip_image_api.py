import sys
import unittest
from pathlib import Path


class TripImageModelMetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        backend_dir = Path(__file__).resolve().parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        import models

        cls.models = models

    def test_modelo_declara_pesaje_unico_cliente_nullable_y_evidencia(self):
        tablero = self.models.TableroProduccion.__table__
        self.assertIn("pesaje_unico", tablero.columns)
        self.assertTrue(tablero.columns.cliente_id.nullable)

        evidencia = self.models.ViajeImagen.__table__
        self.assertTrue(evidencia.columns.token_hash.unique)
        self.assertIn("expires_at", evidencia.columns)

    def test_migracion_repara_indices_con_definicion_exacta(self):
        migration = (
            Path(__file__).resolve().parent
            / "migrations"
            / "20260713_add_trip_image_ocr.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)", migration)
        self.assertIn("index_columns = 'expires_at'", migration)
        self.assertIn("index_columns = 'token_hash'", migration)
        self.assertIn("DROP INDEX ix_viaje_imagenes_expires_at", migration)
        self.assertIn("DROP INDEX uq_viaje_imagenes_token_hash", migration)

    def test_verificacion_muestra_definicion_completa_de_cada_indice(self):
        verification = (
            Path(__file__).resolve().parent
            / "migrations"
            / "20260713_verify_trip_image_ocr.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)", verification)
        self.assertNotIn("COLUMN_NAME IN ('expires_at', 'token_hash')", verification)

    def test_preflight_de_duplicados_antecede_ddl_destructivo_del_token(self):
        migration = (
            Path(__file__).resolve().parent
            / "migrations"
            / "20260713_add_trip_image_ocr.sql"
        ).read_text(encoding="utf-8")

        duplicate_query = "HAVING COUNT(*) > 1"
        signal = "SIGNAL SQLSTATE '45000'"
        drop_token_index = "DROP INDEX uq_viaje_imagenes_token_hash"
        add_unique_token = "ADD UNIQUE INDEX uq_viaje_imagenes_token_hash"

        for required in (duplicate_query, signal, drop_token_index, add_unique_token):
            self.assertIn(required, migration)
        self.assertLess(migration.index(duplicate_query), migration.index(signal))
        self.assertLess(migration.index(signal), migration.index(drop_token_index))
        self.assertLess(migration.index(signal), migration.index(add_unique_token))


if __name__ == "__main__":
    unittest.main()
