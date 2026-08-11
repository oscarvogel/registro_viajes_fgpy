"""Núcleo de correctivos/incidencias sobre las órdenes de servicio legacy.

Issue #27.

Este módulo encapsula el mapping mínimo de las tablas de mantenimiento ya
existentes y la lógica transaccional para registrar trabajos correctivos desde
la PWA sin crear un segundo historial paralelo.

La integración HTTP se realiza en un paso separado para mantener el cambio
revisable y no ampliar todavía más backend/main.py.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, or_
from sqlalchemy.orm import Session, relationship

import models
from database import Base


# Estados usados por el sistema FGPY existente (modelos/Mantenimientos.py y
# controladores/RegistroOrdenServicio.py). Una carga rápida representa un
# trabajo ya realizado y por eso se persiste cerrada.
ESTADO_CERRADO = "Cerrado"


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
    hora_inicio = Column(String(8), nullable=True)
    hora_fin = Column(String(8), nullable=True)
    horas_extras = Column(String(8), nullable=True)
    sector_id = Column(Integer, ForeignKey("sectores.id"), nullable=True)

    cabecera = relationship("CabOrdenServicioCorrectivo", back_populates="detalles")
    tipo_tarea = relationship("TipoTareaCorrectivo")
    repuesto = relationship("RepuestoCorrectivo")


class CorrectivoTrabajoCreate(BaseModel):
    tipo_tarea_id: int
    detalle: str = Field(min_length=1, max_length=4000)
    repuesto_id: Optional[int] = None
    cantidad: float = 0
    precio_unitario: float = 0
    observaciones: str = Field(default="", max_length=200)
    mecanico_id: Optional[int] = None
    sector_id: Optional[int] = None

    @field_validator("cantidad", "precio_unitario")
    @classmethod
    def no_negativos(cls, value: float) -> float:
        if value < 0:
            raise ValueError("No puede ser negativo")
        return value


class CorrectivoCreate(BaseModel):
    fecha: date
    equipo_id: int
    km_hora: float = Field(ge=0)
    descripcion: str = Field(min_length=1, max_length=4000)
    externo: bool = False
    proveedor_id: Optional[int] = None
    mecanico_id: Optional[int] = None
    unidad_negocio_id: int
    moneda_id: int
    cambio: float = Field(default=1.0, gt=0)
    orden_servicio: str = Field(default="", max_length=12)
    trabajos: list[CorrectivoTrabajoCreate] = Field(min_length=1)


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


def _validar_catalogos(db: Session, payload: CorrectivoCreate) -> None:
    equipo = (
        db.query(models.Equipo)
        .filter(models.Equipo.id == payload.equipo_id, models.Equipo.activo.is_(True))
        .first()
    )
    if not equipo:
        raise ValueError("Equipo inexistente o inactivo")

    unidad = (
        db.query(models.UnidadNegocio)
        .filter(
            models.UnidadNegocio.id == payload.unidad_negocio_id,
            models.UnidadNegocio.activo.is_(True),
        )
        .first()
    )
    if not unidad:
        raise ValueError("Unidad de negocio inexistente o inactiva")

    moneda = (
        db.query(MonedaCorrectivo)
        .filter(MonedaCorrectivo.id == payload.moneda_id, MonedaCorrectivo.activo.is_(True))
        .first()
    )
    if not moneda:
        raise ValueError("Moneda inexistente o inactiva")

    if payload.externo:
        if not payload.proveedor_id:
            raise ValueError("Un correctivo externo requiere proveedor")
        proveedor = (
            db.query(models.Proveedor)
            .filter(models.Proveedor.id == payload.proveedor_id, models.Proveedor.activo.is_(True))
            .first()
        )
        if not proveedor:
            raise ValueError("Proveedor inexistente o inactivo")

    tarea_ids = {trabajo.tipo_tarea_id for trabajo in payload.trabajos}
    tareas_validas = {
        item.id
        for item in db.query(TipoTareaCorrectivo)
        .filter(TipoTareaCorrectivo.id.in_(tarea_ids), TipoTareaCorrectivo.activo.is_(True))
        .all()
    }
    faltantes = tarea_ids - tareas_validas
    if faltantes:
        raise ValueError(f"Tipos de tarea inexistentes o inactivos: {sorted(faltantes)}")

    repuesto_ids = {trabajo.repuesto_id for trabajo in payload.trabajos if trabajo.repuesto_id}
    if repuesto_ids:
        repuestos_validos = {
            item.id
            for item in db.query(RepuestoCorrectivo)
            .filter(RepuestoCorrectivo.id.in_(repuesto_ids), RepuestoCorrectivo.activo.is_(True))
            .all()
        }
        faltantes_repuestos = repuesto_ids - repuestos_validos
        if faltantes_repuestos:
            raise ValueError(f"Repuestos inexistentes o inactivos: {sorted(faltantes_repuestos)}")


def crear_correctivo(
    db: Session,
    payload: CorrectivoCreate,
    current_user: models.Empleado,
) -> CorrectivoCreado:
    """Crea cabecera + detalles correctivos en una única transacción.

    El usuario siempre proviene de la sesión/JWT; el payload no permite enviar
    un campo usuario. Una excepción provoca rollback y evita cabeceras huérfanas.
    """
    _validar_catalogos(db, payload)
    usuario = _nombre_usuario(current_user)

    try:
        cabecera = CabOrdenServicioCorrectivo(
            fecha=payload.fecha,
            equipo_id=payload.equipo_id,
            descripcion=payload.descripcion.strip(),
            estado=ESTADO_CERRADO,
            cerrado_por=usuario,
            externo=payload.externo,
            proveedor=payload.proveedor_id or 0,
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
                    detalle=trabajo.detalle.strip(),
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
    """Lista intervenciones que contienen al menos un detalle correctivo."""
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
    if texto:
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
