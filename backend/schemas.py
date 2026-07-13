from pydantic import BaseModel, ConfigDict, field_validator, Field
from typing import Optional, List, Union
from datetime import date, time
from decimal import Decimal
import math

# --- Login & Token ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    documento: Optional[str] = None

class LoginRequest(BaseModel):
    documento: str

# --- Proveedor Shared ---
class ProveedorBase(BaseModel):
    razon_social: str
    direccion: Optional[str] = None
    cuit: Optional[str] = None

class Proveedor(ProveedorBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activo: bool


class ProveedorCatalogo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    razon_social: str
    activo: bool

# --- Cliente ---
class ClienteBase(BaseModel):
    razon_social: str
    direccion: Optional[str] = None
    cuit: Optional[str] = None

class Cliente(ClienteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activo: bool


class ClienteCatalogo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    razon_social: str
    activo: bool

# --- Empleado (Chofer) Shared ---
class EmpleadoBase(BaseModel):
    nombre: str
    apellido: str
    documento: Optional[str] = None

class Empleado(EmpleadoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activo: bool


class EmpleadoCatalogo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    apellido: str
    activo: bool

# --- Equipo (Camion) Shared ---
class EquipoBase(BaseModel):
    descripcion: str
    patente: str
    tipo_movil_id: int

class Equipo(EquipoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activo: bool

# --- Paniol (Tanques) ---
class PaniolBase(BaseModel):
    descripcion: str

class Paniol(PaniolBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activo: bool

# --- Unidad de Negocio ---
class UnidadNegocioBase(BaseModel):
    descripcion: Optional[str] = None
    prefijo: Optional[str] = None

class UnidadNegocio(UnidadNegocioBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activo: bool
    codigo_kobo: Optional[str] = None

# --- Registro de Viaje (Incoming from Frontend) ---
class RegistroViajeCreate(BaseModel):
    # Mapping fields from UI
    fecha_remision: date
    fecha_recepcion: date
    proveedor_id: Optional[int] = None # Using ID, UI will select from list
    numero_remision: str
    numero_remision_fpv: Optional[str] = None
    lote: Optional[str] = None
    
    peso_bruto_origen: Optional[float] = None # tn (now optional; frontend may send destino fields)
    tara_origen: Optional[float] = None # tn (now optional)
    neto_origen: float # tn
    neto_destino: float # tn
    peso_bruto_destino: float # tn
    tara_destino: Optional[float] = None # tn
    pesaje_unico: bool = False
    
    chofer_id: int
    patente: str # Or equipo_id if we map it
    unidad_negocio_id: int = 1
    cliente_id: Optional[int] = None
    
    observaciones: Optional[str] = None

    @field_validator(
        'peso_bruto_origen', 'tara_origen', 'neto_origen',
        'peso_bruto_destino', 'tara_destino', 'neto_destino',
    )
    @classmethod
    def reject_non_finite_weights(cls, value):
        if value is not None and not math.isfinite(value):
            raise ValueError('El peso debe ser un número finito')
        return value

    # Calculated or Default fields managed by Backend
    # produccion (net weight)
    # periodo
    # turno

# --- Response definition ---
class RegistroViajeResponse(BaseModel):
    id: int
    message: str = "Registro creado exitosamente"


class TripImageProposal(BaseModel):
    fecha_remision: date
    numero_remision_fpv: str = Field(pattern=r"^[0-9]{3}-[0-9]{3}-[0-9]{7}$")
    proveedor_id: Optional[int] = None
    proveedor_candidato: Optional[str] = None
    peso_bruto_destino: Decimal
    tara_destino: Decimal
    neto_destino: Decimal
    patente_observada: Optional[str] = None
    chofer_observado: Optional[str] = None
    confidence: dict[str, float]
    warnings: List[str]

    @field_validator('peso_bruto_destino', 'tara_destino', 'neto_destino')
    @classmethod
    def finite_proposal_weights(cls, value):
        if not value.is_finite():
            raise ValueError('El peso debe ser finito')
        return value

    @field_validator('confidence')
    @classmethod
    def valid_confidence(cls, value):
        if any(not math.isfinite(score) or score < 0 or score > 1 for score in value.values()):
            raise ValueError('La confianza debe estar entre 0 y 1')
        return value


class TripImageAnalysisResponse(BaseModel):
    upload_token: str
    proposal: TripImageProposal


class TripImageConfirmRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    upload_token: str
    fecha_remision: date
    fecha_recepcion: date
    numero_remision_fpv: str = Field(pattern=r"^[0-9]{3}-[0-9]{3}-[0-9]{7}$")
    proveedor_id: int
    patente: str
    unidad_negocio_id: int
    peso_bruto_destino: float
    tara_destino: float
    neto_destino: float
    observaciones: Optional[str] = None

    @field_validator('peso_bruto_destino', 'tara_destino', 'neto_destino')
    @classmethod
    def finite_confirm_weights(cls, value):
        if not math.isfinite(value):
            raise ValueError('El peso debe ser finito')
        return value


class TripImageConfirmResponse(BaseModel):
    viaje_id: int
    imagen_id: int

# --- Historial de Viajes (Outgoing to Frontend) ---
class HistorialViajeItem(BaseModel):
    id: int
    fecha: date
    produccion: float
    patente: str
    chofer: str
    remito_proveedor: Optional[str] = None
    remito_fgpy: Optional[str] = None
    observaciones: Optional[str] = None

# --- Movimiento de Combustible ---
class MovimientoCombustibleCreate(BaseModel):
    fecha_carga: date
    litros: float
    km_hora: float
    equipo_id: int
    paniol_id: Optional[int] = None
    proveedor_id: Optional[int] = None
    remito: str
    observaciones: Optional[str] = None
    usuario: Optional[str] = None

class MovimientoCombustibleResponse(BaseModel):
    id: int
    message: str = "Movimiento registrado OK"

class MovimientoCombustibleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: date
    equipo_id: int
    km_hora: float
    litros: float


class MovimientoCarretonCreate(BaseModel):
    fecha: Optional[date] = None
    equipo_id: int
    unidad_negocio_id: int
    hora_inicio_viaje: Optional[time] = None
    km_inicial: float
    km_final: float
    permitir_km_inicial_menor: bool = False
    estado_carga: str
    tipo_maquina_transportada: str
    usuario: Optional[str] = None
    origen_carreton: Optional[str] = Field(None, max_length=100)
    destino_carreton: Optional[str] = Field(None, max_length=100)


class MovimientoCarretonResponse(BaseModel):
    id: int
    message: str = "Movimiento de carretón registrado OK"


class MovimientoCarretonItem(BaseModel):
    id: int
    fecha: date
    patente: str
    unidad_negocio: Optional[str] = None
    hora_inicio_viaje: Optional[time] = None
    km_inicial: float
    km_final: float
    estado_carga: Optional[str] = None
    tipo_maquina_transportada: Optional[str] = None
    chofer: str
    origen_carreton: Optional[str] = None
    destino_carreton: Optional[str] = None


class MovimientoCarretonUltimoItem(BaseModel):
    id: int
    equipo_id: int
    fecha: date
    km_final: float
    hora_inicio_viaje: Optional[time] = None


# --- Client Logging (Frontend) ---
class ClientLogEntry(BaseModel):
    """Log entry enviado desde el frontend"""
    timestamp: str  # ISO format
    level: str  # 'info', 'warning', 'error', 'critical'
    message: str
    logger: str = "frontend"
    
    # Información del cliente (acepta tanto string como int para user_id)
    user_id: Optional[Union[str, int]] = None
    user_agent: Optional[str] = None
    screen_resolution: Optional[str] = None
    viewport_size: Optional[str] = None
    
    # Información del evento
    event_type: Optional[str] = None  # 'error', 'navigation', 'action', 'performance', etc.
    page: Optional[str] = None  # URL o ruta de la página
    component: Optional[str] = None  # Componente Vue
    
    # Detalles adicionales
    error_name: Optional[str] = None
    error_message: Optional[str] = None
    error_stack: Optional[str] = None
    
    # Métricas de rendimiento
    duration_ms: Optional[float] = None
    
    # Contexto adicional
    extra: Optional[dict] = None
    
    @field_validator('user_id')
    @classmethod
    def convert_user_id_to_str(cls, v):
        """Convierte user_id a string si es necesario"""
        if v is not None and not isinstance(v, str):
            return str(v)
        return v


class ClientLogBatch(BaseModel):
    """Batch de logs enviado desde el frontend"""
    logs: List[ClientLogEntry]
    device_info: Optional[dict] = None


class ClientLogResponse(BaseModel):
    """Respuesta al envío de logs"""
    success: bool
    message: str
    logs_received: int
    error_summary: Optional[dict] = None
    suggested_actions: Optional[List[str]] = None
