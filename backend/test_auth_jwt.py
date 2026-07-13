import os
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
