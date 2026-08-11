"""API HTTP de correctivos/incidencias.

Subissue #30 del issue padre #27.

El router se construye mediante factory para reutilizar las dependencias de
sesion/autenticacion del backend sin importar ``main`` ni generar dependencias
circulares.
"""

from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from correctivos import (
    CabOrdenServicioCorrectivo,
    CorrectivoCreate,
    CorrectivoError,
    CorrectivoHistorialItem,
    DetOrdenServicioCorrectivo,
    MonedaCorrectivo,
    RepuestoCorrectivo,
    SectorCorrectivo,
    TipoTareaCorrectivo,
    crear_correctivo,
)


def _catalog_item(item, label_attr: str = "descripcion") -> dict:
    return {
        "id": item.id,
        "descripcion": str(getattr(item, label_attr, "") or ""),
    }


def _empleado_item(item: models.Empleado) -> dict:
    descripcion = " ".join(
        parte for parte in (item.apellido, item.nombre) if parte
    ).strip()
    return {"id": item.id, "descripcion": descripcion}


def _equipo_item(item: models.Equipo) -> dict:
    return {
        "id": item.id,
        "descripcion": item.descripcion or "",
        "patente": item.patente or "",
        "tipo_movil_id": item.tipo_movil_id,
        "ult_hr_km": float(item.ult_hr_km or 0),
    }


def _detalle_response(cabecera: CabOrdenServicioCorrectivo) -> dict:
    detalles = [detalle for detalle in cabecera.detalles if detalle.correctivo]
    return {
        "id": cabecera.id,
        "fecha": cabecera.fecha,
        "equipo_id": cabecera.equipo_id,
        "equipo": cabecera.equipo.descripcion if cabecera.equipo else "",
        "patente": cabecera.equipo.patente if cabecera.equipo else "",
        "descripcion": cabecera.descripcion,
        "estado": cabecera.estado,
        "externo": bool(cabecera.externo),
        "proveedor_id": cabecera.proveedor or None,
        "mecanico_id": cabecera.mecanico or None,
        "unidad_negocio_id": cabecera.unidad_negocio_id,
        "moneda_id": cabecera.moneda_id,
        "cambio": float(cabecera.cambio or 1),
        "orden_servicio": cabecera.orden_servicio or "",
        "usuario": cabecera.usuario or "",
        "cerrado_por": cabecera.cerrado_por or "",
        "trabajos": [
            {
                "id": detalle.id,
                "tipo_tarea_id": detalle.tipo_tarea_id,
                "tipo_tarea": detalle.tipo_tarea.tarea if detalle.tipo_tarea else "",
                "detalle": detalle.detalle or "",
                "repuesto_id": detalle.repuesto_id,
                "repuesto": detalle.repuesto.descripcion if detalle.repuesto else "",
                "cantidad": float(detalle.cantidad or 0),
                "precio_unitario": float(detalle.precio_unitario or 0),
                "km_hora": float(detalle.km_hora or 0),
                "fecha_realizacion": detalle.fecha_realizacion,
                "mecanico_id": detalle.mecanico or None,
                "moneda_id": detalle.moneda_id,
                "cambio": float(detalle.cambio or 1),
                "observaciones": detalle.observaciones or "",
                "sector_id": detalle.sector_id,
            }
            for detalle in sorted(detalles, key=lambda item: item.id or 0)
        ],
    }


def _listar_correctivos_api(
    db: Session,
    *,
    equipo_id: Optional[int] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    tipo_tarea_id: Optional[int] = None,
    externo: Optional[bool] = None,
    proveedor_id: Optional[int] = None,
    texto: Optional[str] = None,
    limite: int = 100,
) -> list[CorrectivoHistorialItem]:
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise CorrectivoError("Rango de fechas inválido")

    query = (
        db.query(CabOrdenServicioCorrectivo)
        .join(DetOrdenServicioCorrectivo)
        .filter(DetOrdenServicioCorrectivo.correctivo.is_(True))
    )
    if equipo_id is not None:
        query = query.filter(CabOrdenServicioCorrectivo.equipo_id == equipo_id)
    if fecha_desde is not None:
        query = query.filter(CabOrdenServicioCorrectivo.fecha >= fecha_desde)
    if fecha_hasta is not None:
        query = query.filter(CabOrdenServicioCorrectivo.fecha <= fecha_hasta)
    if tipo_tarea_id is not None:
        query = query.filter(DetOrdenServicioCorrectivo.tipo_tarea_id == tipo_tarea_id)
    if externo is not None:
        query = query.filter(CabOrdenServicioCorrectivo.externo.is_(externo))
    if proveedor_id is not None:
        query = query.filter(CabOrdenServicioCorrectivo.proveedor == proveedor_id)
    if texto and texto.strip():
        patron = f"%{texto.strip()}%"
        query = query.filter(
            or_(
                CabOrdenServicioCorrectivo.descripcion.ilike(patron),
                DetOrdenServicioCorrectivo.detalle.ilike(patron),
                DetOrdenServicioCorrectivo.observaciones.ilike(patron),
            )
        )

    cabeceras = (
        query.distinct()
        .order_by(CabOrdenServicioCorrectivo.fecha.desc(), CabOrdenServicioCorrectivo.id.desc())
        .limit(max(1, min(limite, 500)))
        .all()
    )
    resultado: list[CorrectivoHistorialItem] = []
    for cabecera in cabeceras:
        detalles = [detalle for detalle in cabecera.detalles if detalle.correctivo]
        km_hora = max((float(detalle.km_hora or 0) for detalle in detalles), default=0.0)
        resultado.append(
            CorrectivoHistorialItem(
                id=cabecera.id,
                fecha=cabecera.fecha,
                equipo_id=cabecera.equipo_id,
                patente=cabecera.equipo.patente if cabecera.equipo else "",
                equipo=cabecera.equipo.descripcion if cabecera.equipo else "",
                descripcion=cabecera.descripcion,
                externo=bool(cabecera.externo),
                proveedor_id=cabecera.proveedor or None,
                mecanico_id=cabecera.mecanico or None,
                km_hora=km_hora,
                trabajos=[detalle.detalle for detalle in detalles],
            )
        )
    return resultado


def build_correctivos_router(get_db: Callable, get_current_user: Callable) -> APIRouter:
    router = APIRouter(tags=["correctivos"])

    @router.get("/correctivos/catalogos")
    def catalogos_correctivos(
        db: Session = Depends(get_db),
        current_user: models.Empleado = Depends(get_current_user),
    ):
        tareas = db.query(TipoTareaCorrectivo).filter(TipoTareaCorrectivo.activo.is_(True)).order_by(TipoTareaCorrectivo.tarea.asc()).all()
        repuestos = db.query(RepuestoCorrectivo).filter(RepuestoCorrectivo.activo.is_(True)).order_by(RepuestoCorrectivo.descripcion.asc()).all()
        monedas = db.query(MonedaCorrectivo).filter(MonedaCorrectivo.activo.is_(True)).order_by(MonedaCorrectivo.descripcion.asc()).all()
        sectores = db.query(SectorCorrectivo).filter(SectorCorrectivo.activo.is_(True)).order_by(SectorCorrectivo.descripcion.asc()).all()
        proveedores = db.query(models.Proveedor).filter(models.Proveedor.activo.is_(True)).order_by(models.Proveedor.razon_social.asc()).all()
        mecanicos = db.query(models.Empleado).filter(models.Empleado.activo.is_(True)).order_by(models.Empleado.apellido.asc(), models.Empleado.nombre.asc()).all()
        equipos = db.query(models.Equipo).filter(models.Equipo.activo.is_(True)).order_by(models.Equipo.patente.asc(), models.Equipo.descripcion.asc()).all()
        unidades = db.query(models.UnidadNegocio).filter(models.UnidadNegocio.activo.is_(True)).order_by(models.UnidadNegocio.descripcion.asc()).all()

        return {
            "tareas": [_catalog_item(item, "tarea") for item in tareas],
            "repuestos": [_catalog_item(item) for item in repuestos],
            "monedas": [{**_catalog_item(item), "simbolo": item.simbolo or "", "cambio": float(item.cambio or 1)} for item in monedas],
            "sectores": [_catalog_item(item) for item in sectores],
            "proveedores": [_catalog_item(item, "razon_social") for item in proveedores],
            "mecanicos": [_empleado_item(item) for item in mecanicos],
            "equipos": [_equipo_item(item) for item in equipos],
            "unidades_negocio": [_catalog_item(item) for item in unidades],
        }

    @router.post("/correctivos", status_code=201)
    def registrar_correctivo(
        payload: CorrectivoCreate,
        db: Session = Depends(get_db),
        current_user: models.Empleado = Depends(get_current_user),
    ):
        try:
            return crear_correctivo(db, payload, current_user)
        except CorrectivoError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/correctivos")
    def consultar_correctivos(
        equipo_id: Optional[int] = Query(default=None, gt=0),
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        tipo_tarea_id: Optional[int] = Query(default=None, gt=0),
        externo: Optional[bool] = None,
        proveedor_id: Optional[int] = Query(default=None, gt=0),
        texto: Optional[str] = Query(default=None, max_length=200),
        limite: int = Query(default=100, ge=1, le=500),
        db: Session = Depends(get_db),
        current_user: models.Empleado = Depends(get_current_user),
    ):
        try:
            return _listar_correctivos_api(
                db,
                equipo_id=equipo_id,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                tipo_tarea_id=tipo_tarea_id,
                externo=externo,
                proveedor_id=proveedor_id,
                texto=texto,
                limite=limite,
            )
        except CorrectivoError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/correctivos/{correctivo_id}")
    def obtener_correctivo(
        correctivo_id: int,
        db: Session = Depends(get_db),
        current_user: models.Empleado = Depends(get_current_user),
    ):
        cabecera = db.query(CabOrdenServicioCorrectivo).filter(CabOrdenServicioCorrectivo.id == correctivo_id).first()
        if not cabecera or not any(detalle.correctivo for detalle in cabecera.detalles):
            raise HTTPException(status_code=404, detail="Correctivo no encontrado")
        return _detalle_response(cabecera)

    @router.get("/equipos/{equipo_id}/correctivos")
    def correctivos_por_equipo(
        equipo_id: int,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        tipo_tarea_id: Optional[int] = Query(default=None, gt=0),
        externo: Optional[bool] = None,
        proveedor_id: Optional[int] = Query(default=None, gt=0),
        texto: Optional[str] = Query(default=None, max_length=200),
        limite: int = Query(default=100, ge=1, le=500),
        db: Session = Depends(get_db),
        current_user: models.Empleado = Depends(get_current_user),
    ):
        equipo = db.query(models.Equipo).filter(models.Equipo.id == equipo_id, models.Equipo.activo.is_(True)).first()
        if not equipo:
            raise HTTPException(status_code=404, detail="Equipo inexistente o inactivo")
        try:
            return _listar_correctivos_api(
                db,
                equipo_id=equipo_id,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                tipo_tarea_id=tipo_tarea_id,
                externo=externo,
                proveedor_id=proveedor_id,
                texto=texto,
                limite=limite,
            )
        except CorrectivoError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
