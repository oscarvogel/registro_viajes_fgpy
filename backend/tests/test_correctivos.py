from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from correctivos import (
    ESTADO_CERRADO,
    CorrectivoCreate,
    CorrectivoTrabajoCreate,
    _nombre_usuario,
)


def test_correctivo_requiere_al_menos_un_trabajo():
    with pytest.raises(ValidationError):
        CorrectivoCreate(
            fecha=date(2026, 8, 11),
            equipo_id=10,
            km_hora=1000,
            descripcion="Pinchadura",
            unidad_negocio_id=1,
            moneda_id=1,
            trabajos=[],
        )


def test_correctivo_no_acepta_importes_negativos():
    with pytest.raises(ValidationError):
        CorrectivoTrabajoCreate(
            tipo_tarea_id=1,
            detalle="Reparar cubierta",
            cantidad=1,
            precio_unitario=-1,
        )


def test_correctivo_no_expone_usuario_en_payload():
    payload = CorrectivoCreate(
        fecha=date(2026, 8, 11),
        equipo_id=10,
        km_hora=1000,
        descripcion="Pinchadura",
        unidad_negocio_id=1,
        moneda_id=1,
        trabajos=[
            CorrectivoTrabajoCreate(
                tipo_tarea_id=3,
                detalle="Desarme, reparación y montaje",
            )
        ],
    )

    assert "usuario" not in payload.model_fields
    assert "cerrado_por" not in payload.model_fields


def test_nombre_usuario_legacy_se_limita_a_30_caracteres():
    empleado = SimpleNamespace(
        id=7,
        apellido="ApellidoMuyLargoParaRegistroLegacy",
        nombre="NombreTambiénMuyLargo",
    )

    usuario = _nombre_usuario(empleado)

    assert len(usuario) <= 30
    assert usuario.startswith("Apellido")


def test_carga_rapida_se_define_como_cerrada():
    assert ESTADO_CERRADO == "Cerrado"
