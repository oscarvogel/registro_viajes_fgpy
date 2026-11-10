import os
import re
import sys
import tempfile
import types
import unittest
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

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


class LecturaCamionBaseTest(unittest.TestCase):
    """Fixture compartida: base SQLite aislada con los datos minimos.

    Las clases de servicio, de endpoint y de historial heredan de aca. La base
    no define tests propios, asi que no se ejecutan por duplicado.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmpdir.name, "lectura_camion_test.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["ENABLE_ERROR_ALERT_EMAILS"] = "false"
        os.environ["JWT_SECRET_KEY"] = "test-secret-for-jwt-with-at-least-32-bytes"
        os.environ["JWT_ALGORITHM"] = "HS-256"
        os.environ["JWT_EXPIRE_MINUTES"] = "60"
        os.environ["AUTH_ENFORCEMENT_MODE"] = "compat"
        os.environ["ADMIN_USER_IDS"] = "1"

        backend_dir = Path(__file__).resolve().parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        self._stub_sentry()
        for module_name in ("main", "models", "database", "trip_service", "schemas"):
            sys.modules.pop(module_name, None)

        import database
        import models
        import schemas
        import trip_service

        self.database = database
        self.models = models
        self.schemas = schemas
        self.trip_service = trip_service

        models.Base.metadata.drop_all(bind=database.engine)
        models.Base.metadata.create_all(bind=database.engine)
        self.db = database.SessionLocal()
        self._seed()

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

    def _seed(self):
        self.empleado = self.models.Empleado(
            id=1, nombre="Ana", apellido="Perez", email="ana@example.com",
            documento="12345678", fecha_contratacion=date(2024, 1, 1),
            activo=True, porcentaje=0.0,
        )
        self.unidad = self.models.UnidadNegocio(
            id=1, descripcion="Transporte Chip", prefijo="TC", activo=True, codigo_kobo="TC",
        )
        self.cliente = self.models.Cliente(id=1, razon_social="Alcogreen", activo=True)
        self.proveedor = self.models.Proveedor(id=1, razon_social="Forestal Paraguay", activo=True)
        # El predio es obligatorio en el contrato de viajes: la unidad de
        # negocio y el cliente se derivan de el.
        self.predio = self.models.Predio(
            id=1, descripcion="Predio Principal", cliente_id=1, activo=True,
        )
        self.equipo_km = self.models.Equipo(
            id=10, descripcion="Scania", patente="ABC123", nro_chasis="CH10",
            nro_motor="MO10", tipo_movil_id=1, movil_asociado=0, activo=True,
            ult_hr_km=0, unidad_hr_km="km",
        )
        self.equipo_hs = self.models.Equipo(
            id=11, descripcion="Tractor", patente="HHS789", nro_chasis="CH11",
            nro_motor="MO11", tipo_movil_id=1, movil_asociado=0, activo=True,
            ult_hr_km=0, unidad_hr_km="hs",
        )
        self.db.add_all([
            self.empleado, self.unidad, self.cliente, self.proveedor, self.predio,
            self.equipo_km, self.equipo_hs,
        ])
        self.db.commit()

    @staticmethod
    def _remito_fpv(numero_remision):
        """Deriva un remito FGPY unico a partir del remito del proveedor.

        El numero de remito del proveedor y el de FGPY tienen constraints
        UNIQUE distintas: si el remito FGPY se deja fijo, el segundo viaje de
        un mismo test choca con la constraint antes de llegar a la validacion
        de la lectura.
        """
        partes = str(numero_remision).split("-")
        if len(partes) != 3 or not partes[-1].isdigit():
            return f"{numero_remision}-FPV"
        partes[-1] = f"{int(partes[-1]) + 1:0{len(partes[-1])}d}"
        return "-".join(partes)

    def _registro(self, **overrides):
        numero_remision = overrides.pop("numero_remision", "002-003-0000001")
        numero_remision_fpv = overrides.pop("numero_remision_fpv", self._remito_fpv(numero_remision))
        datos = dict(
            fecha_remision=date(2026, 11, 9),
            fecha_recepcion=date(2026, 11, 9),
            proveedor_id=1,
            cliente_id=1,
            predio_id=1,
            numero_remision=numero_remision,
            numero_remision_fpv=numero_remision_fpv,
            peso_bruto_origen=50.0,
            tara_origen=18.0,
            neto_origen=32.0,
            peso_bruto_destino=50.0,
            tara_destino=18.0,
            neto_destino=32.0,
            chofer_id=1,
            patente="ABC123",
            unidad_negocio_id=1,
        )
        datos.update(overrides)
        return self.schemas.RegistroViajeCreate(**datos)

    def _crear_viaje(self, **overrides):
        registro = self._registro(**overrides)
        return self.trip_service.create_trip(self.db, registro, self.empleado)


class LecturaCamionServicioTest(LecturaCamionBaseTest):
    def test_guarda_la_lectura_con_la_unidad_resuelta_del_equipo(self):
        viaje = self._crear_viaje(lectura_camion=1234.5)
        self.assertEqual(float(viaje.lectura_camion), 1234.5)
        self.assertEqual(viaje.unidad_lectura, "km")

    def test_equipo_con_horometro_guarda_la_unidad_hs(self):
        # La unidad se graba junto a la lectura: sin lectura no hay unidad
        # (la migracion de Task 1 rechaza esa incoherencia).
        registro = self._registro(
            patente="HHS789", numero_remision="002-003-0000003", lectura_camion=120.25
        )
        viaje = self.trip_service.create_trip(self.db, registro, self.empleado)
        self.assertEqual(viaje.unidad_lectura, "hs")
        self.assertEqual(float(viaje.lectura_camion), 120.25)

    def test_payload_sin_lectura_se_guarda_como_null_y_no_falla(self):
        viaje = self._crear_viaje()
        self.assertIsNone(viaje.lectura_camion)
        self.assertIsNone(viaje.unidad_lectura)

    def test_lectura_menor_a_la_anterior_es_rechazada(self):
        self._crear_viaje(lectura_camion=5000, numero_remision="002-003-0000011")

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:
            self._crear_viaje(lectura_camion=4000, numero_remision="002-003-0000012")

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("5000", str(caught.exception.detail))

    def test_lectura_menor_con_permiso_se_guarda(self):
        self._crear_viaje(lectura_camion=5000, numero_remision="002-003-0000021")
        viaje = self._crear_viaje(lectura_camion=4000, numero_remision="002-003-0000022", permitir_lectura_menor=True)
        self.assertEqual(float(viaje.lectura_camion), 4000)

    def test_lectura_no_positiva_es_rechazada(self):
        from fastapi import HTTPException
        for valor in (0, -10):
            with self.assertRaises(HTTPException) as caught:
                self._crear_viaje(lectura_camion=valor, numero_remision="002-003-0000031")
            self.assertEqual(caught.exception.status_code, 400)

    def test_lectura_desmedida_es_rechazada(self):
        # La columna es DECIMAL(10, 2): una lectura fuera de rango tiene que
        # rechazarse con 400, no reventar la DB con un 500.
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:
            self._crear_viaje(lectura_camion=100000000, numero_remision="002-003-0000032")
        self.assertEqual(caught.exception.status_code, 400)

    def test_lectura_desmedida_no_produce_500_sino_400(self):
        # El tope se compara contra el valor CRUDO, antes del redondeo. Si se
        # redondeara primero, un valor enorme lanzaria InvalidOperation al
        # cuantizar y la API responderia 500 en vez de 400.
        from fastapi import HTTPException
        for valor in (1e30, 99999999.994):
            with self.assertRaises(HTTPException) as caught:
                self._crear_viaje(lectura_camion=valor, numero_remision="002-003-0000033")
            self.assertEqual(caught.exception.status_code, 400)

    def test_lectura_en_el_limite_exacto_de_la_columna_se_guarda(self):
        # 99999999.99 es el maximo exacto de DECIMAL(10, 2): tiene que entrar.
        viaje = self._crear_viaje(lectura_camion=99999999.99, numero_remision="002-003-0000034")
        self.assertEqual(float(viaje.lectura_camion), 99999999.99)

    def test_la_lectura_se_redondea_a_dos_decimales(self):
        # Se verifica el valor que devuelve el servicio, no solo el que queda
        # en la fila: en SQLite la propia columna puede enmascarar que el
        # servicio no redondeo.
        registro = self._registro(lectura_camion=1234.567, numero_remision="002-003-0000035")
        lectura, _ = self.trip_service.validar_lectura(self.db, registro, self.equipo_km)
        self.assertEqual(lectura, Decimal("1234.57"))

        viaje = self._crear_viaje(lectura_camion=1234.567, numero_remision="002-003-0000035")
        self.assertEqual(float(viaje.lectura_camion), 1234.57)

    def test_el_permiso_no_anula_el_rechazo_de_lectura_no_positiva(self):
        # permitir_lectura_menor solo habilita el caso "menor a la anterior":
        # no abre la puerta a lecturas no positivas.
        from fastapi import HTTPException
        for valor in (0, -10):
            with self.assertRaises(HTTPException) as caught:
                self._crear_viaje(
                    lectura_camion=valor,
                    numero_remision="002-003-0000036",
                    permitir_lectura_menor=True,
                )
            self.assertEqual(caught.exception.status_code, 400)

    def test_el_permiso_no_anula_el_tope_de_la_columna(self):
        # Mismo criterio con el desborde de DECIMAL(10, 2).
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:
            self._crear_viaje(
                lectura_camion=100000000,
                numero_remision="002-003-0000037",
                permitir_lectura_menor=True,
            )
        self.assertEqual(caught.exception.status_code, 400)

    def test_no_compara_contra_la_lectura_de_otro_camion_de_la_misma_unidad(self):
        # Dos camiones en km: la lectura del camion A no puede bloquear al B.
        self._crear_viaje(lectura_camion=90000, numero_remision="002-003-0000038")

        self.equipo_km_b = self.models.Equipo(
            id=12, descripcion="Scania 2", patente="XYZ789", nro_chasis="CH12",
            nro_motor="MO12", tipo_movil_id=1, movil_asociado=0, activo=True,
            ult_hr_km=0, unidad_hr_km="km",
        )
        self.db.add(self.equipo_km_b)
        self.db.commit()

        viaje = self._crear_viaje(
            patente="XYZ789", lectura_camion=100, numero_remision="002-003-0000039"
        )
        self.assertEqual(float(viaje.lectura_camion), 100)

    def test_el_override_deja_rastro_en_el_log(self):
        # El flag viene del cliente y desactiva una validacion de negocio:
        # tiene que quedar registrado en el log (espejo del flujo de carreton).
        self._crear_viaje(lectura_camion=5000, numero_remision="002-003-0000040")

        with patch("trip_service.app_logger.warning") as advertencia:
            self._crear_viaje(
                lectura_camion=4000,
                numero_remision="002-003-0000041",
                permitir_lectura_menor=True,
            )

        self.assertEqual(advertencia.call_count, 1)
        detalle = advertencia.call_args.kwargs["extra"]["extra_data"]
        self.assertEqual(detalle["equipo_id"], 10)
        self.assertEqual(detalle["patente"], "ABC123")
        self.assertEqual(detalle["lectura_camion"], "4000.00")
        self.assertEqual(detalle["lectura_anterior"], "5000.00")
        self.assertEqual(detalle["unidad"], "km")
        self.assertEqual(detalle["usuario"], 1)
        self.assertTrue(detalle["confirmado_por_usuario"])

    def test_sin_override_no_se_loguea_nada(self):
        self._crear_viaje(lectura_camion=5000, numero_remision="002-003-0000042")

        from fastapi import HTTPException
        with patch("trip_service.app_logger.warning") as advertencia:
            with self.assertRaises(HTTPException):
                self._crear_viaje(lectura_camion=4000, numero_remision="002-003-0000043")
        advertencia.assert_not_called()

    def test_la_unidad_se_normaliza_a_minusculas(self):
        # 'HS' tiene que terminar en 'hs': sin normalizar, caeria al fallback
        # 'km' y el camion con horometro se trataria como si midiera km.
        self.equipo_hs.unidad_hr_km = "HS"
        self.db.commit()

        viaje = self._crear_viaje(
            patente="HHS789", lectura_camion=10, numero_remision="002-003-0000044"
        )
        self.assertEqual(viaje.unidad_lectura, "hs")

    def test_una_unidad_invalida_cae_a_km(self):
        self.equipo_km.unidad_hr_km = "millas"
        self.db.commit()

        viaje = self._crear_viaje(lectura_camion=10, numero_remision="002-003-0000045")
        self.assertEqual(viaje.unidad_lectura, "km")

    def test_no_compara_contra_lecturas_de_otra_unidad(self):
        # El admin cambia la unidad del camion: la lectura anterior quedo en 'km'
        # y la nueva es 'hs', asi que no se comparan numeros sin sentido.
        self._crear_viaje(lectura_camion=99999, numero_remision="002-003-0000041")

        self.equipo_km.unidad_hr_km = "hs"
        self.db.commit()

        viaje = self._crear_viaje(lectura_camion=5, numero_remision="002-003-0000042")
        self.assertEqual(float(viaje.lectura_camion), 5)
        self.assertEqual(viaje.unidad_lectura, "hs")

    def test_si_mantiene_la_unidad_sigue_comparando(self):
        self._crear_viaje(lectura_camion=99999, numero_remision="002-003-0000061")

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:
            self._crear_viaje(lectura_camion=5, numero_remision="002-003-0000062")

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("99999", str(caught.exception.detail))

    def test_no_compara_contra_movimientos_de_carreton(self):
        # Un movimiento de carreton usa hr_fin, no lectura_camion: no debe entrar en la cadena.
        self.db.add(self.models.TableroProduccion(
            fecha=date(2026, 11, 8),
            unidad_negocio_id=1, empleado_id=1, equipo_id=10,
            hr_inicio=8000.0, hr_fin=9000.0, produccion=1000.0,
            unidad_produccion_id=7, remito=0, remito2=0, hora=time(8, 0), turno="dia",
            predio_id=1, tipo_operacion_id=21, origen_destino_id=1, codigo_tabla=0,
            hrs_no_operativas=0, carga_piso=0, plantas=0, lenia_seca=0,
            carga_rollo=0, carga_lenia=0, coeficiente=1.0, altura=0.0, ancho=0.0,
            cantidad_estibas=0.0, largo_madera=0.0, carros=0, tarifa=0.0, tarifa_empresa=0.0,
            modificado=False, tabla="movimiento_carreton", periodo="202611",
            neto_origen=0, bruto_destino=0, tara_destino=0, neto_destino=0,
        ))
        self.db.commit()

        viaje = self._crear_viaje(lectura_camion=100, numero_remision="002-003-0000051")
        self.assertEqual(float(viaje.lectura_camion), 100)

    def test_un_movimiento_de_carreton_con_lectura_tampoco_entra_en_la_cadena(self):
        # El caso anterior cubre el carreton sin lectura. Este cubre el
        # peor: un movimiento de carreton que ademas traiga lectura y unidad.
        # El odometro del camion no se mueve con los viajes de carreton, asi
        # que esa fila no puede romper la monotonía del siguiente viaje.
        self.db.add(self.models.TableroProduccion(
            fecha=date(2026, 11, 8),
            unidad_negocio_id=1, empleado_id=1, equipo_id=10,
            hr_inicio=8000.0, hr_fin=9000.0, produccion=1000.0,
            unidad_produccion_id=7, remito=0, remito2=0, hora=time(8, 0), turno="dia",
            predio_id=1, tipo_operacion_id=21, origen_destino_id=1, codigo_tabla=0,
            hrs_no_operativas=0, carga_piso=0, plantas=0, lenia_seca=0,
            carga_rollo=0, carga_lenia=0, coeficiente=1.0, altura=0.0, ancho=0.0,
            cantidad_estibas=0.0, largo_madera=0.0, carros=0, tarifa=0.0, tarifa_empresa=0.0,
            modificado=False, tabla="movimiento_carreton", periodo="202611",
            neto_origen=0, bruto_destino=0, tara_destino=0, neto_destino=0,
            lectura_camion=500000, unidad_lectura="km",
        ))
        self.db.commit()

        viaje = self._crear_viaje(lectura_camion=100, numero_remision="002-003-0000052")
        self.assertEqual(float(viaje.lectura_camion), 100)

    def test_la_unidad_no_la_manda_el_cliente(self):
        # El schema de entrada no tiene campo de unidad: la resuelve el servidor
        # desde el equipo, asi que el cliente no puede elegirla.
        self.assertNotIn("unidad_lectura", self.schemas.RegistroViajeCreate.model_fields)
        registro = self._registro(lectura_camion=10, numero_remision="002-003-0000071")
        viaje = self.trip_service.create_trip(self.db, registro, self.empleado)
        self.assertEqual(viaje.unidad_lectura, "km")


class LecturaCamionHistorialTest(LecturaCamionBaseTest):
    def test_el_historial_expone_la_lectura_y_su_unidad(self):
        from fastapi.testclient import TestClient
        import main

        self._crear_viaje(lectura_camion=4321.5, numero_remision="002-003-0000081")

        main.app.dependency_overrides[main.get_db] = lambda: self.db
        main.app.dependency_overrides[main.get_current_user] = lambda: self.empleado
        client = TestClient(main.app)
        try:
            respuesta = client.get("/api/historial-viajes", params={
                "chofer_id": self.empleado.id,
                "fecha_desde": "2026-11-01",
                "fecha_hasta": "2026-11-30",
            })
            self.assertEqual(respuesta.status_code, 200)
            cuerpo = respuesta.json()
            self.assertEqual(len(cuerpo), 1)
            self.assertEqual(float(cuerpo[0]["lectura_camion"]), 4321.5)
            self.assertEqual(cuerpo[0]["unidad_lectura"], "km")
        finally:
            main.app.dependency_overrides.clear()

    def test_el_historial_de_un_viaje_sin_lectura_devuelve_null(self):
        from fastapi.testclient import TestClient
        import main

        self._crear_viaje(numero_remision="002-003-0000091")

        main.app.dependency_overrides[main.get_db] = lambda: self.db
        main.app.dependency_overrides[main.get_current_user] = lambda: self.empleado
        client = TestClient(main.app)
        try:
            respuesta = client.get("/api/historial-viajes", params={
                "chofer_id": self.empleado.id,
                "fecha_desde": "2026-11-01",
                "fecha_hasta": "2026-11-30",
            })
            self.assertEqual(respuesta.status_code, 200)
            cuerpo = respuesta.json()
            self.assertEqual(len(cuerpo), 1)
            self.assertIsNone(cuerpo[0]["lectura_camion"])
            self.assertIsNone(cuerpo[0]["unidad_lectura"])
        finally:
            main.app.dependency_overrides.clear()


class LecturaCamionEndpointTest(LecturaCamionBaseTest):
    def test_ultima_lectura_devuelve_la_lectura_del_ultimo_viaje(self):
        self._crear_viaje(lectura_camion=7777, numero_remision="002-003-0000061")

        from fastapi import HTTPException
        from fastapi.testclient import TestClient
        import main

        main.app.dependency_overrides[main.get_db] = lambda: self.db
        main.app.dependency_overrides[main.get_current_user] = lambda: self.empleado
        client = TestClient(main.app)
        try:
            respuesta = client.get("/api/registro-viaje/ultima-lectura", params={"equipo_id": 10})
            self.assertEqual(respuesta.status_code, 200)
            cuerpo = respuesta.json()
            self.assertEqual(cuerpo["equipo_id"], 10)
            self.assertEqual(float(cuerpo["lectura_camion"]), 7777.0)
            self.assertEqual(cuerpo["unidad_lectura"], "km")
            # Contrato exacto que consume el frontend: tipos de cada campo.
            self.assertIsInstance(cuerpo["equipo_id"], int)
            self.assertIsInstance(cuerpo["lectura_camion"], (int, float))
            self.assertIsInstance(cuerpo["unidad_lectura"], str)
            self.assertIsInstance(cuerpo["fecha"], str)
        finally:
            main.app.dependency_overrides.clear()

    def test_ultima_lectura_sin_viajes_devuelve_null(self):
        from fastapi.testclient import TestClient
        import main

        main.app.dependency_overrides[main.get_db] = lambda: self.db
        main.app.dependency_overrides[main.get_current_user] = lambda: self.empleado
        client = TestClient(main.app)
        try:
            respuesta = client.get("/api/registro-viaje/ultima-lectura", params={"equipo_id": 10})
            self.assertEqual(respuesta.status_code, 200)
            self.assertIsNone(respuesta.json())
        finally:
            main.app.dependency_overrides.clear()

    def test_app_version_expone_el_flag_de_exigencia(self):
        from fastapi.testclient import TestClient
        import main

        client = TestClient(main.app)
        respuesta = client.get("/api/app-version")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("exigir_lectura_camion", respuesta.json())
        self.assertIsInstance(respuesta.json()["exigir_lectura_camion"], bool)

    def test_flag_por_variable_de_entorno(self):
        import importlib
        import main

        original = os.environ.get("VIAJE_EXIGIR_LECTURA_CAMION")
        try:
            os.environ["VIAJE_EXIGIR_LECTURA_CAMION"] = "false"
            self.assertFalse(main.leer_flag_exigir_lectura_camion())
            os.environ["VIAJE_EXIGIR_LECTURA_CAMION"] = "0"
            self.assertFalse(main.leer_flag_exigir_lectura_camion())
            os.environ["VIAJE_EXIGIR_LECTURA_CAMION"] = "true"
            self.assertTrue(main.leer_flag_exigir_lectura_camion())
            os.environ.pop("VIAJE_EXIGIR_LECTURA_CAMION", None)
            self.assertTrue(main.leer_flag_exigir_lectura_camion())
        finally:
            if original is None:
                os.environ.pop("VIAJE_EXIGIR_LECTURA_CAMION", None)
            else:
                os.environ["VIAJE_EXIGIR_LECTURA_CAMION"] = original

    def test_ultima_lectura_devuelve_la_unidad_del_equipo(self):
        # El equipo con horometro (id=11) devuelve la unidad 'hs': el frontend
        # la usa para etiquetar el campo y no la inventa.
        self._crear_viaje(patente="HHS789", lectura_camion=88.25, numero_remision="002-003-0000101")

        from fastapi.testclient import TestClient
        import main

        main.app.dependency_overrides[main.get_db] = lambda: self.db
        main.app.dependency_overrides[main.get_current_user] = lambda: self.empleado
        client = TestClient(main.app)
        try:
            respuesta = client.get("/api/registro-viaje/ultima-lectura", params={"equipo_id": 11})
            self.assertEqual(respuesta.status_code, 200)
            cuerpo = respuesta.json()
            self.assertEqual(cuerpo["equipo_id"], 11)
            self.assertEqual(float(cuerpo["lectura_camion"]), 88.25)
            self.assertEqual(cuerpo["unidad_lectura"], "hs")
        finally:
            main.app.dependency_overrides.clear()

    def test_ultima_lectura_de_un_equipo_inexistente_devuelve_404(self):
        from fastapi.testclient import TestClient
        import main

        main.app.dependency_overrides[main.get_db] = lambda: self.db
        main.app.dependency_overrides[main.get_current_user] = lambda: self.empleado
        client = TestClient(main.app)
        try:
            respuesta = client.get("/api/registro-viaje/ultima-lectura", params={"equipo_id": 999})
            self.assertEqual(respuesta.status_code, 404)
        finally:
            main.app.dependency_overrides.clear()

    def test_el_flag_se_relee_en_cada_llamada(self):
        # El frontend consulta app-version en cada carga de la pantalla: si el
        # flag fuera una constante de modulo, cambiarlo en runtime no tendria
        # efecto y el formulario seguiria exigiendo la lectura.
        from fastapi.testclient import TestClient
        import main

        original = os.environ.get("VIAJE_EXIGIR_LECTURA_CAMION")
        client = TestClient(main.app)
        try:
            os.environ["VIAJE_EXIGIR_LECTURA_CAMION"] = "false"
            respuesta = client.get("/api/app-version")
            self.assertEqual(respuesta.status_code, 200)
            self.assertIs(respuesta.json()["exigir_lectura_camion"], False)

            os.environ["VIAJE_EXIGIR_LECTURA_CAMION"] = "true"
            respuesta = client.get("/api/app-version")
            self.assertEqual(respuesta.status_code, 200)
            self.assertIs(respuesta.json()["exigir_lectura_camion"], True)
        finally:
            if original is None:
                os.environ.pop("VIAJE_EXIGIR_LECTURA_CAMION", None)
            else:
                os.environ["VIAJE_EXIGIR_LECTURA_CAMION"] = original


if __name__ == "__main__":
    unittest.main()
