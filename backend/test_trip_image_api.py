import sys
import types
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import tempfile

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


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
        self.assertIn("token_hash IS NOT NULL", migration)
        self.assertNotIn("token_hash <> ''", migration)
        self.assertLess(migration.index(duplicate_query), migration.index(signal))
        self.assertLess(migration.index(signal), migration.index(drop_token_index))
        self.assertLess(migration.index(signal), migration.index(add_unique_token))


class CreateTripServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        backend_dir = Path(__file__).resolve().parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        import models
        import schemas

        cls.models = models
        cls.schemas = schemas
        cls.engine = create_engine("sqlite:///:memory:")
        for table in (
            models.Empleado.__table__,
            models.Proveedor.__table__,
            models.Cliente.__table__,
            models.Equipo.__table__,
            models.UnidadNegocio.__table__,
            models.TableroProduccion.__table__,
        ):
            table.create(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        for model in (
            self.models.TableroProduccion,
            self.models.Equipo,
            self.models.UnidadNegocio,
            self.models.Proveedor,
            self.models.Cliente,
            self.models.Empleado,
        ):
            self.db.query(model).delete()
        self.db.commit()

        self.employee = self.models.Empleado(
            id=10, nombre="Ana", apellido="Perez", email="a@example.com",
            documento="123", fecha_contratacion=date(2020, 1, 1), activo=True,
            porcentaje=0,
        )
        self.provider = self.models.Proveedor(id=20, razon_social="Proveedor", activo=True)
        self.client = self.models.Cliente(id=1, razon_social="Cliente", activo=True)
        self.unit = self.models.UnidadNegocio(id=3, descripcion="Transporte", activo=True)
        self.equipment = self.models.Equipo(
            id=30, descripcion="Camion", patente="AA 123 BB", nro_chasis="c",
            nro_motor="m", tipo_movil_id=1, activo=True, movil_asociado=0, ult_hr_km=0,
        )
        self.db.add_all([self.employee, self.provider, self.client, self.unit, self.equipment])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def payload(self, **overrides):
        values = dict(
            fecha_remision=date(2026, 7, 13), fecha_recepcion=date(2026, 7, 13),
            proveedor_id=20, numero_remision="R-1", numero_remision_fpv="F-1",
            peso_bruto_origen=48.5, tara_origen=16.5, neto_origen=32.0,
            peso_bruto_destino=49.690, tara_destino=17.080, neto_destino=32.610,
            chofer_id=10, patente="aa123bb", unidad_negocio_id=3, cliente_id=1,
            observaciones="ok", pesaje_unico=False,
        )
        values.update(overrides)
        return self.schemas.RegistroViajeCreate(**values)

    def create_trip(self, registro, **kwargs):
        from trip_service import create_trip
        return create_trip(self.db, registro, self.employee, **kwargs)

    def assert_bad_request(self, **overrides):
        with self.assertRaises(HTTPException) as ctx:
            self.create_trip(self.payload(**overrides))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_pesaje_unico_guarda_destino_produccion_y_cliente_nulo(self):
        row = self.create_trip(self.payload(
            pesaje_unico=True, cliente_id=None, peso_bruto_origen=0,
            tara_origen=0, neto_origen=0,
        ))
        self.assertEqual(row.neto_origen, Decimal("0.00"))
        self.assertEqual(row.bruto_destino, Decimal("49.69"))
        self.assertEqual(row.tara_destino, Decimal("17.08"))
        self.assertEqual(row.neto_destino, Decimal("32.61"))
        self.assertEqual(row.produccion, Decimal("32.61"))
        self.assertTrue(row.pesaje_unico)
        self.assertIsNone(row.cliente_id)

    def test_normal_rechaza_origen_no_positivo_y_produce_desde_origen(self):
        self.assert_bad_request(neto_origen=0)
        row = self.create_trip(self.payload(numero_remision="R-2", numero_remision_fpv="F-2"))
        self.assertEqual(row.produccion, Decimal("32.00"))
        self.assertFalse(row.pesaje_unico)

    def test_normal_acepta_hasta_200_tn_y_rechaza_mas(self):
        row = self.create_trip(self.payload(
            neto_origen=150, neto_destino=150,
            peso_bruto_origen=180, tara_origen=30,
        ))
        self.assertEqual(row.produccion, Decimal("150.00"))
        self.assert_bad_request(
            numero_remision="R-2", numero_remision_fpv="F-2",
            neto_origen=201, neto_destino=150,
        )

    def test_pesaje_unico_rechaza_origen_no_cero(self):
        for field in ("peso_bruto_origen", "tara_origen", "neto_origen"):
            values = dict(pesaje_unico=True, cliente_id=None, peso_bruto_origen=0,
                          tara_origen=0, neto_origen=0)
            values[field] = 1
            self.assert_bad_request(**values)

    def test_pesaje_unico_rechaza_pesos_destino_invalidos(self):
        base = dict(pesaje_unico=True, cliente_id=None, peso_bruto_origen=0,
                    tara_origen=0, neto_origen=0)
        for changes in (
            {"neto_destino": 0}, {"peso_bruto_destino": -1},
            {"tara_destino": -1}, {"neto_destino": 81},
            {"peso_bruto_destino": 81}, {"tara_destino": 81},
            {"peso_bruto_destino": 49.690, "tara_destino": 17.000, "neto_destino": 32.610},
        ):
            self.assert_bad_request(**(base | changes))

    def test_pesaje_unico_acepta_hasta_200_tn_y_rechaza_mas(self):
        base = dict(
            pesaje_unico=True, cliente_id=None, peso_bruto_origen=0,
            tara_origen=0, neto_origen=0,
        )
        row = self.create_trip(self.payload(
            **base, peso_bruto_destino=190, tara_destino=40, neto_destino=150,
        ))
        self.assertEqual(row.produccion, Decimal("150.00"))
        self.assert_bad_request(
            **base, numero_remision="R-2", numero_remision_fpv="F-2",
            peso_bruto_destino=201, tara_destino=1, neto_destino=200,
        )

    def test_normal_preserva_mapeo_defaults_duplicados_y_normalizacion(self):
        row = self.create_trip(self.payload(proveedor_id=None, cliente_id=None))
        self.assertEqual(row.proveedor_id, None)
        self.assertEqual(row.cliente_id, 1)
        self.assertEqual(row.equipo_id, 30)
        self.assertEqual(row.unidad_negocio_id, 3)
        self.assertEqual(row.remito_proveedor, "R-1")
        self.assertEqual(row.remito_fgpy, "F-1")
        self.assertEqual(row.bruto_destino, Decimal("48.50"))
        self.assertEqual(row.tara_destino, Decimal("16.50"))
        self.assertEqual(row.usuario, "10")
        self.assert_bad_request(numero_remision="R-1", numero_remision_fpv="F-9")
        self.assert_bad_request(numero_remision="R-9", numero_remision_fpv="F-1")

    def test_cliente_default_debe_exist_y_estar_activo(self):
        row = self.create_trip(self.payload(cliente_id=None))
        self.assertEqual(row.cliente_id, 1)
        self.db.delete(self.client)
        self.db.commit()
        self.assert_bad_request(
            cliente_id=None, numero_remision="R-2", numero_remision_fpv="F-2"
        )
        self.client = self.models.Cliente(id=1, razon_social="Cliente inactivo", activo=False)
        self.db.add(self.client)
        self.db.commit()
        self.assert_bad_request(
            cliente_id=None, numero_remision="R-3", numero_remision_fpv="F-3"
        )

    def test_schema_rechaza_pesos_no_finitos(self):
        for field in (
            "peso_bruto_origen", "tara_origen", "neto_origen",
            "peso_bruto_destino", "tara_destino", "neto_destino",
        ):
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.assertRaises(ValueError, msg=f"{field}={value}"):
                    self.payload(**{field: value})

    def test_servicio_rechaza_pesos_no_finitos_aunque_se_omita_schema(self):
        normal = self.payload()
        unique = self.payload(
            pesaje_unico=True, cliente_id=None, peso_bruto_origen=0,
            tara_origen=0, neto_origen=0,
        )
        for base, fields in (
            (normal, ("peso_bruto_origen", "tara_origen", "neto_origen",
                      "peso_bruto_destino", "tara_destino", "neto_destino")),
            (unique, ("peso_bruto_origen", "tara_origen", "neto_origen",
                      "peso_bruto_destino", "tara_destino", "neto_destino")),
        ):
            for field in fields:
                for value in (float("nan"), float("inf"), float("-inf")):
                    registro = base.model_copy(update={field: value})
                    with self.assertRaises(HTTPException, msg=f"{field}={value}") as ctx:
                        self.create_trip(registro)
                    self.assertEqual(ctx.exception.status_code, 400)

    def test_redondea_pesos_a_centavos_half_up(self):
        row = self.create_trip(self.payload(
            peso_bruto_origen=48.505, tara_origen=16.505,
            neto_origen=32.005, neto_destino=32.615,
        ))
        self.assertEqual(row.bruto_destino, Decimal("48.51"))
        self.assertEqual(row.tara_destino, Decimal("16.51"))
        self.assertEqual(row.neto_origen, Decimal("32.01"))
        self.assertEqual(row.neto_destino, Decimal("32.62"))
        self.assertEqual(row.produccion, Decimal("32.01"))

    def test_pesaje_unico_valida_crudo_y_persiste_relacion_redondeada(self):
        row = self.create_trip(self.payload(
            pesaje_unico=True, cliente_id=None, peso_bruto_origen=0,
            tara_origen=0, neto_origen=0, peso_bruto_destino=49.695,
            tara_destino=17.084, neto_destino=32.611,
        ))
        self.assertEqual(row.bruto_destino, Decimal("49.70"))
        self.assertEqual(row.tara_destino, Decimal("17.08"))
        self.assertEqual(row.neto_destino, Decimal("32.62"))
        self.assertEqual(row.produccion, Decimal("32.62"))
        self.assertEqual(row.bruto_destino - row.tara_destino, row.neto_destino)

    def test_commit_false_flushes_y_outer_rollback_removes_row(self):
        row = self.create_trip(self.payload(), commit=False)
        self.assertIsNotNone(row.id)
        row_id = row.id
        self.db.rollback()
        self.assertIsNone(self.db.get(self.models.TableroProduccion, row_id))

    def test_commit_true_commits(self):
        row_id = self.create_trip(self.payload(), commit=True).id
        self.db.close()
        self.db = self.Session()
        self.assertIsNotNone(self.db.get(self.models.TableroProduccion, row_id))

    def test_identidad_efectiva_es_explicita_y_debe_estar_activa(self):
        row = self.create_trip(self.payload())
        self.assertEqual(row.empleado_id, self.employee.id)
        self.assertEqual(row.usuario, str(self.employee.id))
        self.employee.activo = False
        self.db.commit()
        self.assert_bad_request(numero_remision="R-2", numero_remision_fpv="F-2")

    def test_rechaza_equipo_y_cliente_inactivos(self):
        self.equipment.activo = False
        self.db.commit()
        self.assert_bad_request()
        self.equipment.activo = True
        self.client.activo = False
        self.db.commit()
        self.assert_bad_request()

    def test_servicio_establece_contexto_de_chofer_y_vehiculo(self):
        with patch("trip_service.set_request_context") as context:
            self.create_trip(self.payload())
        context.assert_any_call(chofer="Perez Ana")
        context.assert_any_call(vehiculo="AA 123 BB - Camion")

    def test_endpoint_rechaza_chofer_ajeno_y_delega_usuario_actual(self):
        sentry_sdk = types.ModuleType("sentry_sdk")
        sentry_sdk.init = lambda *args, **kwargs: None
        sys.modules.setdefault("sentry_sdk", sentry_sdk)
        sys.modules.setdefault("sentry_sdk.integrations", types.ModuleType("sentry_sdk.integrations"))
        for suffix, class_name in (
            ("logging", "LoggingIntegration"), ("starlette", "StarletteIntegration"),
            ("fastapi", "FastApiIntegration"),
        ):
            module = types.ModuleType(f"sentry_sdk.integrations.{suffix}")
            setattr(module, class_name, type(class_name, (), {"__init__": lambda self, *a, **k: None}))
            sys.modules.setdefault(f"sentry_sdk.integrations.{suffix}", module)
        import main

        registro = self.payload(chofer_id=99)
        with self.assertRaises(HTTPException) as ctx:
            with patch("main.clear_request_context") as clear_rejected:
                main.create_registro_viaje(registro, self.db, self.employee)
        self.assertEqual(ctx.exception.status_code, 403)
        clear_rejected.assert_called_once_with()

        registro = self.payload(chofer_id=self.employee.id)
        sentinel = type("Trip", (), {"id": 777})()
        with patch("main.create_trip", return_value=sentinel) as create, \
             patch("main.clear_request_context") as clear:
            response = main.create_registro_viaje(registro, self.db, self.employee)
        create.assert_called_once_with(self.db, registro, self.employee)
        clear.assert_called_once_with()
        self.assertEqual(response, {"id": 777, "message": "Viaje registrado OK"})


if __name__ == "__main__":
    unittest.main()


class TripImageEndpointServiceTest(unittest.TestCase):
    def test_analysis_saves_bounded_image_normalizes_and_matches_unique_provider(self):
        from image_storage import ImageStorage
        from trip_image_service import TripImageService
        import models

        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        storage = ImageStorage(Path(root.name).resolve(), "x" * 32)
        vision_data = {
            "fecha_remision": "2026-07-13", "remito_tipo": "002",
            "remito_sucursal": "003", "remito_numero": "0003677",
            "proveedor_candidato": "Alcogreen S.A.", "peso_bruto": 49690,
            "tara": 17080, "neto": 32610, "unidad_peso": "kg",
            "patente_observada": "ABC123", "chofer_observado": "Otro",
            "confidence": {"fecha_remision": .9}, "warnings": ["revisar"],
        }
        vision = type("Vision", (), {"analyze": lambda self, path: vision_data})()
        engine = create_engine("sqlite:///:memory:")
        models.Proveedor.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        db.add(models.Proveedor(id=7, razon_social="ALCOGREEN SRL", activo=True)); db.commit()
        result = TripImageService(db, storage, vision).analyze(
            b"\xff\xd8\xffdata", "ticket.jpg", "image/jpeg"
        )
        self.assertEqual(result["proposal"]["proveedor_id"], 7)
        self.assertEqual(result["proposal"]["numero_remision_fpv"], "002-003-0003677")
        self.assertEqual(result["proposal"]["neto_destino"], Decimal("32.610"))
        self.assertEqual(result["proposal"]["patente_observada"], "ABC123")

    def test_confirm_schema_does_not_accept_identity_fields(self):
        from schemas import TripImageConfirmRequest
        fields = set(TripImageConfirmRequest.model_fields)
        self.assertNotIn("chofer_id", fields)
        self.assertNotIn("cliente_id", fields)
        self.assertNotIn("pesaje_unico", fields)
