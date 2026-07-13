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


if __name__ == "__main__":
    unittest.main()
