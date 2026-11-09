import re
import sys
import unittest
from pathlib import Path

MIGRACIONES_DIR = Path(__file__).resolve().parent / "migrations"

# Verbos que no pueden aparecer en el script de verificacion: es de solo lectura.
VERBOS_ESCRITURA = (
    "INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE", "TRUNCATE",
    "REPLACE", "RENAME", "GRANT", "REVOKE", "CALL", "SET", "LOCK", "UNLOCK",
    "LOAD", "COMMIT", "ROLLBACK",
)


def sin_comentarios(sql):
    """Quita los comentarios de linea.

    Asi el chequeo no se rompe por una palabra que aparece en un comentario
    (por ejemplo 'created' o 'update') y no cuenta como operacion SQL.
    """
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


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
        # El default existe tambien del lado del motor: un esquema creado desde
        # el ORM (SQLite de desarrollo, entorno nuevo) no queda NOT NULL sin default.
        self.assertIsNotNone(columna.server_default)
        self.assertEqual(columna.server_default.arg, "km")
        self.assertIsInstance(columna.type, self.models.String)
        self.assertEqual(columna.type.length, 3)

    def test_tablero_produccion_declara_lectura_camion_nullable(self):
        columna = self.models.TableroProduccion.__table__.columns["lectura_camion"]
        self.assertTrue(columna.nullable)
        self.assertIsInstance(columna.type, self.models.DECIMAL)
        self.assertEqual(columna.type.precision, 10)
        self.assertEqual(columna.type.scale, 2)

    def test_tablero_produccion_declara_unidad_lectura_nullable(self):
        columna = self.models.TableroProduccion.__table__.columns["unidad_lectura"]
        self.assertTrue(columna.nullable)
        self.assertIsInstance(columna.type, self.models.String)
        self.assertEqual(columna.type.length, 3)

    def test_hr_inicio_y_hr_fin_no_cambian_de_semantica(self):
        tablero = self.models.TableroProduccion.__table__
        for nombre in ("hr_inicio", "hr_fin"):
            columna = tablero.columns[nombre]
            self.assertTrue(columna.nullable is False)
            # El tipo tambien es intocable: son flotantes, no texto ni decimales.
            self.assertIsInstance(columna.type, self.models.Float)


class LecturaCamionEsquemaRealTest(unittest.TestCase):
    """Prueba funcional sobre el esquema real que crea el ORM."""

    @classmethod
    def setUpClass(cls):
        backend_dir = Path(__file__).resolve().parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        import models

        cls.models = models

    def setUp(self):
        from sqlalchemy import create_engine, inspect
        from sqlalchemy.orm import sessionmaker

        self.engine = create_engine("sqlite:///:memory:")
        self.models.Base.metadata.create_all(self.engine)
        self.inspector = inspect(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_el_esquema_real_expone_las_tres_columnas_nuevas(self):
        equipos = {c["name"]: c for c in self.inspector.get_columns("equipos")}
        tablero = {c["name"]: c for c in self.inspector.get_columns("tablero_produccion")}

        self.assertIn("unidad_hr_km", equipos)
        self.assertFalse(equipos["unidad_hr_km"]["nullable"])
        self.assertIn("lectura_camion", tablero)
        self.assertTrue(tablero["lectura_camion"]["nullable"])
        self.assertIn("unidad_lectura", tablero)
        self.assertTrue(tablero["unidad_lectura"]["nullable"])

    def test_el_orm_puede_insertar_un_equipo_sin_indicar_la_unidad(self):
        equipo = self.models.Equipo(
            descripcion="Scania",
            patente="ABC123",
            nro_chasis="CH10",
            nro_motor="MO10",
            tipo_movil_id=1,
            movil_asociado=0,
            activo=True,
        )
        self.db.add(equipo)
        self.db.commit()
        self.db.refresh(equipo)

        self.assertEqual(equipo.unidad_hr_km, "km")


class LecturaCamionMigracionTest(unittest.TestCase):
    def _sql_migracion(self):
        return (MIGRACIONES_DIR / "20261109_add_lectura_camion.sql").read_text(encoding="utf-8")

    def _sql_verificacion(self):
        return (MIGRACIONES_DIR / "20261109_verify_lectura_camion.sql").read_text(encoding="utf-8")

    def test_migracion_es_idempotente_y_tiene_las_tres_columnas(self):
        sql = self._sql_migracion()

        self.assertIn("ADD COLUMN lectura_camion DECIMAL(10, 2) NULL", sql)
        self.assertIn("ADD COLUMN unidad_lectura VARCHAR(3) NULL", sql)
        self.assertIn("ADD COLUMN unidad_hr_km VARCHAR(3) NOT NULL DEFAULT 'km'", sql)

        cuerpo = sin_comentarios(sql)
        # Las tres columnas se agregan solo si no existen, y solo esas tres.
        self.assertEqual(cuerpo.count("IF NOT EXISTS"), 3)
        self.assertEqual(cuerpo.count("ADD COLUMN"), 3)

    def test_migracion_no_toca_el_par_de_tramo_del_carreton(self):
        cuerpo = sin_comentarios(self._sql_migracion())

        # hr_inicio/hr_fin son el par de tramo del flujo de carreton: esta
        # migracion no los renombra, no los altera y no los borra.
        self.assertNotIn("hr_inicio", cuerpo)
        self.assertNotIn("hr_fin", cuerpo)
        self.assertNotIn("MODIFY", cuerpo.upper())
        self.assertNotIn("CHANGE COLUMN", cuerpo.upper())
        self.assertNotIn("DROP COLUMN", cuerpo.upper())

    def test_script_de_verificacion_es_solo_lectura(self):
        cuerpo = sin_comentarios(self._sql_verificacion())

        for verbo in VERBOS_ESCRITURA:
            self.assertIsNone(
                re.search(rf"\b{verbo}\b", cuerpo.upper()),
                f"El script de verificacion no debe ejecutar {verbo}",
            )

        # Ademas, todas las sentencias son SELECT.
        sentencias = [s.strip() for s in cuerpo.split(";") if s.strip()]
        self.assertTrue(sentencias, "El script de verificacion no tiene sentencias")
        for sentencia in sentencias:
            self.assertTrue(
                sentencia.upper().startswith("SELECT"),
                f"El script de verificacion solo puede ejecutar SELECT: {sentencia[:60]}",
            )

    def test_script_de_verificacion_controla_el_dominio_de_la_unidad_lectura(self):
        cuerpo = sin_comentarios(self._sql_verificacion()).upper()
        compacto = cuerpo.replace(" ", "")

        # La unidad grabada en cada viaje tiene que ser 'km' o 'hs'.
        self.assertIn("UNIDAD_LECTURA", cuerpo)
        self.assertIn("UNIDAD_LECTURANOTIN('KM','HS')", compacto)
        # Y tiene que ser coherente con la lectura: no hay lectura sin unidad
        # ni unidad sin lectura.
        self.assertIn("LECTURA_CAMIONISNOTNULL", compacto)
        self.assertIn("LECTURA_CAMIONISNULLANDUNIDAD_LECTURAISNOTNULL", compacto)


if __name__ == "__main__":
    unittest.main()
