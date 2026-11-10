"""Núcleo de correctivos/incidencias sobre órdenes de servicio legacy.

Subissue #29 del issue #27.

Este módulo mantiene aislada la lógica de negocio de correctivos para que la
integración HTTP del #30 no duplique reglas. Reutiliza las tablas existentes de
mantenimiento y no crea un historial paralelo.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, or_
from sqlalchemy.orm import Session, relationship

import models
from database import Base


ESTADO_CERRADO = "Cerrado"


class CorrectivoError(ValueError):
    """Error de validación de negocio del módulo de correctivos."""


class TipoTareaCorrectivo(Base):
    __tablename__ = "tipostareas"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    tarea = Column(String(150), nullable=False, default="")
    activo = Column(Boolean, nullable=False, default=True)
    descripcion = Column(Text, nullable=False, default="")


class RepuestoCorrectivo(Base):
    __tablename__ = "repuestos"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    descripcion = Column(String(150), nullable=False, default="")
    activo = Column(Boolean, nullable=False, default=True)


class MonedaCorrectivo(Base):
    __tablename__ = "monedas"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    descripcion = Column(String(100), nullable=False)
    simbolo = Column(String(10), nullable=False)
    cambio = Column(Float, nullable=False, default=1.0)
    activo = Column(Boolean, nullable=False, default=True)


class SectorCorrectivo(Base):
    __tablename__ = "sectores"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    descripcion = Column(String(80), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)


class CabOrdenServicioCorrectivo(Base):
    __tablename__ = "cab_orden_servicio"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    fecha = Column(Date, nullable=False)
    equipo_id = Column(Integer, ForeignKey("equipos.id"), nullable=False)
    descripcion = Column(Text, nullable=False, default="")
    estado = Column(String(20), nullable=False, default="Pendiente")
    cerrado_por = Column(String(30), nullable=False, default="")
    externo = Column(Boolean, nullable=False, default=False)
    proveedor = Column(Integer, nullable=False, default=0)
    mecanico = Column(Integer, nullable=False, default=0)
    unidad_negocio_id = Column(Integer, ForeignKey("unidades_negocio.id"), nullable=False)
    usuario = Column(String(30), nullable=False, default="")
    creado = Column(DateTime, nullable=False, default=datetime.utcnow)
    moneda_id = Column(Integer, ForeignKey("monedas.id"), nullable=False)
    cambio = Column(Float, nullable=False, default=1.0)
    orden_servicio = Column(String(12), nullable=False, default="")
    planilla_trabajo = Column(Boolean, nullable=False, default=False)
    checklist = Column(Boolean, nullable=False, default=False)

    equipo = relationship(models.Equipo)
    detalles = relationship(
        "DetOrdenServicioCorrectivo",
        back_populates="cabecera",
        cascade="save-update, merge",
    )


class DetOrdenServicioCorrectivo(Base):
    __tablename__ = "det_orden_servicio"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    cabecera_id = Column(Integer, ForeignKey("cab_orden_servicio.id"), nullable=False)
    tipo_tarea_id = Column(Integer, ForeignKey("tipostareas.id"), nullable=False)
    repuesto_id = Column(Integer, ForeignKey("repuestos.id"), nullable=True)
    cantidad = Column(Float, nullable=False, default=0)
    precio_unitario = Column(Float, nullable=False, default=0)
    preventivo = Column(Boolean, nullable=False, default=False)
    correctivo = Column(Boolean, nullable=False, default=True)
    realizado = Column(Boolean, nullable=False, default=True)
    km_hora = Column(Float, nullable=False, default=0)
    diferencia = Column(Float, nullable=False, default=0)
    detalle = Column(Text, nullable=False, default="")
    fecha_realizacion = Column(Date, nullable=True)
    mecanico = Column(Integer, nullable=False, default=0)
    moneda_id = Column(Integer, ForeignKey("monedas.id"), nullable=False)
    cambio = Column(Float, nullable=False, default=1.0)
    observaciones = Column(String(200), nullable=False, default="")
    hora_inicio = Column(Time, nullable=True)
    hora_fin = Column(Time, nullable=True)
    horas_extras = Column(Time, nullable=True)
    sector_id = Column(Integer, ForeignKey("sectores.id"), nullable=True)

    cabecera = relationship("CabOrdenServicioCorrectivo", back_populates="detalles")
    tipo_tarea = relationship("TipoTareaCorrectivo")
    repuesto = relationship("RepuestoCorrectivo")


class CorrectivoTrabajoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_tarea_id: int = Field(gt=0)
    detalle: str = Field(min_length=1, max_length=4000)
    repuesto_id: Optional[int] = Field(default=None, gt=0)
    cantidad: float = Field(default=0, ge=0)
    precio_unitario: float = Field(default=0, ge=0)
    observaciones: str = Field(default="", max_length=200)
    mecanico_id: Optional[int] = Field(default=None, gt=0)
    sector_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("detalle")
    @classmethod
    def detalle_no_vacio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El trabajo realizado no puede quedar vacío")
        return value


class CorrectivoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha: date
    equipo_id: int = Field(gt=0)
    km_hora: float = Field(ge=0)
    descripcion: str = Field(min_length=1, max_length=4000)
    externo: bool = False
    proveedor_id: Optional[int] = Field(default=None, gt=0)
    mecanico_id: Optional[int] = Field(default=None, gt=0)
    unidad_negocio_id: int = Field(gt=0)
    moneda_id: int = Field(gt=0)
    cambio: float = Field(default=1.0, gt=0)
    orden_servicio: str = Field(default="", max_length=12)
    trabajos: list[CorrectivoTrabajoCreate] = Field(min_length=1)

    @field_validator("descripcion")
    @classmethod
    def descripcion_no_vacia(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("La incidencia no puede quedar vacía")
        return value


class CorrectivoCreado(BaseModel):
    id: int
    estado: str
    trabajos: int


class CorrectivoHistorialItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: date
    equipo_id: int
    patente: str
    equipo: str
    descripcion: str
    externo: bool
    proveedor_id: Optional[int] = None
    mecanico_id: Optional[int] = None
    km_hora: float
    trabajos: list[str]


def _nombre_usuario(empleado: models.Empleado) -> str:
    """Nombre compacto compatible con los varchar(30) legacy."""
    texto = f"{empleado.apellido} {empleado.nombre}".strip()
    if not texto:
        texto = str(empleado.id)
    return texto[:30]


def _ids_activos(db: Session, model, ids: set[int]) -> set[int]:
    if not ids:
        return set()
    return {
        item.id
        for item in db.query(model)
        .filter(model.id.in_(ids), model.activo.is_(True))
        .all()
    }


def _validar_catalogos(db: Session, payload: CorrectivoCreate) -> None:
    equipo = (
        db.query(models.Equipo)
        .filter(models.Equipo.id == payload.equipo_id, models.Equipo.activo.is_(True))
        .first()
    )
    if not equipo:
        raise CorrectivoError("Equipo inexistente o inactivo")

    unidad = (
        db.query(models.UnidadNegocio)
        .filter(
            models.UnidadNegocio.id == payload.unidad_negocio_id,
            models.UnidadNegocio.activo.is_(True),
        )
        .first()
    )
    if not unidad:
        raise CorrectivoError("Unidad de negocio inexistente o inactiva")

    moneda = (
        db.query(MonedaCorrectivo)
        .filter(MonedaCorrectivo.id == payload.moneda_id, MonedaCorrectivo.activo.is_(True))
        .first()
    )
    if not moneda:
        raise CorrectivoError("Moneda inexistente o inactiva")

    if payload.externo:
        if not payload.proveedor_id:
            raise CorrectivoError("Un correctivo externo requiere proveedor")
        proveedor = (
            db.query(models.Proveedor)
            .filter(models.Proveedor.id == payload.proveedor_id, models.Proveedor.activo.is_(True))
            .first()
        )
        if not proveedor:
            raise CorrectivoError("Proveedor inexistente o inactivo")

    tarea_ids = {trabajo.tipo_tarea_id for trabajo in payload.trabajos}
    faltantes_tareas = tarea_ids - _ids_activos(db, TipoTareaCorrectivo, tarea_ids)
    if faltantes_tareas:
        raise CorrectivoError(f"Tipos de tarea inexistentes o inactivos: {sorted(faltantes_tareas)}")

    repuesto_ids = {trabajo.repuesto_id for trabajo in payload.trabajos if trabajo.repuesto_id}
    faltantes_repuestos = repuesto_ids - _ids_activos(db, RepuestoCorrectivo, repuesto_ids)
    if faltantes_repuestos:
        raise CorrectivoError(f"Repuestos inexistentes o inactivos: {sorted(faltantes_repuestos)}")

    sector_ids = {trabajo.sector_id for trabajo in payload.trabajos if trabajo.sector_id}
    faltantes_sectores = sector_ids - _ids_activos(db, SectorCorrectivo, sector_ids)
    if faltantes_sectores:
        raise CorrectivoError(f"Sectores inexistentes o inactivos: {sorted(faltantes_sectores)}")

    mecanico_ids = {trabajo.mecanico_id for trabajo in payload.trabajos if trabajo.mecanico_id}
    if payload.mecanico_id:
        mecanico_ids.add(payload.mecanico_id)
    if mecanico_ids:
        mecanicos_validos = {
            item.id
            for item in db.query(models.Empleado)
            .filter(models.Empleado.id.in_(mecanico_ids), models.Empleado.activo.is_(True))
            .all()
        }
        faltantes_mecanicos = mecanico_ids - mecanicos_validos
        if faltantes_mecanicos:
            raise CorrectivoError(f"Mecánicos inexistentes o inactivos: {sorted(faltantes_mecanicos)}")


def crear_correctivo(
    db: Session,
    payload: CorrectivoCreate,
    current_user: models.Empleado,
) -> CorrectivoCreado:
    """Crea cabecera + detalles en una única transacción.

    La identidad se recibe desde la capa autenticada. El contrato no admite
    campos `usuario` ni `cerrado_por` y cualquier error revierte la operación.
    """
    _validar_catalogos(db, payload)
    usuario = _nombre_usuario(current_user)

    try:
        cabecera = CabOrdenServicioCorrectivo(
            fecha=payload.fecha,
            equipo_id=payload.equipo_id,
            descripcion=payload.descripcion,
            estado=ESTADO_CERRADO,
            cerrado_por=usuario,
            externo=payload.externo,
            proveedor=(payload.proveedor_id or 0) if payload.externo else 0,
            mecanico=payload.mecanico_id or 0,
            unidad_negocio_id=payload.unidad_negocio_id,
            usuario=usuario,
            creado=datetime.utcnow(),
            moneda_id=payload.moneda_id,
            cambio=payload.cambio,
            orden_servicio=payload.orden_servicio.strip(),
            planilla_trabajo=False,
            checklist=False,
        )
        db.add(cabecera)
        db.flush()

        for trabajo in payload.trabajos:
            db.add(
                DetOrdenServicioCorrectivo(
                    cabecera_id=cabecera.id,
                    tipo_tarea_id=trabajo.tipo_tarea_id,
                    repuesto_id=trabajo.repuesto_id,
                    cantidad=trabajo.cantidad,
                    precio_unitario=trabajo.precio_unitario,
                    preventivo=False,
                    correctivo=True,
                    realizado=True,
                    km_hora=payload.km_hora,
                    diferencia=0,
                    detalle=trabajo.detalle,
                    fecha_realizacion=payload.fecha,
                    mecanico=trabajo.mecanico_id or payload.mecanico_id or 0,
                    moneda_id=payload.moneda_id,
                    cambio=payload.cambio,
                    observaciones=trabajo.observaciones.strip(),
                    sector_id=trabajo.sector_id,
                )
            )

        db.commit()
        db.refresh(cabecera)
        return CorrectivoCreado(id=cabecera.id, estado=cabecera.estado, trabajos=len(payload.trabajos))
    except Exception:
        db.rollback()
        raise


def listar_correctivos(
    db: Session,
    *,
    equipo_id: Optional[int] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    texto: Optional[str] = None,
    limite: int = 100,
) -> list[CorrectivoHistorialItem]:
    """Lista intervenciones con al menos un detalle correctivo."""
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
