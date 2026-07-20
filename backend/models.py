from datetime import datetime

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Date, Float, Text, Time, DECIMAL, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base

class Empleado(Base):
    __tablename__ = "empleados"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(50), nullable=False)
    email = Column(String(100), nullable=False)
    telefono = Column(String(80))
    direccion = Column(String(255))
    documento = Column(String(15)) # DNI for login
    fecha_contratacion = Column(Date, nullable=False)
    fecha_nacimiento = Column(Date)
    fecha_baja = Column(Date)
    activo = Column(Boolean, nullable=False, default=True)
    observaciones = Column(Text)
    porcentaje = Column(Float, nullable=False, default=0.0)
    codigo_kobo = Column(String(50))

class Proveedor(Base):
    __tablename__ = "proveedor"

    id = Column(Integer, primary_key=True, index=True)
    razon_social = Column(String(100), nullable=False, unique=True)
    direccion = Column(String(100))
    telefono = Column(String(20))
    cuit = Column(String(20), unique=True)
    contacto = Column(String(100))
    activo = Column(Boolean, nullable=False, default=True)
    observaciones = Column(Text)


class Cliente(Base):
    __tablename__ = "cliente"

    id = Column(Integer, primary_key=True, index=True)
    razon_social = Column(String(100), nullable=False, unique=True)
    direccion = Column(String(100))
    telefono = Column(String(20))
    cuit = Column(String(20), unique=True)
    contacto = Column(String(100))
    activo = Column(Boolean, nullable=False, default=True)
    observaciones = Column(Text)

class Equipo(Base):
    __tablename__ = "equipos" # Camiones

    id = Column(Integer, primary_key=True, index=True)
    descripcion = Column(String(100), nullable=False)
    patente = Column(String(10), nullable=False)
    nro_chasis = Column(String(30), nullable=False)
    nro_motor = Column(String(30), nullable=False)
    capacidad_tanque = Column(DECIMAL(10, 2))
    fecha_adquisicion = Column(Date)
    fecha_baja = Column(Date)
    tipo_movil_id = Column(Integer, nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    observaciones = Column(Text)
    movil_asociado = Column(Integer, nullable=False)
    codigo_kobo = Column(String(50))
    ult_hr_km = Column(DECIMAL(10, 2), nullable=False, default=0.0)

class UnidadNegocio(Base):
    __tablename__ = "unidades_negocio"

    id = Column(Integer, primary_key=True, index=True)
    descripcion = Column(Text)
    prefijo = Column(String(10))
    activo = Column(Boolean, nullable=False)
    codigo_kobo = Column(String(50), unique=True)

class Paniol(Base):
    __tablename__ = "panioles"

    id = Column(Integer, primary_key=True, index=True)
    descripcion = Column(String(100), nullable=False, unique=True)
    activo = Column(Boolean, nullable=False, default=True)
    unidad_negocio_id = Column(Integer, ForeignKey("unidades_negocio.id"), nullable=False, default=1)
    unidad_negocio = relationship("UnidadNegocio")

class TableroProduccion(Base):
    __tablename__ = "tablero_produccion"
    __table_args__ = (
        UniqueConstraint(
            "remito_proveedor",
            name="uq_tablero_produccion_remito_proveedor",
        ),
        UniqueConstraint(
            "remito_fgpy",
            name="uq_tablero_produccion_remito_fgpy",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False)
    unidad_negocio_id = Column(Integer, ForeignKey("unidades_negocio.id"), nullable=False)  # Context specific
    unidad_negocio = relationship("UnidadNegocio")
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    equipo_id = Column(Integer, ForeignKey("equipos.id"), nullable=False)
    
    hr_inicio = Column(Float, nullable=False, default=0)
    hr_fin = Column(Float, nullable=False, default=0)
    produccion = Column(DECIMAL(10, 2), nullable=False) # Net weight logic
    unidad_produccion_id = Column(Integer, nullable=False, default=0)
    
    observaciones = Column(Text)
    coeficiente = Column(DECIMAL(10, 2), nullable=False, default=1.0)
    altura = Column(DECIMAL(10, 2), nullable=False, default=0.0)
    ancho = Column(DECIMAL(10, 2), nullable=False, default=0.0)
    cantidad_estibas = Column(DECIMAL(10, 2), nullable=False, default=0.0)
    largo_madera = Column(DECIMAL(10, 2), nullable=False, default=0.0)
    
    remito = Column(Integer, nullable=False) # Internal Remito? Or Remito Proveedor number mapped here?
    carros = Column(Integer, nullable=False, default=0)
    hora = Column(Time, nullable=False)
    turno = Column(String(10), nullable=False)
    
    cliente_id = Column(Integer, nullable=True)
    pesaje_unico = Column(Boolean, nullable=False, default=False)
    proveedor_id = Column(Integer, ForeignKey("proveedor.id"), nullable=True)
    proveedor = relationship("Proveedor")
    plantas = Column(Integer, nullable=False, default=0)
    predio_id = Column(Integer, nullable=False)
    hrs_no_operativas = Column(Integer, nullable=False, default=0)
    carga_piso = Column(Integer, nullable=False, default=0)
    tipo_operacion_id = Column(Integer, nullable=False, default=1)
    
    lenia_seca = Column(Integer, nullable=False, default=0)
    carga_rollo = Column(Integer, nullable=False, default=0)
    carga_lenia = Column(Integer, nullable=False, default=0)
    
    fecha_corte = Column(Date)
    periodo = Column(String(6), nullable=False) # YYYYMM
    tarifa = Column(Float, nullable=False, default=0.0)
    tarifa_empresa = Column(Float, nullable=False, default=0.0)
    
    origen_destino_id = Column(Integer, nullable=False)
    tabla = Column(String(50))
    codigo_tabla = Column(Integer, nullable=False, default=0)
    origen = Column(String(80))
    
    remito2 = Column(Integer, nullable=False, default=0) # Maybe Remito FPV?
    modificado = Column(Boolean, nullable=False, default=False)
    usuario = Column(String(50))
    
    remito_proveedor = Column(String(20))
    remito_fgpy = Column(String(20))
    
    hora_inicio_viaje = Column(Time)
    hora_fin_viaje = Column(Time)

    origen_carreton = Column(String(100))
    destino_carreton = Column(String(100))

    neto_origen = Column(DECIMAL(10, 2), nullable=False, default=0.0)
    bruto_destino = Column(DECIMAL(10, 2), nullable=False, default=0.0)
    tara_destino = Column(DECIMAL(10, 2), nullable=False, default=0.0)

    neto_destino = Column(DECIMAL(10, 2), nullable=False, default=0.0)
    # Relationships
    empleado = relationship("Empleado")
    equipo = relationship("Equipo")
    imagenes = relationship("ViajeImagen", back_populates="viaje")


class ViajeImagen(Base):
    __tablename__ = "viaje_imagenes"

    id = Column(Integer, primary_key=True, index=True)
    viaje_id = Column(Integer, ForeignKey("tablero_produccion.id"), nullable=False, index=True)
    storage_path = Column(String(500), nullable=False)
    original_name = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)

    viaje = relationship("TableroProduccion", back_populates="imagenes")

class MovimientoCombustible(Base):
    __tablename__ = "movimientocombustible"

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False)
    tipo_combustible_id = Column(Integer, nullable=False)
    equipo_id = Column(Integer, ForeignKey("equipos.id"), nullable=False)
    km_hora = Column(Float, nullable=False)
    precio_litro = Column(DECIMAL(10, 2), nullable=False)
    ingreso = Column(DECIMAL(10, 2), nullable=False)
    egreso = Column(DECIMAL(10, 2), nullable=False)
    unidad_negocio_id = Column(Integer, nullable=False)
    paniol_id = Column(Integer, ForeignKey("panioles.id"), nullable=True)
    remito = Column(String(12), nullable=False)
    idtabla = Column(Integer, nullable=False)
    tabla = Column(String(30), nullable=False)
    usuario = Column(String(30), nullable=False)
    fecha_grabacion = Column(DateTime, nullable=False)
    observaciones = Column(Text)
    proveedor_id = Column(Integer, ForeignKey("proveedor.id"), nullable=True)
    periodo = Column(String(6), nullable=False)
    remito2 = Column(String(12), nullable=False)

    equipo = relationship("Equipo")
    paniol = relationship("Paniol")
    proveedor = relationship("Proveedor")


class ClientLogSummary(Base):
    __tablename__ = "client_log_summary"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, nullable=False, index=True)
    summary_json = Column(Text, nullable=False)
    suggested_actions_json = Column(Text, nullable=False)
    samples_json = Column(Text, nullable=False)
