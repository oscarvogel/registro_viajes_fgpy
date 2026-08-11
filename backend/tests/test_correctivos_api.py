from datetime import date

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from correctivos import (
    CabOrdenServicioCorrectivo,
    DetOrdenServicioCorrectivo,
    MonedaCorrectivo,
    RepuestoCorrectivo,
    SectorCorrectivo,
    TipoTareaCorrectivo,
)
from correctivos_api import build_correctivos_router
from database import Base


@pytest.fixture()
def api_env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    session.add_all(
        [
            usuario,
            models.Empleado(
                id=8,
                nombre="Juan",
                apellido="Mecanico",
                email="juan@example.com",
                fecha_contratacion=date(2020, 1, 1),
                activo=True,
                porcentaje=0,
            ),
            models.Proveedor(id=20, razon_social="Gomeria Test", activo=True),
            models.Proveedor(id=21, razon_social="Taller Externo", activo=True),
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
            models.UnidadNegocio(id=1, descripcion="Transporte", activo=True),
            MonedaCorrectivo(id=1, descripcion="Guaranies", simbolo="Gs", cambio=1, activo=True),
            TipoTareaCorrectivo(id=3, tarea="Gomeria", descripcion="", activo=True),
            TipoTareaCorrectivo(id=4, tarea="Mecanica", descripcion="", activo=True),
            RepuestoCorrectivo(id=30, descripcion="Valvula", activo=True),
            SectorCorrectivo(id=2, descripcion="Taller", activo=True),
        ]
    )
    session.commit()

    def get_db():
        yield session

    def get_current_user():
        return session.get(models.Empleado, 7)

    app = FastAPI()
    app.include_router(build_correctivos_router(get_db, get_current_user), prefix="/api")
    client = TestClient(app)

    try:
        yield client, session
    finally:
        session.close()
        engine.dispose()


def payload_base(**overrides):
    payload = {
        "fecha": "2026-08-11",
        "equipo_id": 10,
        "km_hora": 185420,
        "descripcion": "Pinchadura cubierta trasera derecha",
        "externo": True,
        "proveedor_id": 20,
        "unidad_negocio_id": 1,
        "moneda_id": 1,
        "trabajos": [
            {
                "tipo_tarea_id": 3,
                "detalle": "Desarme, reparacion y montaje",
                "sector_id": 2,
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_catalogos_correctivos_devuelve_nombres_reales(api_env):
    client, _ = api_env
    response = client.get("/api/correctivos/catalogos")

    assert response.status_code == 200
    data = response.json()
    assert data["tareas"] == [
        {"id": 3, "descripcion": "Gomeria"},
        {"id": 4, "descripcion": "Mecanica"},
    ]
    assert data["proveedores"] == [
        {"id": 20, "descripcion": "Gomeria Test"},
        {"id": 21, "descripcion": "Taller Externo"},
    ]
    assert data["mecanicos"][0]["descripcion"] == "Mecanico Juan"
    assert data["equipos"][0]["patente"] == "AAPL657"


def test_post_correctivo_crea_cabecera_y_detalle(api_env):
    client, session = api_env
    response = client.post("/api/correctivos", json=payload_base())

    assert response.status_code == 201
    created = response.json()
    assert created["estado"] == "Cerrado"
    assert created["trabajos"] == 1
    cabecera = session.get(CabOrdenServicioCorrectivo, created["id"])
    assert cabecera.usuario == "Vogel Oscar"
    assert cabecera.proveedor == 20


def test_post_correctivo_rechaza_usuario_suplantado(api_env):
    client, _ = api_env
    payload = payload_base(usuario="otro")
    response = client.post("/api/correctivos", json=payload)
    assert response.status_code == 422


def test_post_correctivo_devuelve_400_para_proveedor_invalido(api_env):
    client, _ = api_env
    response = client.post("/api/correctivos", json=payload_base(proveedor_id=999))
    assert response.status_code == 400
    assert "Proveedor inexistente" in response.json()["detail"]


def test_get_correctivo_devuelve_trabajos(api_env):
    client, _ = api_env
    created = client.post("/api/correctivos", json=payload_base()).json()
    response = client.get(f"/api/correctivos/{created['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["patente"] == "AAPL657"
    assert data["trabajos"][0]["tipo_tarea"] == "Gomeria"
    assert data["trabajos"][0]["detalle"] == "Desarme, reparacion y montaje"


def test_historial_filtra_por_tipo_externo_y_proveedor(api_env):
    client, _ = api_env
    client.post("/api/correctivos", json=payload_base())
    client.post(
        "/api/correctivos",
        json=payload_base(
            descripcion="Ajuste de frenos interno",
            externo=False,
            proveedor_id=None,
            mecanico_id=8,
            trabajos=[{"tipo_tarea_id": 4, "detalle": "Regular frenos"}],
        ),
    )
    client.post(
        "/api/correctivos",
        json=payload_base(
            descripcion="Reparacion mecanica externa",
            proveedor_id=21,
            trabajos=[{"tipo_tarea_id": 4, "detalle": "Cambiar extremo"}],
        ),
    )

    por_tarea = client.get("/api/correctivos?tipo_tarea_id=3")
    internos = client.get("/api/correctivos?externo=false")
    por_proveedor = client.get("/api/correctivos?proveedor_id=21")

    assert por_tarea.status_code == 200
    assert len(por_tarea.json()) == 1
    assert por_tarea.json()[0]["descripcion"] == "Pinchadura cubierta trasera derecha"
    assert internos.status_code == 200
    assert len(internos.json()) == 1
    assert internos.json()[0]["externo"] is False
    assert por_proveedor.status_code == 200
    assert len(por_proveedor.json()) == 1
    assert por_proveedor.json()[0]["proveedor_id"] == 21


def test_historial_por_equipo_y_rango_invalido(api_env):
    client, _ = api_env
    client.post("/api/correctivos", json=payload_base())

    response = client.get("/api/equipos/10/correctivos")
    assert response.status_code == 200
    assert len(response.json()) == 1

    invalid = client.get("/api/correctivos?fecha_desde=2026-08-12&fecha_hasta=2026-08-11")
    assert invalid.status_code == 400


def test_router_exige_dependencia_de_autenticacion():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(bind=engine)
    session = Session()

    def get_db():
        yield session

    def deny_user():
        raise HTTPException(status_code=401, detail="No autenticado")

    app = FastAPI()
    app.include_router(build_correctivos_router(get_db, deny_user), prefix="/api")
    client = TestClient(app)

    try:
        response = client.get("/api/correctivos")
        assert response.status_code == 401
    finally:
        session.close()
        engine.dispose()
