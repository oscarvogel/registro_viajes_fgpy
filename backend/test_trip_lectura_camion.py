import sys
import unittest
from pathlib import Path


class LecturaCamionModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        backend_dir = Path(__file__).resolve().parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        import models

        cls.models = models

    def test_equipos_declara_unidad_hr_km_por_defecto_km(self):
        columna = self.models.Equipo.__table__.columns["unidad_hr_km"]
        self.assertFalse(columna.nullable)
        self.assertEqual(columna.default.arg, "km")

    def test_tablero_produccion_declara_lectura_camion_nullable(self):
        columna = self.models.TableroProduccion.__table__.columns["lectura_camion"]
        self.assertTrue(columna.nullable)

    def test_tablero_produccion_declara_unidad_lectura_nullable(self):
        columna = self.models.TableroProduccion.__table__.columns["unidad_lectura"]
        self.assertTrue(columna.nullable)

    def test_hr_inicio_y_hr_fin_no_cambian_de_semantica(self):
        tablero = self.models.TableroProduccion.__table__
        self.assertTrue(tablero.columns["hr_inicio"].nullable is False)
        self.assertTrue(tablero.columns["hr_fin"].nullable is False)


class LecturaCamionMigracionTest(unittest.TestCase):
    def test_migracion_es_idempotente_y_tiene_las_tres_columnas(self):
        sql = (Path(__file__).resolve().parent / "migrations" / "20261109_add_lectura_camion.sql").read_text(encoding="utf-8")

        self.assertIn("ADD COLUMN lectura_camion DECIMAL(10, 2) NULL", sql)
        self.assertIn("ADD COLUMN unidad_lectura VARCHAR(3) NULL", sql)
        self.assertIn("ADD COLUMN unidad_hr_km VARCHAR(3) NOT NULL DEFAULT 'km'", sql)
        # Las tres columnas se agregan solo si no existen.
        self.assertEqual(sql.count("IF NOT EXISTS"), 3)
        # Nunca se hace DROP de hr_inicio/hr_fin.
        self.assertNotIn("DROP COLUMN", sql)

    def test_script_de_verificacion_es_solo_lectura(self):
        sql = (Path(__file__).resolve().parent / "migrations" / "20261109_verify_lectura_camion.sql").read_text(encoding="utf-8")

        for verbo in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE"):
            self.assertNotIn(verbo, sql.upper(), f"El script de verificacion no debe ejecutar {verbo}")


if __name__ == "__main__":
    unittest.main()
