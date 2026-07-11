import os
import sys
import tempfile
import types
import unittest
from datetime import date, datetime, time
from pathlib import Path


class AdminDashboardTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmpdir.name, "admin_dashboard_test.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["ENABLE_ERROR_ALERT_EMAILS"] = "false"
        os.environ["JWT_SECRET_KEY"] = "test-secret-for-jwt-with-at-least-32-bytes"
        os.environ["JWT_ALGORITHM"] = "HS256"
        os.environ["JWT_EXPIRE_MINUTES"] = "60"
        os.environ["AUTH_ENFORCEMENT_MODE"] = "compat"
        os.environ["ADMIN_USER_IDS"] = "123"
        os.environ["CLIENT_LOG_RETENTION_DAYS"] = "15"
        os.environ.pop("ENABLE_SENTRY_DEBUG", None)

        backend_dir = Path(__file__).resolve().parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        self._stub_sentry()
        for module_name in ("main", "models", "database"):
            sys.modules.pop(module_name, None)

        import database
        import main
        import models

        self.database = database
        self.main = main
        self.models = models

        models.Base.metadata.drop_all(bind=database.engine)
        models.Base.metadata.create_all(bind=database.engine)
        self.db = database.SessionLocal()
        self._seed_records()
        main.client_log_summary_items.clear()

    def tearDown(self):
        self.db.close()
        self.database.engine.dispose()
        self.tmpdir.cleanup()

    def _stub_sentry(self):
        sentry_sdk = types.ModuleType("sentry_sdk")
        sentry_sdk.init = lambda *args, **kwargs: None

        integrations = types.ModuleType("sentry_sdk.integrations")
        logging_integration = types.ModuleType("sentry_sdk.integrations.logging")
        starlette_integration = types.ModuleType("sentry_sdk.integrations.starlette")
        fastapi_integration = types.ModuleType("sentry_sdk.integrations.fastapi")

        class _Integration:
            def __init__(self, *args, **kwargs):
                pass

        logging_integration.LoggingIntegration = _Integration
        starlette_integration.StarletteIntegration = _Integration
        fastapi_integration.FastApiIntegration = _Integration

        sys.modules.setdefault("sentry_sdk", sentry_sdk)
        sys.modules.setdefault("sentry_sdk.integrations", integrations)
        sys.modules.setdefault("sentry_sdk.integrations.logging", logging_integration)
        sys.modules.setdefault("sentry_sdk.integrations.starlette", starlette_integration)
        sys.modules.setdefault("sentry_sdk.integrations.fastapi", fastapi_integration)

    def _seed_records(self):
        admin = self.models.Empleado(
            id=123,
            nombre="Ada",
            apellido="Lovelace",
            email="ada@example.com",
            documento="12345678",
            fecha_contratacion=date(2024, 1, 1),
            activo=True,
            porcentaje=0.0,
        )
        chofer = self.models.Empleado(
            id=125,
            nombre="Alan",
            apellido="Turing",
            email="alan@example.com",
            documento="11223344",
            fecha_contratacion=date(2024, 1, 1),
            activo=True,
            porcentaje=0.0,
        )
        unidad = self.models.UnidadNegocio(
            id=1,
            descripcion="Transporte Chip",
            prefijo="TC",
            activo=True,
            codigo_kobo="TC",
        )
        unidad_no_transporte = self.models.UnidadNegocio(
            id=2,
            descripcion="Forestal",
            prefijo="FOR",
            activo=True,
            codigo_kobo="FOR",
        )
        unidad_rollos = self.models.UnidadNegocio(
            id=3,
            descripcion="Transporte Rollos",
            prefijo="TR",
            activo=True,
            codigo_kobo="TR",
        )
        equipo = self.models.Equipo(
            id=10,
            descripcion="Camion Test",
            patente="ABC123",
            nro_chasis="CH10",
            nro_motor="MO10",
            tipo_movil_id=4,
            activo=True,
            movil_asociado=0,
            ult_hr_km=0,
        )
        proveedor = self.models.Proveedor(id=1, razon_social="Proveedor Test", activo=True)
        paniol = self.models.Paniol(id=1, descripcion="Tanque Test", activo=True, unidad_negocio_id=1)
        self.db.add_all([admin, chofer, unidad, unidad_no_transporte, unidad_rollos, equipo, proveedor, paniol])
        self.db.commit()

        self.db.add(
            self.models.TableroProduccion(
                id=100,
                fecha=date(2026, 5, 10),
                unidad_negocio_id=1,
                empleado_id=125,
                equipo_id=10,
                hr_inicio=0,
                hr_fin=0,
                produccion=30.5,
                remito=100,
                hora=time(8, 0),
                turno="D",
                cliente_id=1,
                proveedor_id=1,
                predio_id=1,
                periodo="202605",
                origen_destino_id=1,
                tabla=None,
                origen="Origen",
            )
        )
        self.db.add(
            self.models.TableroProduccion(
                id=102,
                fecha=date(2026, 5, 13),
                unidad_negocio_id=2,
                empleado_id=125,
                equipo_id=10,
                hr_inicio=0,
                hr_fin=0,
                produccion=999.0,
                remito=102,
                hora=time(10, 0),
                turno="D",
                cliente_id=1,
                proveedor_id=1,
                predio_id=1,
                periodo="202605",
                origen_destino_id=1,
                tabla=None,
                origen="No transporte",
            )
        )
        self.db.add(
            self.models.TableroProduccion(
                id=103,
                fecha=date(2026, 5, 14),
                unidad_negocio_id=3,
                empleado_id=125,
                equipo_id=10,
                hr_inicio=0,
                hr_fin=0,
                produccion=10.0,
                remito=103,
                hora=time(11, 0),
                turno="D",
                cliente_id=1,
                proveedor_id=1,
                predio_id=1,
                periodo="202605",
                origen_destino_id=1,
                tabla=None,
                origen="Rollos",
            )
        )
        self.db.add(
            self.models.TableroProduccion(
                id=101,
                fecha=date(2026, 5, 11),
                unidad_negocio_id=1,
                empleado_id=125,
                equipo_id=10,
                hr_inicio=100,
                hr_fin=120,
                produccion=0,
                remito=101,
                hora=time(9, 0),
                turno="D",
                cliente_id=1,
                proveedor_id=1,
                predio_id=1,
                periodo="202605",
                origen_destino_id=1,
                tabla="movimiento_carreton",
                origen="Cargado",
                observaciones="Excavadora",
            )
        )
        self.db.add(
            self.models.TableroProduccion(
                id=104,
                fecha=date(2026, 5, 15),
                unidad_negocio_id=2,
                empleado_id=125,
                equipo_id=10,
                hr_inicio=100,
                hr_fin=120,
                produccion=0,
                remito=104,
                hora=time(12, 0),
                turno="D",
                cliente_id=1,
                proveedor_id=1,
                predio_id=1,
                periodo="202605",
                origen_destino_id=1,
                tabla="movimiento_carreton",
                origen="No transporte",
                observaciones="No transporte",
            )
        )
        self.db.add(
            self.models.MovimientoCombustible(
                id=200,
                fecha=date(2026, 5, 12),
                tipo_combustible_id=1,
                equipo_id=10,
                km_hora=12345,
                precio_litro=0,
                ingreso=80,
                egreso=0,
                unidad_negocio_id=1,
                paniol_id=1,
                remito="R200",
                idtabla=0,
                tabla="movimientocombustible",
                usuario="125",
                fecha_grabacion=datetime(2026, 5, 12, 10, 0, 0),
                periodo="202605",
                remito2="R200",
            )
        )
        self.db.add(
            self.models.MovimientoCombustible(
                id=201,
                fecha=date(2026, 5, 16),
                tipo_combustible_id=1,
                equipo_id=10,
                km_hora=12355,
                precio_litro=0,
                ingreso=500,
                egreso=0,
                unidad_negocio_id=2,
                paniol_id=1,
                remito="R201",
                idtabla=0,
                tabla="movimientocombustible",
                usuario="125",
                fecha_grabacion=datetime(2026, 5, 16, 10, 0, 0),
                periodo="202605",
                remito2="R201",
            )
        )
        self.db.add(
            self.models.ClientLogSummary(
                created_at=datetime(2026, 5, 12, 11, 0, 0),
                summary_json=self.main._client_log_json_dumps(
                    {"errors": 2, "warnings": 1, "categories": {"server": 2, "storage": 1}}
                ),
                suggested_actions_json=self.main._client_log_json_dumps(["Revisar backend"]),
                samples_json=self.main._client_log_json_dumps([]),
            )
        )
        self.db.commit()

    def _admin_headers(self):
        token = self.main.create_access_token({"sub": "123"})
        return {"Authorization": f"Bearer {token}"}

    def test_dashboard_summary_requiere_token(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        response = client.get("/api/admin/dashboard-summary?fecha_desde=2026-05-01&fecha_hasta=2026-05-31")

        self.assertEqual(response.status_code, 401)

    def test_dashboard_summary_requiere_usuario_admin(self):
        from fastapi.testclient import TestClient

        token = self.main.create_access_token({"sub": "125"})
        client = TestClient(self.main.app)

        response = client.get(
            "/api/admin/dashboard-summary?fecha_desde=2026-05-01&fecha_hasta=2026-05-31",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 403)

    def test_dashboard_summary_devuelve_kpis_y_rankings(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        response = client.get(
            "/api/admin/dashboard-summary?fecha_desde=2026-05-01&fecha_hasta=2026-05-31",
            headers=self._admin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["period"], {"fecha_desde": "2026-05-01", "fecha_hasta": "2026-05-31"})
        self.assertEqual(data["kpis"]["viajes"], 2)
        self.assertEqual(data["kpis"]["toneladas"], 40.5)
        self.assertEqual(data["kpis"]["promedio_toneladas_por_viaje"], 20.25)
        self.assertEqual(data["kpis"]["litros"], 80.0)
        self.assertEqual(data["kpis"]["movimientos_carreton"], 1)
        self.assertNotIn("errores_frontend", data["kpis"])
        self.assertNotIn("warnings_frontend", data["kpis"])
        self.assertEqual(data["rankings"]["por_equipo"][0]["label"], "ABC123")
        self.assertEqual(data["rankings"]["por_equipo"][0]["id"], 10)
        self.assertEqual(data["rankings"]["por_equipo"][0]["kind"], "equipo")
        self.assertEqual(data["rankings"]["por_equipo"][0]["average"], 20.25)
        self.assertEqual(data["rankings"]["por_equipo"][0]["share"], 100.0)
        self.assertEqual(
            data["rankings"]["por_equipo"][0]["units"],
            [
                {"label": "Transporte Chip", "count": 1, "total": 30.5},
                {"label": "Transporte Rollos", "count": 1, "total": 10.0},
            ],
        )
        self.assertEqual(
            data["rankings"]["por_equipo"][0]["days"],
            [
                {"fecha": "2026-05-10", "count": 1, "total": 30.5, "average": 30.5},
                {"fecha": "2026-05-14", "count": 1, "total": 10.0, "average": 10.0},
            ],
        )
        self.assertEqual(data["rankings"]["por_equipo"][0]["fuel_liters"], 580.0)
        self.assertEqual(
            data["rankings"]["por_equipo"][0]["fuel_days"],
            [
                {"fecha": "2026-05-12", "litros": 80.0},
                {"fecha": "2026-05-16", "litros": 500.0},
            ],
        )
        self.assertEqual(data["rankings"]["por_chofer"][0]["label"], "Turing Alan")
        self.assertEqual(data["rankings"]["por_chofer"][0]["id"], 125)
        self.assertEqual(data["rankings"]["por_chofer"][0]["kind"], "chofer")
        self.assertEqual(data["rankings"]["por_chofer"][0]["average"], 20.25)
        self.assertEqual(data["rankings"]["por_chofer"][0]["share"], 100.0)
        self.assertEqual(
            data["rankings"]["por_chofer"][0]["days"],
            [
                {"fecha": "2026-05-10", "count": 1, "total": 30.5, "average": 30.5},
                {"fecha": "2026-05-14", "count": 1, "total": 10.0, "average": 10.0},
            ],
        )
        self.assertEqual(data["rankings"]["por_chofer"][0]["fuel_liters"], 580.0)
        self.assertEqual(
            data["rankings"]["por_chofer"][0]["fuel_days"],
            [
                {"fecha": "2026-05-12", "litros": 80.0},
                {"fecha": "2026-05-16", "litros": 500.0},
            ],
        )
        unidad_labels = [item["label"] for item in data["rankings"]["por_unidad_negocio"]]
        self.assertEqual(unidad_labels, ["Transporte Chip", "Transporte Rollos"])
        self.assertNotIn("Forestal", unidad_labels)
        self.assertNotIn("client_log_items", data["alerts"])


if __name__ == "__main__":
    unittest.main()
