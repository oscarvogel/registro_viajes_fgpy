from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import models
from correctivos import (
    ESTADO_CERRADO,
    CabOrdenServicioCorrectivo,
    CorrectivoCreate,
    CorrectivoError,
    CorrectivoTrabajoCreate,
    DetOrdenServicioCorrectivo,
    MonedaCorrectivo,
    RepuestoCorrectivo,
    SectorCorrectivo,
    TipoTareaCorrectivo,
    _nombre_usuario,
    crear_correctivo,
    listar_correctivos,
)
from database import Base


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    tables = [
        models.Empleado.__table__,
        models.Proveedor.__table__,
        models.Equipo.__table__,
        models.UnidadNegocio.__table__,
        MonedaCorrectivo.__table__,
        TipoTareaCorrectivo.__table__,
        RepuestoCorrectivo.__table__,
        SectorCorrectivo.__table__,
        CabOrdenServicioCorrectivo.__table__,
        DetOrdenServicioCorrectivo.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()

    usuario = models.Empleado(
        id=7,
        nombre="Oscar",
        apellido="Vogel",
        email="oscar@example.com",
        fecha_contratacion=date(2020, 1, 1),
        activo=True,
        porcentaje=0,
    )
    mecanico = models.Empleado(
        id=8,
        nombre="Juan",
        apellido="Mecanico",
        email="juan@example.com",
        fecha_contratacion=date(2020, 1, 1),
        activo=True,
        porcentaje=0,
    )
    session.add_all(
        [
            usuario,
            mecanico,
            models.Proveedor(id=20, razon_social="Gomeria Test", activo=True),
            models.Equipo(
                id=10,
                descripcion="CAMION KIA",
                patente="AAPL657",
                nro_chasis="CHASIS10",
                nro_motor="MOTOR10",
                tipo_movil_id=1,
                activo=True,
                movil_asociado=0,
                ult_hr_km=185000,
            ),
            models.Equipo(
                id=11,
                descripcion="CAMION 2",
                patente="BBBB111",
                nro_chasis="CHASIS11",
                nro_motor="MOTOR11",
                tipo_movil_id=1,
                activo=True,
                movil_asociado=0,
                ult_hr_km=90000,
            ),
            models.UnidadNegocio(id=1, descripcion="Transporte", activo=True),
            MonedaCorrectivo(id=1, descripcion="Guaranies", simbolo="Gs", cambio=1, activo=True),
            TipoTareaCorrectivo(id=3, tarea="Gomeria", descripcion="", activo=True),
            TipoTareaCorrectivo(id=4, tarea="Mecanica", descripcion="", activo=True),
            RepuestoCorrectivo(id=30, descripcion="Valvula", activo=True),
            SectorCorrectivo(id=2, descripcion="Taller", activo=True),
        ]
    )
    session.commit()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def payload_base(**overrides):
    data = {
        "fecha": date(2026, 8, 11),
        "equipo_id": 10,
        "km_hora": 185420,
        "descripcion": "Pinchadura cubierta trasera derecha",
        "externo": True,
        "proveedor_id": 20,
        "unidad_negocio_id": 1,
        "moneda_id": 1,
        "trabajos": [
            CorrectivoTrabajoCreate(
                tipo_tarea_id=3,
                detalle="Desarme, reparacion y montaje",
                sector_id=2,
            )
        ],
    }
    data.update(overrides)
    return CorrectivoCreate(**data)


def test_correctivo_requiere_al_menos_un_trabajo():
    with pytest.raises(ValidationError):
        payload_base(trabajos=[])


def test_correctivo_no_acepta_importes_negativos():
    with pytest.raises(ValidationError):
        CorrectivoTrabajoCreate(
            tipo_tarea_id=1,
            detalle="Reparar cubierta",
            cantidad=1,
            precio_unitario=-1,
        )


def test_correctivo_rechaza_identidad_en_payload():
    with pytest.raises(ValidationError):
        CorrectivoCreate(
            fecha=date(2026, 8, 11),
            equipo_id=10,
            km_hora=1000,
            descripcion="Pinchadura",
            unidad_negocio_id=1,
            moneda_id=1,
            usuario="otro_usuario",
            trabajos=[
                CorrectivoTrabajoCreate(
                    tipo_tarea_id=3,
                    detalle="Desarme, reparacion y montaje",
                )
            ],
        )


def test_nombre_usuario_legacy_se_limita_a_30_caracteres():
    empleado = SimpleNamespace(
        id=7,
        apellido="ApellidoMuyLargoParaRegistroLegacy",
        nombre="NombreTambienMuyLargo",
    )
    usuario = _nombre_usuario(empleado)
    assert len(usuario) <= 30
    assert usuario.startswith("Apellido")


def test_carga_rapida_se_define_como_cerrada():
    assert ESTADO_CERRADO == "Cerrado"


def test_crear_correctivo_externo_persiste_cabecera_y_detalle(db):
    usuario = db.get(models.Empleado, 7)
    result = crear_correctivo(db, payload_base(), usuario)

    cabecera = db.get(CabOrdenServicioCorrectivo, result.id)
    detalles = (
        db.query(DetOrdenServicioCorrectivo)
        .filter(DetOrdenServicioCorrectivo.cabecera_id == result.id)
        .all()
    )

    assert result.estado == "Cerrado"
    assert result.trabajos == 1
    assert cabecera.estado == "Cerrado"
    assert cabecera.usuario == "Vogel Oscar"
    assert cabecera.cerrado_por == "Vogel Oscar"
    assert cabecera.proveedor == 20
    assert len(detalles) == 1
    assert detalles[0].correctivo is True
    assert detalles[0].preventivo is False
    assert detalles[0].realizado is True
    assert detalles[0].fecha_realizacion == date(2026, 8, 11)
    assert detalles[0].km_hora == 185420


def test_correctivo_admite_multiples_trabajos_y_repuesto(db):
    usuario = db.get(models.Empleado, 7)
    payload = payload_base(
        externo=False,
        proveedor_id=None,
        mecanico_id=8,
        descripcion="Trabajo de tren delantero",
        trabajos=[
            CorrectivoTrabajoCreate(tipo_tarea_id=4, detalle="Cambiar extremo", repuesto_id=30, cantidad=1),
            CorrectivoTrabajoCreate(tipo_tarea_id=4, detalle="Alinear tren delantero"),
            CorrectivoTrabajoCreate(tipo_tarea_id=3, detalle="Rotar cubiertas"),
        ],
    )

    result = crear_correctivo(db, payload, usuario)
    cabecera = db.get(CabOrdenServicioCorrectivo, result.id)
    detalles = db.query(DetOrdenServicioCorrectivo).filter_by(cabecera_id=result.id).all()

    assert result.trabajos == 3
    assert cabecera.externo is False
    assert cabecera.proveedor == 0
    assert cabecera.mecanico == 8
    assert len(detalles) == 3
    assert detalles[0].repuesto_id == 30
    assert all(detalle.correctivo for detalle in detalles)


def test_correctivo_externo_requiere_proveedor(db):
    usuario = db.get(models.Empleado, 7)
    with pytest.raises(CorrectivoError, match="requiere proveedor"):
        crear_correctivo(db, payload_base(proveedor_id=None), usuario)


def test_correctivo_rechaza_sector_inexistente(db):
    usuario = db.get(models.Empleado, 7)
    payload = payload_base(
        trabajos=[CorrectivoTrabajoCreate(tipo_tarea_id=3, detalle="Trabajo", sector_id=999)]
    )
    with pytest.raises(CorrectivoError, match="Sectores inexistentes"):
        crear_correctivo(db, payload, usuario)


def test_correctivo_rechaza_mecanico_inexistente(db):
    usuario = db.get(models.Empleado, 7)
    with pytest.raises(CorrectivoError, match="Mecánicos inexistentes"):
        crear_correctivo(db, payload_base(mecanico_id=999), usuario)


def test_falla_en_detalle_hace_rollback_completo(db):
    usuario = db.get(models.Empleado, 7)
    payload = payload_base(
        trabajos=[
            CorrectivoTrabajoCreate(tipo_tarea_id=3, detalle="Primer trabajo"),
            CorrectivoTrabajoCreate(tipo_tarea_id=3, detalle="FALLAR"),
        ]
    )

    def fallar_segundo_detalle(mapper, connection, target):
        if target.detalle == "FALLAR":
            raise RuntimeError("fallo simulado en detalle")

    event.listen(DetOrdenServicioCorrectivo, "before_insert", fallar_segundo_detalle)
    try:
        with pytest.raises(RuntimeError, match="fallo simulado"):
            crear_correctivo(db, payload, usuario)
    finally:
        event.remove(DetOrdenServicioCorrectivo, "before_insert", fallar_segundo_detalle)

    assert db.query(CabOrdenServicioCorrectivo).count() == 0
    assert db.query(DetOrdenServicioCorrectivo).count() == 0


def test_listar_correctivos_filtra_por_equipo_y_texto(db):
    usuario = db.get(models.Empleado, 7)
    crear_correctivo(db, payload_base(descripcion="Pinchadura rueda trasera"), usuario)
    crear_correctivo(
        db,
        payload_base(
            equipo_id=11,
            descripcion="Problema electrico",
            trabajos=[CorrectivoTrabajoCreate(tipo_tarea_id=4, detalle="Revisar alternador")],
        ),
        usuario,
    )

    por_equipo = listar_correctivos(db, equipo_id=10)
    por_texto = listar_correctivos(db, texto="alternador")

    assert len(por_equipo) == 1
    assert por_equipo[0].equipo_id == 10
    assert por_equipo[0].patente == "AAPL657"
    assert len(por_texto) == 1
    assert por_texto[0].equipo_id == 11


def test_listar_correctivos_rechaza_rango_invertido(db):
    with pytest.raises(CorrectivoError, match="Rango de fechas"):
        listar_correctivos(
            db,
            fecha_desde=date(2026, 8, 12),
            fecha_hasta=date(2026, 8, 11),
        )
