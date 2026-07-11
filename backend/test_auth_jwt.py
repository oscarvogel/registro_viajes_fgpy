import os
import sys
import tempfile
import types
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch


class AuthJwtTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmpdir.name, "auth_test.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["ENABLE_ERROR_ALERT_EMAILS"] = "false"
        os.environ["JWT_SECRET_KEY"] = "test-secret-for-jwt-with-at-least-32-bytes"
        os.environ["JWT_ALGORITHM"] = "HS256"
        os.environ["JWT_EXPIRE_MINUTES"] = "60"
        os.environ["AUTH_ENFORCEMENT_MODE"] = "compat"
        os.environ["LOGIN_RATE_LIMIT_ATTEMPTS"] = "3"
        os.environ["LOGIN_RATE_LIMIT_WINDOW_SECONDS"] = "900"
        os.environ["LOGIN_RATE_LIMIT_LOCKOUT_SECONDS"] = "900"
        os.environ.pop("CORS_ORIGINS", None)
        os.environ["ADMIN_USER_IDS"] = "123"
        os.environ["CLIENT_LOG_RETENTION_DAYS"] = "60"
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
        self._seed_employee()
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

    def _seed_employee(self):
        empleado = self.models.Empleado(
            id=123,
            nombre="Ada",
            apellido="Lovelace",
            email="ada@example.com",
            documento="12345678",
            fecha_contratacion=date(2024, 1, 1),
            activo=True,
            porcentaje=0.0,
        )
        self.db.add(empleado)
        inactivo = self.models.Empleado(
            id=124,
            nombre="Grace",
            apellido="Hopper",
            email="grace@example.com",
            documento="87654321",
            fecha_contratacion=date(2024, 1, 1),
            activo=False,
            porcentaje=0.0,
        )
        self.db.add(inactivo)
        no_admin = self.models.Empleado(
            id=125,
            nombre="Alan",
            apellido="Turing",
            email="alan@example.com",
            documento="11223344",
            fecha_contratacion=date(2024, 1, 1),
            activo=True,
            porcentaje=0.0,
        )
        self.db.add(no_admin)
        proveedor = self.models.Proveedor(
            id=10,
            razon_social="Proveedor Uno",
            direccion="Direccion secreta",
            telefono="123",
            cuit="80012345-6",
            activo=True,
        )
        self.db.add(proveedor)
        cliente = self.models.Cliente(
            id=20,
            razon_social="Cliente Uno",
            direccion="Direccion cliente",
            telefono="456",
            cuit="90012345-6",
            activo=True,
        )
        self.db.add(cliente)
        self.db.commit()

    def _seed_carreton_references(self):
        equipo = self.models.Equipo(
            id=10,
            descripcion="Carreton test",
            patente="TEST10",
            nro_chasis="CH10",
            nro_motor="MO10",
            tipo_movil_id=4,
            activo=True,
            movil_asociado=0,
            ult_hr_km=0,
        )
        unidad = self.models.UnidadNegocio(
            id=19,
            descripcion="Unidad test",
            prefijo="UT",
            activo=True,
            codigo_kobo="UT19",
        )
        self.db.add(equipo)
        self.db.add(unidad)
        self.db.commit()

    def test_login_emite_jwt_real_manteniendo_contrato(self):
        request = self.main.schemas.LoginRequest(documento="12345678")

        response = self.main.login(request, self.db)

        self.assertEqual(response["token_type"], "bearer")
        self.assertEqual(response["user"]["id"], 123)
        self.assertNotIn("fake-jwt-token", response["access_token"])
        self.assertEqual(len(response["access_token"].split(".")), 3)

        payload = self.main.decode_access_token(response["access_token"])
        self.assertEqual(payload["sub"], "123")
        self.assertEqual(payload["documento"], "12345678")
        self.assertEqual(payload["nombre"], "Ada")
        self.assertIn("exp", payload)

    def test_login_no_enumera_documento_inexistente_o_inactivo(self):
        from fastapi import HTTPException

        for documento in ("00000000", "87654321"):
            with self.subTest(documento=documento):
                request = self.main.schemas.LoginRequest(documento=documento)
                with self.assertRaises(HTTPException) as ctx:
                    self.main.login(request, self.db)

                self.assertEqual(ctx.exception.status_code, 400)
                self.assertEqual(ctx.exception.detail, "Credenciales invalidas")

    def test_login_aplica_rate_limit_por_documento(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)
        payload = {"documento": "99999999"}

        for _ in range(3):
            response = client.post("/api/login", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"], "Credenciales invalidas")

        response = client.post("/api/login", json=payload)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"], "Demasiados intentos. Intente nuevamente mas tarde.")
        self.assertEqual(response.headers["retry-after"], "900")

    def test_login_acepta_barra_final_para_clientes_legacy(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        response = client.post("/api/login/", json={"documento": "12345678"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["id"], 123)
        self.assertEqual(response.json()["token_type"], "bearer")

    def test_admin_health_sigue_publico(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        response = client.get("/api/admin/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "registro_viajes")

    def test_catalogos_no_exponen_datos_sensibles(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        empleados = client.get("/api/empleados").json()
        proveedores = client.get("/api/proveedores").json()
        clientes = client.get("/api/clientes").json()

        self.assertGreaterEqual(len(empleados), 1)
        self.assertNotIn("documento", empleados[0])
        self.assertNotIn("email", empleados[0])
        self.assertNotIn("telefono", empleados[0])
        self.assertNotIn("direccion", empleados[0])

        self.assertEqual(proveedores[0]["razon_social"], "Proveedor Uno")
        self.assertNotIn("cuit", proveedores[0])
        self.assertNotIn("direccion", proveedores[0])
        self.assertNotIn("telefono", proveedores[0])

        self.assertEqual(clientes[0]["razon_social"], "Cliente Uno")
        self.assertNotIn("cuit", clientes[0])
        self.assertNotIn("direccion", clientes[0])
        self.assertNotIn("telefono", clientes[0])

    def test_cors_permite_origenes_configurados(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        response = client.options(
            "/api/admin/health",
            headers={
                "Origin": "https://viajes.forestalparaguay.com",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "https://viajes.forestalparaguay.com",
        )

    def test_cors_no_refleja_origen_no_permitido(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        response = client.get(
            "/api/admin/health",
            headers={"Origin": "https://evil.example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.headers.get("access-control-allow-origin"), "*")
        self.assertIsNone(response.headers.get("access-control-allow-origin"))

    def test_sentry_debug_deshabilitado_por_defecto(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        response = client.get("/sentry-debug")

        self.assertEqual(response.status_code, 404)

    def test_admin_scheduled_jobs_requiere_token(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        response = client.get("/api/admin/scheduled-jobs")

        self.assertEqual(response.status_code, 401)

    def test_admin_scheduled_jobs_acepta_jwt_valido(self):
        from fastapi.testclient import TestClient

        token = self.main.create_access_token({"sub": "123"})
        client = TestClient(self.main.app)

        with patch.object(self.main.task_scheduler, "get_scheduled_jobs", return_value=[]):
            response = client.get(
                "/api/admin/scheduled-jobs",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"jobs": [], "count": 0})

    def test_client_log_summary_requiere_token(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        response = client.get("/api/admin/client-log-summary")

        self.assertEqual(response.status_code, 401)

    def test_client_log_summary_requiere_usuario_admin(self):
        from fastapi.testclient import TestClient

        token = self.main.create_access_token({"sub": "125"})
        client = TestClient(self.main.app)

        response = client.get(
            "/api/admin/client-log-summary",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 403)

    def test_client_log_summary_acepta_usuario_admin(self):
        from fastapi.testclient import TestClient

        token = self.main.create_access_token({"sub": "123"})
        client = TestClient(self.main.app)

        response = client.get(
            "/api/admin/client-log-summary",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["max_items"], 200)
        self.assertEqual(data["filters"], {"category": None, "page": None, "date_from": None, "date_to": None})

    def test_rutas_escritura_requieren_token(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)
        endpoints = (
            "/api/registro-viaje",
            "/api/movimiento-combustible",
            "/api/movimiento-carreton",
        )

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = client.post(endpoint, json={})
                self.assertEqual(response.status_code, 401)

    def test_movimiento_carreton_acepta_estado_vacio_con_tilde(self):
        from fastapi.testclient import TestClient

        self._seed_carreton_references()
        token = self.main.create_access_token({"sub": "123"})
        client = TestClient(self.main.app)

        response = client.post(
            "/api/movimiento-carreton",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "fecha": "2026-05-18",
                "equipo_id": 10,
                "unidad_negocio_id": 19,
                "hora_inicio_viaje": "07:00:00",
                "km_inicial": 99635.0,
                "km_final": 99645.0,
                "estado_carga": "vacío",
                "tipo_maquina_transportada": "RANDON",
                "usuario": "123",
                "origen_carreton": "PORTERIA PARAGUARI",
                "destino_carreton": "Playa Biomasa",
            },
        )

        self.assertEqual(response.status_code, 200)
        movimiento = (
            self.db.query(self.models.TableroProduccion)
            .filter(self.models.TableroProduccion.tabla == "movimiento_carreton")
            .one()
        )
        self.assertEqual(movimiento.origen, "Vacío")

    def test_movimiento_carreton_acepta_km_inicial_menor_si_fue_confirmado(self):
        from fastapi.testclient import TestClient

        self._seed_carreton_references()
        anterior = self.models.TableroProduccion(
            fecha=date(2026, 5, 17),
            unidad_negocio_id=19,
            empleado_id=123,
            equipo_id=10,
            hr_inicio=102200.0,
            hr_fin=102252.0,
            produccion=52.0,
            unidad_produccion_id=7,
            observaciones="RANDON",
            coeficiente=1.0,
            altura=0.0,
            ancho=0.0,
            cantidad_estibas=0.0,
            largo_madera=0.0,
            remito=0,
            carros=0,
            hora=datetime.now().time(),
            turno="dia",
            cliente_id=1,
            proveedor_id=None,
            plantas=0,
            predio_id=1,
            hrs_no_operativas=0,
            carga_piso=0,
            tipo_operacion_id=1,
            lenia_seca=0,
            carga_rollo=0,
            carga_lenia=0,
            periodo="202605",
            tarifa=0.0,
            tarifa_empresa=0.0,
            origen_destino_id=1,
            tabla="movimiento_carreton",
            codigo_tabla=0,
            origen="Vacío",
            remito2=0,
            modificado=False,
            usuario="123",
        )
        self.db.add(anterior)
        self.db.commit()

        token = self.main.create_access_token({"sub": "123"})
        client = TestClient(self.main.app)

        response = client.post(
            "/api/movimiento-carreton",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "fecha": "2026-05-18",
                "equipo_id": 10,
                "unidad_negocio_id": 19,
                "hora_inicio_viaje": "07:00:00",
                "km_inicial": 102240.0,
                "km_final": 102260.0,
                "estado_carga": "vacío",
                "tipo_maquina_transportada": "RANDON",
                "usuario": "123",
                "origen_carreton": "PORTERIA PARAGUARI",
                "destino_carreton": "Playa Biomasa",
                "permitir_km_inicial_menor": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        movimientos = (
            self.db.query(self.models.TableroProduccion)
            .filter(self.models.TableroProduccion.tabla == "movimiento_carreton")
            .order_by(self.models.TableroProduccion.id)
            .all()
        )
        self.assertEqual(len(movimientos), 2)
        self.assertEqual(float(movimientos[-1].hr_inicio), 102240.0)

    def test_rutas_consulta_usuario_requieren_token(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)
        endpoints = (
            "/api/historial-viajes?chofer_id=123&fecha_desde=2026-01-01&fecha_hasta=2026-01-31",
            "/api/movimientos-combustible?fecha_desde=2026-01-01&fecha_hasta=2026-01-31",
            "/api/movimientos-carreton?chofer_id=123&fecha_desde=2026-01-01&fecha_hasta=2026-01-31",
            "/api/movimientos-carreton/ultimo?equipo_id=1",
        )

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = client.get(endpoint)
                self.assertEqual(response.status_code, 401)

    def test_historial_no_permite_consultar_otro_usuario(self):
        from fastapi.testclient import TestClient

        token = self.main.create_access_token({"sub": "123"})
        client = TestClient(self.main.app)

        response = client.get(
            "/api/historial-viajes?chofer_id=999&fecha_desde=2026-01-01&fecha_hasta=2026-01-31",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 403)

    def test_movimientos_carreton_no_permite_consultar_otro_usuario(self):
        from fastapi.testclient import TestClient

        token = self.main.create_access_token({"sub": "123"})
        client = TestClient(self.main.app)

        response = client.get(
            "/api/movimientos-carreton?chofer_id=999&fecha_desde=2026-01-01&fecha_hasta=2026-01-31",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 403)

    def test_client_logs_recibe_errores_y_sugiere_acciones(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        response = client.post(
            "/api/logs/client",
            json={
                "logs": [
                    {
                        "timestamp": "2026-05-24T20:00:00Z",
                        "level": "error",
                        "message": "HTTP 500 al enviar logs",
                        "event_type": "error",
                        "page": "/fuel-load",
                        "component": "ClientLogger",
                        "user_id": "123",
                        "error_name": "Error",
                        "error_message": "HTTP 500",
                        "extra": {"access_token": "secret-token", "payload": "x" * 2000},
                    }
                ],
                "device_info": {"userAgent": "test", "token": "secret"},
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["logs_received"], 1)
        self.assertEqual(data["error_summary"]["errors"], 1)
        self.assertEqual(data["error_summary"]["categories"]["server"], 1)
        self.assertIn("Revisar logs del backend", data["suggested_actions"][0])

    def test_client_log_summary_guarda_resumen_sanitizado_para_admin(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)
        admin_token = self.main.create_access_token({"sub": "123"})

        client.post(
            "/api/logs/client",
            json={
                "logs": [
                    {
                        "timestamp": "2026-05-24T20:00:00Z",
                        "level": "error",
                        "message": "HTTP 500 con token secreto",
                        "event_type": "error",
                        "page": "/fuel-load",
                        "component": "ClientLogger",
                        "user_id": "123",
                        "error_name": "Error",
                        "error_message": "HTTP 500",
                        "extra": {"access_token": "secret-token", "payload": "x" * 2000},
                    }
                ],
                "device_info": {"userAgent": "test", "token": "secret"},
            },
        )

        response = client.get(
            "/api/admin/client-log-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["max_items"], 200)
        item = data["items"][0]
        self.assertEqual(item["summary"]["categories"]["server"], 1)
        self.assertEqual(item["samples"][0]["extra"]["access_token"], "REDACTED")
        self.assertEqual(len(item["samples"][0]["extra"]["payload"]), 500)

    def test_client_log_summary_persiste_aunque_se_limpie_memoria(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)
        admin_token = self.main.create_access_token({"sub": "123"})

        client.post(
            "/api/logs/client",
            json={
                "logs": [
                    {
                        "timestamp": "2026-05-24T20:00:00Z",
                        "level": "error",
                        "message": "Persistente",
                        "event_type": "frontend",
                    }
                ],
            },
        )
        self.main.client_log_summary_items.clear()

        response = client.get(
            "/api/admin/client-log-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["items"][0]["samples"][0]["message"], "Persistente")

    def test_client_log_summary_no_guarda_logs_info(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)
        admin_token = self.main.create_access_token({"sub": "123"})

        client.post(
            "/api/logs/client",
            json={
                "logs": [
                    {
                        "timestamp": "2026-05-24T20:00:00Z",
                        "level": "info",
                        "message": "pantalla cargada",
                        "event_type": "navigation",
                    }
                ],
            },
        )

        response = client.get(
            "/api/admin/client-log-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_client_log_summary_delete_requiere_token(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)

        response = client.delete("/api/admin/client-log-summary")

        self.assertEqual(response.status_code, 401)

    def test_client_log_summary_delete_requiere_admin(self):
        from fastapi.testclient import TestClient

        token = self.main.create_access_token({"sub": "125"})
        client = TestClient(self.main.app)

        response = client.delete(
            "/api/admin/client-log-summary",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 403)

    def test_client_log_summary_delete_limpia_items(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)
        admin_token = self.main.create_access_token({"sub": "123"})

        client.post(
            "/api/logs/client",
            json={
                "logs": [
                    {
                        "timestamp": "2026-05-24T20:00:00Z",
                        "level": "warning",
                        "message": "IndexedDB quota warning",
                        "event_type": "storage",
                    }
                ],
            },
        )

        response = client.delete(
            "/api/admin/client-log-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "cleared": 1})

        response = client.get(
            "/api/admin/client-log-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_client_log_summary_delete_filtra_por_categoria_sin_borrar_otros(self):
        from fastapi.testclient import TestClient

        self.db.add_all([
            self.models.ClientLogSummary(
                created_at=datetime(2026, 5, 24, 10, 0, 0),
                summary_json=self.main._client_log_json_dumps({"errors": 1, "warnings": 0, "categories": {"server": 1}}),
                suggested_actions_json=self.main._client_log_json_dumps(["server"]),
                samples_json=self.main._client_log_json_dumps([{"level": "error", "message": "HTTP 500", "page": "/fuel-load"}]),
            ),
            self.models.ClientLogSummary(
                created_at=datetime(2026, 5, 24, 11, 0, 0),
                summary_json=self.main._client_log_json_dumps({"errors": 1, "warnings": 0, "categories": {"frontend": 1}}),
                suggested_actions_json=self.main._client_log_json_dumps(["frontend"]),
                samples_json=self.main._client_log_json_dumps([{"level": "error", "message": "Vue error", "page": "/history"}]),
            ),
        ])
        self.db.commit()

        client = TestClient(self.main.app)
        admin_token = self.main.create_access_token({"sub": "123"})

        response = client.delete(
            "/api/admin/client-log-summary?category=server",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cleared"], 1)

        response = client.get(
            "/api/admin/client-log-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["items"][0]["samples"][0]["message"], "Vue error")

    def test_client_log_summary_delete_filtra_por_pagina_y_conserva_otras_muestras(self):
        from fastapi.testclient import TestClient

        self.db.add(
            self.models.ClientLogSummary(
                created_at=datetime(2026, 5, 24, 10, 0, 0),
                summary_json=self.main._client_log_json_dumps({"errors": 2, "warnings": 0, "categories": {"server": 1, "frontend": 1}}),
                suggested_actions_json=self.main._client_log_json_dumps(["server", "frontend"]),
                samples_json=self.main._client_log_json_dumps([
                    {"level": "error", "message": "HTTP 500", "error_message": "HTTP 500", "page": "/fuel-load"},
                    {"level": "error", "message": "Vue error", "error_message": "Vue error", "page": "/history"},
                ]),
            )
        )
        self.db.commit()

        client = TestClient(self.main.app)
        admin_token = self.main.create_access_token({"sub": "123"})

        response = client.delete(
            "/api/admin/client-log-summary?page=fuel",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cleared"], 1)

        response = client.get(
            "/api/admin/client-log-summary",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(len(data["items"][0]["samples"]), 1)
        self.assertEqual(data["items"][0]["samples"][0]["page"], "/history")
        self.assertEqual(data["items"][0]["summary"]["categories"], {"frontend": 1})

    def test_client_log_summary_respeta_limite_maximo(self):
        from fastapi.testclient import TestClient

        client = TestClient(self.main.app)
        admin_token = self.main.create_access_token({"sub": "123"})
        original_max = self.main.CLIENT_LOG_SUMMARY_MAX_ITEMS
        self.main.CLIENT_LOG_SUMMARY_MAX_ITEMS = 2

        try:
            for index in range(3):
                client.post(
                    "/api/logs/client",
                    json={
                        "logs": [
                            {
                                "timestamp": "2026-05-24T20:00:00Z",
                                "level": "error",
                                "message": f"Error {index}",
                                "event_type": "frontend",
                            }
                        ],
                    },
                )

            response = client.get(
                "/api/admin/client-log-summary",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        finally:
            self.main.CLIENT_LOG_SUMMARY_MAX_ITEMS = original_max

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["max_items"], 2)
        messages = [item["samples"][0]["message"] for item in data["items"]]
        self.assertEqual(messages, ["Error 2", "Error 1"])

    def test_client_log_summary_aplica_retencion_por_dias(self):
        from fastapi.testclient import TestClient

        original_retention_days = self.main.CLIENT_LOG_RETENTION_DAYS
        self.main.CLIENT_LOG_RETENTION_DAYS = 15
        old_record = self.models.ClientLogSummary(
            created_at=datetime.now() - timedelta(days=30),
            summary_json=self.main._client_log_json_dumps({"errors": 1, "warnings": 0, "categories": {"frontend": 1}}),
            suggested_actions_json=self.main._client_log_json_dumps(["viejo"]),
            samples_json=self.main._client_log_json_dumps([{"message": "Registro viejo"}]),
        )
        fresh_record = self.models.ClientLogSummary(
            created_at=datetime.now(),
            summary_json=self.main._client_log_json_dumps({"errors": 1, "warnings": 0, "categories": {"frontend": 1}}),
            suggested_actions_json=self.main._client_log_json_dumps(["nuevo"]),
            samples_json=self.main._client_log_json_dumps([{"message": "Registro nuevo"}]),
        )
        self.db.add_all([old_record, fresh_record])
        self.db.commit()

        client = TestClient(self.main.app)
        admin_token = self.main.create_access_token({"sub": "123"})

        try:
            response = client.get(
                "/api/admin/client-log-summary",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        finally:
            self.main.CLIENT_LOG_RETENTION_DAYS = original_retention_days

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["items"][0]["samples"][0]["message"], "Registro nuevo")
        self.assertEqual(self.db.query(self.models.ClientLogSummary).count(), 1)

    def test_client_log_summary_filtra_por_categoria_pagina_y_fecha(self):
        from fastapi.testclient import TestClient

        records = [
            self.models.ClientLogSummary(
                created_at=datetime(2026, 5, 24, 10, 0, 0),
                summary_json=self.main._client_log_json_dumps({"errors": 2, "warnings": 0, "categories": {"server": 1, "frontend": 1}}),
                suggested_actions_json=self.main._client_log_json_dumps(["server"]),
                samples_json=self.main._client_log_json_dumps([
                    {"message": "HTTP 500", "page": "/fuel-load"},
                    {"message": "Vue error same batch", "page": "/history"},
                ]),
            ),
            self.models.ClientLogSummary(
                created_at=datetime(2026, 5, 24, 11, 0, 0),
                summary_json=self.main._client_log_json_dumps({"errors": 1, "warnings": 0, "categories": {"frontend": 1}}),
                suggested_actions_json=self.main._client_log_json_dumps(["frontend"]),
                samples_json=self.main._client_log_json_dumps([{"message": "Vue error", "page": "/history"}]),
            ),
            self.models.ClientLogSummary(
                created_at=datetime(2026, 5, 20, 11, 0, 0),
                summary_json=self.main._client_log_json_dumps({"errors": 1, "warnings": 0, "categories": {"server": 1}}),
                suggested_actions_json=self.main._client_log_json_dumps(["server viejo"]),
                samples_json=self.main._client_log_json_dumps([{"message": "Old HTTP 500", "page": "/fuel-load"}]),
            ),
        ]
        self.db.add_all(records)
        self.db.commit()

        client = TestClient(self.main.app)
        admin_token = self.main.create_access_token({"sub": "123"})

        response = client.get(
            "/api/admin/client-log-summary?category=server&page=fuel&date_from=2026-05-24&date_to=2026-05-24",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["items"][0]["samples"][0]["message"], "HTTP 500")
        self.assertEqual(len(data["items"][0]["samples"]), 1)
        self.assertEqual(data["filters"], {
            "category": "server",
            "page": "fuel",
            "date_from": "2026-05-24",
            "date_to": "2026-05-24",
        })


if __name__ == "__main__":
    unittest.main()
