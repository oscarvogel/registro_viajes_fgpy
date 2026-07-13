from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import models
from logger import set_request_context


NETO_MAX_TN = Decimal("200.0")
PESO_TOLERANCIA_TN = Decimal("0.010")
DB_WEIGHT_SCALE = Decimal("0.01")


def _decimal(name, value, *, allow_none=False):
    if value is None and allow_none:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Valor inválido o faltante: {name} debe ser numérico")
    if not result.is_finite():
        raise HTTPException(status_code=400, detail=f"Valor inválido: {name} debe ser finito")
    return result


def _quantize(value):
    return value.quantize(DB_WEIGHT_SCALE, rounding=ROUND_HALF_UP)


def _validate_remitos(db, registro):
    checks = (
        (registro.numero_remision, models.TableroProduccion.remito_proveedor, "El Nº Remito Proveedor ya existe"),
        (registro.numero_remision_fpv, models.TableroProduccion.remito_fgpy, "El Nº Remito FGPY ya existe"),
    )
    for value, column, message in checks:
        if value and db.query(models.TableroProduccion.id).filter(column == value).first():
            raise HTTPException(status_code=400, detail=message)


def _effective_employee(db, effective_user):
    employee_id = getattr(effective_user, "id", None)
    employee = db.query(models.Empleado).filter(models.Empleado.id == employee_id).first()
    if not employee or not employee.activo:
        raise HTTPException(status_code=400, detail="Usuario efectivo no encontrado o inactivo")
    return employee


def _equipment(db, raw_patente):
    patente = (raw_patente or "").strip().upper()
    if not patente:
        raise HTTPException(status_code=400, detail="Patente requerida")
    compact = patente.replace(" ", "")
    equipo = db.query(models.Equipo).filter(models.Equipo.patente == patente).first()
    if not equipo:
        equipo = db.query(models.Equipo).filter(
            func.replace(models.Equipo.patente, " ", "") == compact
        ).first()
    if not equipo or not equipo.activo:
        raise HTTPException(status_code=400, detail="Patente no encontrada")
    return equipo


def _catalogs(db, registro):
    unidad = db.query(models.UnidadNegocio).filter(
        models.UnidadNegocio.id == registro.unidad_negocio_id
    ).first()
    if not unidad or not unidad.activo:
        raise HTTPException(status_code=400, detail="Unidad de negocio no encontrada")

    proveedor_id = None
    if registro.proveedor_id is not None:
        proveedor = db.query(models.Proveedor).filter(models.Proveedor.id == registro.proveedor_id).first()
        if not proveedor or not proveedor.activo:
            raise HTTPException(status_code=400, detail="Proveedor no encontrado")
        proveedor_id = proveedor.id

    if registro.pesaje_unico:
        if proveedor_id is None:
            raise HTTPException(status_code=400, detail="Proveedor requerido para pesaje único")
        if registro.cliente_id is not None:
            raise HTTPException(status_code=400, detail="Cliente no permitido para pesaje único")
        cliente_id = None
    else:
        cliente_id = registro.cliente_id if registro.cliente_id is not None else 1
        cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
        if not cliente or not cliente.activo:
            raise HTTPException(status_code=400, detail="Cliente no encontrado")
    return proveedor_id, cliente_id


def _weights(registro):
    raw = {
        name: _decimal(name, getattr(registro, name), allow_none=True)
        for name in (
            "peso_bruto_origen", "tara_origen", "neto_origen",
            "peso_bruto_destino", "tara_destino", "neto_destino",
        )
    }
    destino_neto = raw["neto_destino"]
    if destino_neto <= 0 or destino_neto > NETO_MAX_TN:
        raise HTTPException(status_code=400, detail=f"Valor inválido: neto_destino debe ser > 0 y <= {NETO_MAX_TN} Tn")

    if registro.pesaje_unico:
        for name in ("peso_bruto_origen", "tara_origen", "neto_origen"):
            value = raw[name]
            if value is not None and value != 0:
                raise HTTPException(status_code=400, detail=f"{name} debe ser 0 o estar ausente para pesaje único")
        bruto = raw["peso_bruto_destino"]
        tara = raw["tara_destino"]
        for name, value in (("peso_bruto_destino", bruto), ("tara_destino", tara)):
            if value < 0 or value > NETO_MAX_TN:
                raise HTTPException(status_code=400, detail=f"Valor inválido: {name}")
        if bruto <= tara or abs(bruto - tara - destino_neto) > PESO_TOLERANCIA_TN:
            raise HTTPException(status_code=400, detail="Pesos de destino inconsistentes")
        bruto_db = _quantize(bruto)
        tara_db = _quantize(tara)
        neto_db = bruto_db - tara_db
        return Decimal("0.00"), bruto_db, tara_db, neto_db, neto_db

    origen_neto = raw["neto_origen"]
    if origen_neto <= 0 or origen_neto > NETO_MAX_TN:
        raise HTTPException(status_code=400, detail=f"Valor inválido: neto_origen debe ser > 0 y <= {NETO_MAX_TN} Tn")
    bruto = raw["peso_bruto_origen"]
    if bruto is None:
        bruto = raw["peso_bruto_destino"]
    tara = raw["tara_origen"]
    if tara is None:
        tara = raw["tara_destino"] or Decimal("0")
    origen_db = _quantize(origen_neto)
    return origen_db, _quantize(bruto), _quantize(tara), _quantize(destino_neto), origen_db


def _build_record(registro, employee, equipo, proveedor_id, cliente_id, weights):
    neto_origen, bruto, tara, neto_destino, produccion = weights
    return models.TableroProduccion(
        fecha=registro.fecha_remision, empleado_id=employee.id, equipo_id=equipo.id,
        produccion=produccion, remito=0, remito2=0,
        remito_proveedor=registro.numero_remision, remito_fgpy=registro.numero_remision_fpv,
        hora=datetime.now().time(), turno="dia", unidad_negocio_id=registro.unidad_negocio_id,
        cliente_id=cliente_id, predio_id=1,
        periodo=f"{registro.fecha_remision.year}{registro.fecha_remision.month:02d}",
        proveedor_id=proveedor_id, bruto_destino=bruto, tara_destino=tara,
        neto_origen=neto_origen, neto_destino=neto_destino, pesaje_unico=registro.pesaje_unico,
        hr_inicio=0.0, hr_fin=0.0, unidad_produccion_id=5, coeficiente=1.0,
        altura=0.0, ancho=0.0, cantidad_estibas=0.0, largo_madera=0.0,
        carros=0, plantas=0, hrs_no_operativas=0, carga_piso=0,
        tipo_operacion_id=21, lenia_seca=0, carga_rollo=0, carga_lenia=0,
        tarifa=0.0, tarifa_empresa=0.0, origen_destino_id=1, tabla=None,
        codigo_tabla=0, origen="", origen_carreton="", destino_carreton="",
        modificado=False, usuario=str(employee.id), observaciones=registro.observaciones,
    )


def create_trip(db: Session, registro, effective_user, commit=True):
    employee = _effective_employee(db, effective_user)
    _validate_remitos(db, registro)
    equipo = _equipment(db, registro.patente)
    set_request_context(chofer=f"{employee.apellido} {employee.nombre}")
    set_request_context(vehiculo=f"{equipo.patente} - {equipo.descripcion}")
    proveedor_id, cliente_id = _catalogs(db, registro)
    record = _build_record(
        registro, employee, equipo, proveedor_id, cliente_id, _weights(registro)
    )
    db.add(record)
    try:
        db.flush()
        if commit:
            db.commit()
            db.refresh(record)
        return record
    except SQLAlchemyError:
        if commit:
            db.rollback()
        raise
