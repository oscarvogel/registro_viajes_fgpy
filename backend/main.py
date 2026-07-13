from fastapi import FastAPI, Depends, HTTPException, status, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError, DataError, SQLAlchemyError
from typing import List, Optional
from datetime import datetime, date, time, timedelta, timezone
from pathlib import Path
from contextlib import asynccontextmanager
import time as time_module
import os
import logging
import jwt
import json
import unicodedata

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration

import models, schemas, database
from logger import app_logger, log_api_request, log_user_action, log_system_event, sanitize_for_logging, set_request_context, clear_request_context
# Initialize Sentry as early as possible

# Configure logging integration: breadcrumbs at INFO, events at ERROR
sentry_logging = LoggingIntegration(
    level=logging.INFO,
    event_level=logging.ERROR,
)

def _before_send(event, hint):
    # Minimal sanitization: redact common sensitive fields in request data and extras
    try:
        request = event.get('request') or {}
        # redact auth header if present
        headers = request.get('headers') or {}
        if isinstance(headers, dict):
            if 'Authorization' in headers:
                headers['Authorization'] = 'REDACTED'
            request['headers'] = headers

        # sanitize form/body
        data = request.get('data')
        if data:
            request['data'] = sanitize_for_logging(data)
            event['request'] = request

        # sanitize extra
        if 'extra' in event:
            event['extra'] = sanitize_for_logging(event['extra'])
    except Exception:
        pass

    return event


sentry_sdk.init(
    dsn=os.getenv('SENTRY_DSN'),
    integrations=[sentry_logging, StarletteIntegration(), FastApiIntegration()],
    environment=os.getenv('SENTRY_ENV', os.getenv('APP_ENV', 'development')),
    release=os.getenv('SENTRY_RELEASE'),
    send_default_pii=False,
    traces_sample_rate=0.0,
    before_send=_before_send,
)
from scheduler import task_scheduler
from email_service import email_service


DEFAULT_CORS_ORIGINS = [
    "https://viajes.forestalparaguay.com",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]


def parse_cors_origins(value: Optional[str] = None) -> List[str]:
    raw_value = value if value is not None else os.getenv("CORS_ORIGINS")
    if not raw_value:
        return DEFAULT_CORS_ORIGINS

    return [origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip()]


ALLOWED_CORS_ORIGINS = parse_cors_origins()


def apply_allowed_cors_header(request: Request, response):
    origin = request.headers.get("origin")
    if origin in ALLOWED_CORS_ORIGINS:
        response.headers.setdefault("Access-Control-Allow-Origin", origin)
        response.headers.setdefault("Vary", "Origin")
    return response


def parse_admin_user_ids(value: Optional[str] = None) -> set[int]:
    raw_value = value if value is not None else os.getenv("ADMIN_USER_IDS", "")
    admin_ids: set[int] = set()

    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            admin_ids.add(int(item))
        except ValueError:
            app_logger.warning(f"ADMIN_USER_IDS contiene un valor invalido: {item}")

    return admin_ids

# Validation limits
NETO_MAX_TN = 200.0  # maximum reasonable net weight in Tn for a single trip
ENABLE_ERROR_ALERT_EMAILS = os.getenv("ENABLE_ERROR_ALERT_EMAILS", "true").lower() in ("1", "true", "yes", "on")
DEFAULT_FUEL_PROVEEDOR_ID = os.getenv("DEFAULT_FUEL_PROVEEDOR_ID")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))
AUTH_ENFORCEMENT_MODE = os.getenv("AUTH_ENFORCEMENT_MODE", "compat").lower()
LOGIN_RATE_LIMIT_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "900"))
LOGIN_RATE_LIMIT_LOCKOUT_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_LOCKOUT_SECONDS", "900"))
LOGIN_INVALID_DETAIL = "Credenciales invalidas"
_login_failed_attempts = {}


def get_client_ip(request: Optional[Request]) -> str:
    if request is None:
        return "local"

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"


def _login_rate_key(documento: str, client_ip: str) -> tuple:
    return (client_ip or "unknown", documento or "")


def _cleanup_login_attempts(now: float) -> None:
    expired_keys = [
        key for key, attempts in _login_failed_attempts.items()
        if not attempts or attempts[-1] <= now - LOGIN_RATE_LIMIT_LOCKOUT_SECONDS
    ]
    for key in expired_keys:
        _login_failed_attempts.pop(key, None)


def is_login_rate_limited(documento: str, client_ip: str, now: Optional[float] = None) -> bool:
    if LOGIN_RATE_LIMIT_ATTEMPTS <= 0:
        return False

    now = now or time_module.time()
    _cleanup_login_attempts(now)
    key = _login_rate_key(documento, client_ip)
    window_start = now - LOGIN_RATE_LIMIT_WINDOW_SECONDS
    attempts = [ts for ts in _login_failed_attempts.get(key, []) if ts >= window_start]
    _login_failed_attempts[key] = attempts
    return len(attempts) >= LOGIN_RATE_LIMIT_ATTEMPTS


def register_failed_login(documento: str, client_ip: str, now: Optional[float] = None) -> None:
    now = now or time_module.time()
    key = _login_rate_key(documento, client_ip)
    window_start = now - LOGIN_RATE_LIMIT_WINDOW_SECONDS
    attempts = [ts for ts in _login_failed_attempts.get(key, []) if ts >= window_start]
    attempts.append(now)
    _login_failed_attempts[key] = attempts


def clear_failed_login(documento: str, client_ip: str) -> None:
    _login_failed_attempts.pop(_login_rate_key(documento, client_ip), None)


def notify_critical_api_error(endpoint: str, method: str, status_code: int, error: str, details: dict = None):
    """EnvÃ­a alerta de error crÃ­tico por email, con protecciÃ³n anti-spam."""
    if not ENABLE_ERROR_ALERT_EMAILS:
        return

    try:
        email_service.send_critical_error_alert(
            title="Error API en ProducciÃ³n",
            error=error,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            details=details or {},
            dedupe_key=f"api:{method}:{endpoint}:{status_code}:{error[:120]}"
        )
    except Exception as alert_error:
        app_logger.error(f"No se pudo enviar alerta crÃ­tica por email: {alert_error}", exc_info=True)

# Setup DB
try:
    models.Base.metadata.create_all(bind=database.engine)
except Exception as db_setup_error:
    app_logger.error(f"No se pudo inicializar la base de datos al arrancar: {db_setup_error}", exc_info=True)


# Lifespan context manager for application startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja el ciclo de vida de la aplicaciÃ³n"""
    # Startup event
    log_system_event("AplicaciÃ³n iniciada", severity="info")
    
    # Iniciar scheduler de tareas
    try:
        task_scheduler.start()
        log_system_event("Scheduler de tareas iniciado", severity="info")
    except Exception as e:
        log_system_event(f"Error iniciando scheduler: {str(e)}", severity="error")
    
    yield  # AquÃ­ la aplicaciÃ³n estÃ¡ corriendo
    
    # Shutdown event
    log_system_event("AplicaciÃ³n cerrÃ¡ndose", severity="info")
    
    # Detener scheduler
    try:
        task_scheduler.stop()
        log_system_event("Scheduler detenido", severity="info")
    except Exception as e:
        log_system_event(f"Error deteniendo scheduler: {str(e)}", severity="error")


app = FastAPI(lifespan=lifespan)

# API Router with /api prefix (recommended for nginx configuration)
api_router = APIRouter(prefix="/api")

# --- Frontend (SPA) static files ---
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_ROOT = BASE_DIR.parent / "frontend"
FRONTEND_DIST = FRONTEND_ROOT / "dist"
FRONTEND_SPA_ROOT = FRONTEND_DIST if (FRONTEND_DIST / "index.html").exists() else FRONTEND_ROOT

if FRONTEND_SPA_ROOT.exists():
    assets_dir = FRONTEND_SPA_ROOT / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom exception handler for validation errors (422)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log and return detailed validation errors"""
    errors = exc.errors()
    app_logger.error(f"Validation error on {request.method} {request.url.path}: {errors}")
    return JSONResponse(
        status_code=422,
        content={"detail": errors}
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler that logs the error and sends an alert email to ops."""
    # Log full exception with traceback
    app_logger.error(f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}", exc_info=True)

    # Send alert email (non-blocking best-effort)
    try:
        notify_critical_api_error(
            endpoint=request.url.path,
            method=request.method,
            status_code=500,
            error=str(exc),
            details={
                'query_params': str(request.query_params),
                'client': str(request.client) if hasattr(request, 'client') else None,
            }
        )
    except Exception as email_err:
        app_logger.error(f"Error sending critical alert email: {email_err}", exc_info=True)

    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


# Middleware de logging para todas las peticiones HTTP
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Registra todas las peticiones HTTP con detalles de rendimiento"""
    start_time = time_module.time()

    # InformaciÃ³n bÃ¡sica de la peticiÃ³n
    endpoint = request.url.path
    method = request.method

    try:
        response = await call_next(request)
        status_code = response.status_code
        error_msg = None

        if status_code >= 500 and request.url.path.startswith("/api"):
            notify_critical_api_error(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                error=f"Respuesta HTTP {status_code}",
                details={
                    "query_params": str(request.query_params),
                },
            )
    except Exception as e:
        app_logger.error(f"Error procesando peticiÃ³n {method} {endpoint}: {str(e)}", exc_info=True)
        status_code = 500
        error_msg = str(e)

        if request.url.path.startswith("/api"):
            notify_critical_api_error(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                error=error_msg,
                details={
                    "query_params": str(request.query_params),
                    "exception_type": type(e).__name__,
                },
            )

        # Re-raise para que FastAPI maneje el error
        raise
    finally:
        # Calcular duraciÃ³n
        duration_ms = (time_module.time() - start_time) * 1000

        # Extraer user_id si existe en headers o query params
        user_id = request.headers.get("X-User-ID") or request.query_params.get("user_id")

        # Registrar la peticiÃ³n
        log_api_request(
            endpoint=endpoint,
            method=method,
            user_id=user_id,
            status_code=status_code,
            duration_ms=duration_ms,
            error=error_msg
        )

    return apply_allowed_cors_header(request, response)


# Safety middleware: ensure CORS header present on every response (helps when exceptions occur)
@app.middleware("http")
async def ensure_cors_header(request, call_next):
    try:
        response = await call_next(request)
    except Exception as e:
        # If an exception bubbles, craft a minimal response with CORS header
        from fastapi.responses import PlainTextResponse
        resp = PlainTextResponse(str(e), status_code=500)
        return apply_allowed_cors_header(request, resp)

    return apply_allowed_cors_header(request, response)


# Helpers
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT while keeping the existing login response contract."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invÃ¡lido")


def _extract_bearer_token(request: Request) -> Optional[str]:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[models.Empleado]:
    token = _extract_bearer_token(request)
    if not token:
        return None

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invÃ¡lido")

    try:
        empleado_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invÃ¡lido")

    empleado = db.query(models.Empleado).filter(models.Empleado.id == empleado_id).first()
    if not empleado or not empleado.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no autorizado")

    return empleado


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.Empleado:
    empleado = get_current_user_optional(request, db)
    if empleado is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    return empleado


def ensure_same_user(requested_user_id: int, current_user: models.Empleado) -> None:
    if requested_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado para consultar este usuario")


def require_admin_user(current_user: models.Empleado = Depends(get_current_user)) -> models.Empleado:
    admin_ids = parse_admin_user_ids()
    if current_user.id not in admin_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")
    return current_user

# --- Endpoints ---

@app.get("/")
def serve_root():
    index_file = FRONTEND_SPA_ROOT / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend no disponible")


# Test route to verify Sentry integration (trigger an exception)
@app.get("/sentry-debug")
def sentry_debug():
    if os.getenv("ENABLE_SENTRY_DEBUG", "false").lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=404, detail="Not found")
    division_by_zero = 1 / 0
    return {"ok": False}

@api_router.get("/empleados", response_model=List[schemas.EmpleadoCatalogo])
def read_empleados(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    # Return valid drivers (activo=True)
    return db.query(models.Empleado).filter(models.Empleado.activo == True).offset(skip).limit(limit).all()

@api_router.get("/proveedores", response_model=List[schemas.ProveedorCatalogo])
def read_proveedores(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Proveedor).filter(models.Proveedor.activo == True).offset(skip).limit(limit).all()


@api_router.get("/clientes", response_model=List[schemas.ClienteCatalogo])
def read_clientes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Devuelve clientes activos (para sincronizar al dispositivo mÃ³vil)"""
    # Some deployments may not have the `cliente` table; guardamos excepciones
    try:
        return db.query(models.Cliente).filter(models.Cliente.activo == True).offset(skip).limit(limit).all()
    except Exception as e:
        app_logger.warning(f"Tabla clientes no disponible o error: {e}")
        return []

@api_router.get("/equipos", response_model=List[schemas.Equipo])
def read_equipos(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Equipo).filter(models.Equipo.activo == True).offset(skip).limit(limit).all()

@api_router.get("/panioles", response_model=List[schemas.Paniol])
def read_panioles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Paniol).filter(models.Paniol.activo == True).offset(skip).limit(limit).all()

@api_router.get("/unidades-negocio", response_model=List[schemas.UnidadNegocio])
def read_unidades_negocio(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return (
        db.query(models.UnidadNegocio)
        .filter(models.UnidadNegocio.activo == True)
        .order_by(models.UnidadNegocio.descripcion.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )

@api_router.get("/remitos/existe")
def remito_existe(
    numero_remision: str = "",
    numero_remision_fpv: str = "",
    db: Session = Depends(get_db)
):
    exists_proveedor = False
    exists_fgpy = False

    if numero_remision:
        exists_proveedor = db.query(models.TableroProduccion.id).filter(
            models.TableroProduccion.remito_proveedor == numero_remision
        ).first() is not None

    if numero_remision_fpv:
        exists_fgpy = db.query(models.TableroProduccion.id).filter(
            models.TableroProduccion.remito_fgpy == numero_remision_fpv
        ).first() is not None

    return {
        "exists": exists_proveedor or exists_fgpy,
        "exists_proveedor": exists_proveedor,
        "exists_fgpy": exists_fgpy
    }

@api_router.get("/historial-viajes", response_model=List[schemas.HistorialViajeItem])
def read_historial_viajes(
    chofer_id: int,
    fecha_desde: date,
    fecha_hasta: date,
    db: Session = Depends(get_db),
    current_user: models.Empleado = Depends(get_current_user),
):
    ensure_same_user(chofer_id, current_user)

    if fecha_desde > fecha_hasta:
        raise HTTPException(status_code=400, detail="Rango de fechas invÃ¡lido")

    # set logging context with chofer name when possible
    try:
        empleado_ctx = db.query(models.Empleado).filter(models.Empleado.id == chofer_id).first()
        if empleado_ctx:
            set_request_context(chofer=f"{empleado_ctx.apellido} {empleado_ctx.nombre}")
    except Exception:
        # ignore context setting failures
        pass

    try:
        registros = (
            db.query(models.TableroProduccion, models.Empleado, models.Equipo)
            .outerjoin(models.Empleado, models.TableroProduccion.empleado_id == models.Empleado.id)
            .outerjoin(models.Equipo, models.TableroProduccion.equipo_id == models.Equipo.id)
            .filter(
                models.TableroProduccion.empleado_id == chofer_id,
                models.TableroProduccion.fecha >= fecha_desde,
                models.TableroProduccion.fecha <= fecha_hasta,
            )
            .order_by(models.TableroProduccion.fecha.desc(), models.TableroProduccion.id.desc())
            .all()
        )
    except Exception as e:
        app_logger.error(f"Error fetching historial for chofer={chofer_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error consultando historial: {str(e)}")
    finally:
        clear_request_context()

    result = []
    for tablero, empleado, equipo in registros:
        result.append({
            "id": tablero.id,
            "fecha": tablero.fecha,
            "produccion": float(tablero.produccion) if tablero.produccion is not None else 0.0,
            "patente": equipo.patente if equipo else "",
            "chofer": f"{empleado.apellido} {empleado.nombre}" if empleado else "",
            "remito_proveedor": tablero.remito_proveedor,
            "remito_fgpy": tablero.remito_fgpy,
            "observaciones": tablero.observaciones,
        })

    return result

@api_router.post("/login/")
@api_router.post("/login")
def login(request: schemas.LoginRequest, db: Session = Depends(get_db), http_request: Request = None):
    # Simple login logic based on Documento
    log_api_request(endpoint="/login", method="POST", user_id=None, status_code=200, duration_ms=0)
    
    # Validate input
    if not request.documento or not str(request.documento).strip():
        log_system_event("Login attempt with empty documento", severity="warning")
        raise HTTPException(status_code=400, detail=LOGIN_INVALID_DETAIL)
    
    documento = str(request.documento).strip()
    client_ip = get_client_ip(http_request)

    if is_login_rate_limited(documento, client_ip):
        log_system_event(f"Login rate limit exceeded for ip={client_ip}", severity="warning")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Intente nuevamente mas tarde.",
            headers={"Retry-After": str(LOGIN_RATE_LIMIT_LOCKOUT_SECONDS)},
        )
    
    empleado = db.query(models.Empleado).filter(models.Empleado.documento == documento).first()
    if not empleado:
        log_system_event(f"Login attempt with non-existent documento: {documento}", severity="warning")
        register_failed_login(documento, client_ip)
        raise HTTPException(status_code=400, detail=LOGIN_INVALID_DETAIL)
    
    if not empleado.activo:
        log_system_event(f"Login attempt with inactive user: {documento}", severity="warning")
        register_failed_login(documento, client_ip)
        raise HTTPException(status_code=400, detail=LOGIN_INVALID_DETAIL)
    
    clear_failed_login(documento, client_ip)
    log_user_action(user_id=empleado.id, action="login", details={"documento": documento})
    
    access_token = create_access_token(
        data={
            "sub": str(empleado.id),
            "documento": documento,
            "nombre": empleado.nombre,
            "apellido": empleado.apellido,
        }
    )
    return {"access_token": access_token, "token_type": "bearer", "user": {"nombre": empleado.nombre, "apellido": empleado.apellido, "id": empleado.id}}

@api_router.post("/registro-viaje", response_model=schemas.RegistroViajeResponse)
def create_registro_viaje(
    registro: schemas.RegistroViajeCreate,
    db: Session = Depends(get_db),
    current_user: models.Empleado = Depends(get_current_user),
):
    # LÃ³gica de cÃ¡lculo y mapeo
    
    # 1. Calcular ProducciÃ³n (Net Weight in kg or Tn?)
    # DB has simple fields, looks like we need standard units.
    # UI: Peso Bruto Origen (Tn), Tara Origen (Tn).
    # Produccion = (Bruto - Tara) * 1000 to get KG? 
    # Or keep it in Tn? models.Produccion is Decimal(10,2). 
    # Let's assume Tn for now as per forestry standards usually.
    
    produccion_tn = registro.neto_origen  # neto_origen is already in Tn

    # Prevent duplicate remitos
    if registro.numero_remision:
        exists_proveedor = db.query(models.TableroProduccion.id).filter(
            models.TableroProduccion.remito_proveedor == registro.numero_remision
        ).first() is not None
        if exists_proveedor:
            raise HTTPException(status_code=400, detail="El NÂº Remito Proveedor ya existe")

    if registro.numero_remision_fpv:
        exists_fgpy = db.query(models.TableroProduccion.id).filter(
            models.TableroProduccion.remito_fgpy == registro.numero_remision_fpv
        ).first() is not None
        if exists_fgpy:
            raise HTTPException(status_code=400, detail="El NÂº Remito FGPY ya existe")
    
    # 2. Validate Chofer
    empleado = db.query(models.Empleado).filter(models.Empleado.id == registro.chofer_id).first()
    if not empleado:
        raise HTTPException(status_code=400, detail="Chofer no encontrado")

    # set request logging context (chofer)
    try:
        set_request_context(chofer=f"{empleado.apellido} {empleado.nombre}")
    except Exception:
        pass

    # 3. Find Equipo (normalize patente)
    patente = (registro.patente or "").strip().upper()
    if not patente:
        raise HTTPException(status_code=400, detail="Patente requerida")

    equipo = db.query(models.Equipo).filter(models.Equipo.patente == patente).first()
    if not equipo:
        patente_compact = patente.replace(" ", "")
        if patente_compact != patente:
            equipo = db.query(models.Equipo).filter(models.Equipo.patente == patente_compact).first()
        if not equipo:
            equipo = db.query(models.Equipo).filter(func.replace(models.Equipo.patente, " ", "") == patente_compact).first()

    if not equipo:
        raise HTTPException(status_code=400, detail="Patente no encontrada")

    equipo_id = equipo.id
    try:
        set_request_context(vehiculo=f"{equipo.patente} - {equipo.descripcion}")
    except Exception:
        pass

    # 3. Create Record
    # We need defaults for many required columns in tablero_produccion that aren't in the form
    # Build periodo YYYYMM from fecha_remision
    try:
        periodo = f"{registro.fecha_remision.year}{registro.fecha_remision.month:02d}"
    except Exception:
        periodo = datetime.now().strftime('%Y%m')

    # Validate net weights are numeric and within a reasonable range
    def validate_neto(name, value):
        try:
            v = float(value)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Valor invÃ¡lido o faltante: {name} debe ser numÃ©rico (recibido={value})")
        if v <= 0:
            raise HTTPException(status_code=400, detail=f"Valor invÃ¡lido: {name} debe ser > 0 (recibido={v})")
        if v > NETO_MAX_TN:
            raise HTTPException(status_code=400, detail=f"Valor invÃ¡lido: {name} demasiado grande (> {NETO_MAX_TN} Tn) (recibido={v})")
        return v

    validate_neto('neto_origen', getattr(registro, 'neto_origen', None))
    validate_neto('neto_destino', getattr(registro, 'neto_destino', None))

    # Determine cliente/proveedor behavior based on unidad de negocio
    # Defaults: if one of the fields is missing, store None (NULL) for proveedor, 1 for cliente
    proveedor_id_val = None  # Allow NULL for proveedor when not provided
    cliente_id_val = 1

    unidad = None
    try:
        if getattr(registro, 'unidad_negocio_id', None) is not None:
            unidad = db.query(models.UnidadNegocio).filter(models.UnidadNegocio.id == registro.unidad_negocio_id).first()
    except Exception:
        unidad = None

    is_tc = False
    if unidad and unidad.descripcion:
        try:
            is_tc = 'Transporte Chip - TC' in unidad.descripcion
        except Exception:
            is_tc = False

    # If proveedor_id provided, validate it (DB enforces proveedor existence)
    if getattr(registro, 'proveedor_id', None) is not None:
        proveedor_obj = db.query(models.Proveedor).filter(models.Proveedor.id == registro.proveedor_id).first()
        if not proveedor_obj:
            raise HTTPException(status_code=400, detail="Proveedor no encontrado")
        proveedor_id_val = proveedor_obj.id

    # cliente_id may be provided by the client app (used for Transporte Chip - TC)
    if getattr(registro, 'cliente_id', None) is not None:
        try:
            cliente_id_val = int(registro.cliente_id)
            # Validate cliente exists if model available
            try:
                cliente_obj = db.query(models.Cliente).filter(models.Cliente.id == cliente_id_val).first()
                if not cliente_obj:
                    raise HTTPException(status_code=400, detail="Cliente no encontrado")
            except AttributeError:
                # models.Cliente may not exist in some deployments; skip validation
                pass
        except Exception:
            cliente_id_val = 1

    nuevo_registro = models.TableroProduccion(
        fecha=registro.fecha_remision, # Or use today?
        empleado_id=registro.chofer_id,
        equipo_id=equipo_id,
        produccion=produccion_tn,
        remito=0,
        remito2=0,
        remito_proveedor = registro.numero_remision,
        remito_fgpy = registro.numero_remision_fpv,
        hora=datetime.now().time(),
        turno="dia", # Logic needed based on time
        unidad_negocio_id=registro.unidad_negocio_id,
        cliente_id=(cliente_id_val if cliente_id_val is not None else 1),
        predio_id=1, # Default
        periodo=periodo,
        proveedor_id=proveedor_id_val,  # Can be None (NULL) if not provided
        # Pesos y medidas (store in origin columns; fallback to destination fields if origin not provided)
        bruto_destino=(registro.peso_bruto_origen if getattr(registro, 'peso_bruto_origen', None) is not None else getattr(registro, 'peso_bruto_destino', None)),
        tara_destino=(registro.tara_origen if getattr(registro, 'tara_origen', None) is not None else getattr(registro, 'tara_destino', None)),
        neto_origen=registro.neto_origen,
        neto_destino=registro.neto_destino,
        # Explicit defaults for other NOT NULL columns to avoid DB errors
        hr_inicio=0.0,
        hr_fin=0.0,
        unidad_produccion_id=5, # Default TN transportadas
        coeficiente=1.0,
        altura=0.0,
        ancho=0.0,
        cantidad_estibas=0.0,
        largo_madera=0.0,
        carros=0,
        plantas=0,
        hrs_no_operativas=0,
        carga_piso=0,
        tipo_operacion_id=21, # Default "Transporte" 
        lenia_seca=0,
        carga_rollo=0,
        carga_lenia=0,
        tarifa=0.0,
        tarifa_empresa=0.0,
        origen_destino_id=1,
        tabla=None,
        codigo_tabla=0,
        origen=(getattr(registro, 'origen', None) or ""),
        origen_carreton=(getattr(registro, 'origen_carreton', None) or ""),
        destino_carreton=(getattr(registro, 'destino_carreton', None) or ""),
        modificado=False,
        usuario=str(registro.chofer_id) if registro.chofer_id else None,
        observaciones=registro.observaciones
    )
    
    try:
        db.add(nuevo_registro)
        db.commit()
        db.refresh(nuevo_registro)
        return {"id": nuevo_registro.id, "message": "Viaje registrado OK"}
    finally:
        clear_request_context()

@api_router.post("/movimiento-combustible", response_model=schemas.MovimientoCombustibleResponse)
def create_movimiento_combustible(
    registro: schemas.MovimientoCombustibleCreate,
    db: Session = Depends(get_db),
    current_user: models.Empleado = Depends(get_current_user),
):
    # Defaults and mappings for required fields
    try:
        periodo = f"{registro.fecha_carga.year}{registro.fecha_carga.month:02d}"
    except Exception:
        periodo = datetime.now().strftime('%Y%m')

    if not registro.remito:
        raise HTTPException(status_code=400, detail="NÂº Remito requerido")

    remito_normalizado = str(registro.remito).strip()
    if not remito_normalizado:
        raise HTTPException(status_code=400, detail="NÂº Remito requerido")
    if len(remito_normalizado) > 12:
        raise HTTPException(status_code=400, detail="NÂº Remito no puede superar 12 caracteres")

    if registro.litros is None or float(registro.litros) <= 0:
        raise HTTPException(status_code=400, detail="Litros debe ser mayor a 0")
    if registro.km_hora is None or float(registro.km_hora) <= 0:
        raise HTTPException(status_code=400, detail="KM/Hora debe ser mayor a 0")

    usuario = registro.usuario or "app"
    chofer_id = None
    chofer_nombre = "N/A"
    try:
        chofer_id = int(usuario)
        chofer = db.query(models.Empleado).filter(models.Empleado.id == chofer_id).first()
        if chofer:
            chofer_nombre = f"{chofer.apellido} {chofer.nombre}".strip()
            # set request context
            try:
                set_request_context(chofer=chofer_nombre)
            except Exception:
                pass
    except Exception:
        chofer_id = None

    # Validate equipo early to avoid DB FK 500 errors
    equipo = db.query(models.Equipo).filter(models.Equipo.id == registro.equipo_id).first()
    if not equipo:
        raise HTTPException(status_code=400, detail="Equipo no encontrado")

    # Validate paniol and get unidad_negocio_id from it when present
    unidad_negocio_id = 1  # Default
    if registro.paniol_id:
        paniol = db.query(models.Paniol).filter(models.Paniol.id == registro.paniol_id).first()
        if not paniol:
            raise HTTPException(status_code=400, detail="PaÃ±ol no encontrado")
        if paniol.unidad_negocio_id is not None:
            unidad_negocio_id = paniol.unidad_negocio_id

    unidad_negocio = db.query(models.UnidadNegocio).filter(models.UnidadNegocio.id == unidad_negocio_id).first()
    frente_desc = unidad_negocio.descripcion if unidad_negocio and unidad_negocio.descripcion else "N/A"
    camion_desc = f"{equipo.patente} - {equipo.descripcion}" if equipo else "N/A"
    try:
        set_request_context(vehiculo=camion_desc)
    except Exception:
        pass
    # Handle proveedor_id: some production DBs require proveedor_id as NOT NULL
    proveedor_id_val = None
    if getattr(registro, 'proveedor_id', None) is not None:
        proveedor_obj = db.query(models.Proveedor).filter(models.Proveedor.id == registro.proveedor_id).first()
        if not proveedor_obj:
            raise HTTPException(status_code=400, detail="Proveedor no encontrado")
        proveedor_id_val = proveedor_obj.id
    else:
        proveedor_obj = None
        if DEFAULT_FUEL_PROVEEDOR_ID:
            try:
                proveedor_default_id = int(DEFAULT_FUEL_PROVEEDOR_ID)
                proveedor_obj = db.query(models.Proveedor).filter(models.Proveedor.id == proveedor_default_id).first()
            except Exception:
                proveedor_obj = None

        # Fallback if env var not set or points to a non-existing provider
        if not proveedor_obj:
            proveedor_obj = (
                db.query(models.Proveedor)
                .filter(models.Proveedor.activo == True)
                .order_by(models.Proveedor.id.asc())
                .first()
            )

        if not proveedor_obj:
            raise HTTPException(
                status_code=400,
                detail="Proveedor requerido: configure DEFAULT_FUEL_PROVEEDOR_ID o seleccione proveedor en el formulario",
            )

        proveedor_id_val = proveedor_obj.id

    nuevo = models.MovimientoCombustible(
        fecha=registro.fecha_carga,
        tipo_combustible_id=1,
        equipo_id=registro.equipo_id,
        km_hora=registro.km_hora,
        precio_litro=0.0,
        ingreso=registro.litros,
        egreso=0.0,
        unidad_negocio_id=unidad_negocio_id,
        paniol_id=registro.paniol_id,
        remito=remito_normalizado,
        idtabla=0,
        tabla="movimientocombustible",
        usuario=usuario,
        fecha_grabacion=datetime.now(),
        observaciones=registro.observaciones,
        proveedor_id=proveedor_id_val,
        periodo=periodo,
        remito2="0",
    )
    payload_snapshot = {
        "fecha": str(registro.fecha_carga),
        "tipo_combustible_id": 1,
        "equipo_id": registro.equipo_id,
        "km_hora": registro.km_hora,
        "precio_litro": 0.0,
        "ingreso": registro.litros,
        "egreso": 0.0,
        "unidad_negocio_id": unidad_negocio_id,
        "paniol_id": registro.paniol_id,
        "remito": remito_normalizado,
        "idtabla": 0,
        "tabla": "movimientocombustible",
        "usuario": usuario,
        "observaciones": registro.observaciones,
        "proveedor_id": proveedor_id_val,
        "periodo": periodo,
        "remito2": "0",
    }

    contexto_operativo = {
        "chofer_id": chofer_id,
        "chofer": chofer_nombre,
        "camion_id": equipo.id if equipo else None,
        "camion": camion_desc,
        "frente_id": unidad_negocio_id,
        "frente": frente_desc,
    }

    try:
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
    except IntegrityError as e:
        db.rollback()
        err = str(e)
        detail = "Datos invÃ¡lidos para registrar movimiento de combustible"
        if "1048" in err and "proveedor_id" in err:
            detail = "Proveedor es obligatorio en esta base de datos"
        if "1452" in err or "foreign key constraint fails" in err.lower():
            detail = "Error de referencia: equipo, paÃ±ol o proveedor no vÃ¡lido"
        elif "1062" in err or "duplicate" in err.lower():
            detail = "Registro duplicado: verifique datos ya cargados"

        from logger import sanitize_for_logging
        app_logger.error(
            f"Error de integridad en movimiento-combustible: {str(e)}",
            exc_info=True,
            extra={'extra_data': {'contexto_operativo': sanitize_for_logging(contexto_operativo), 'payload': sanitize_for_logging(payload_snapshot)}}
        )
        notify_critical_api_error(
            endpoint="/api/movimiento-combustible",
            method="POST",
            status_code=400,
            error=str(e),
            details={
                "error_type": "IntegrityError",
                "contexto_operativo": contexto_operativo,
                "payload": payload_snapshot,
            },
        )
        raise HTTPException(status_code=400, detail=detail)
    except DataError as e:
        db.rollback()
        err = str(e)
        detail = "Formato o longitud de datos invÃ¡lidos"
        if "Data too long for column" in err:
            detail = "Hay un campo demasiado largo (ej: NÂº Remito max 12 caracteres)"
        elif "Incorrect" in err or "truncated" in err.lower():
            detail = "Hay valores con formato invÃ¡lido"

        from logger import sanitize_for_logging
        app_logger.error(
            f"Error de datos en movimiento-combustible: {str(e)}",
            exc_info=True,
            extra={'extra_data': {'contexto_operativo': sanitize_for_logging(contexto_operativo), 'payload': sanitize_for_logging(payload_snapshot)}}
        )
        notify_critical_api_error(
            endpoint="/api/movimiento-combustible",
            method="POST",
            status_code=400,
            error=str(e),
            details={
                "error_type": "DataError",
                "contexto_operativo": contexto_operativo,
                "payload": payload_snapshot,
            },
        )
        raise HTTPException(status_code=400, detail=detail)
    except SQLAlchemyError as e:
        db.rollback()
        from logger import sanitize_for_logging
        app_logger.error(
            f"Error SQLAlchemy en movimiento-combustible: {str(e)}",
            exc_info=True,
            extra={'extra_data': {'contexto_operativo': sanitize_for_logging(contexto_operativo), 'payload': sanitize_for_logging(payload_snapshot)}}
        )
        notify_critical_api_error(
            endpoint="/api/movimiento-combustible",
            method="POST",
            status_code=500,
            error=str(e),
            details={
                "error_type": "SQLAlchemyError",
                "contexto_operativo": contexto_operativo,
                "payload": payload_snapshot,
            },
        )
        raise HTTPException(status_code=500, detail="Error de base de datos al registrar movimiento")
    finally:
        clear_request_context()

    return {"id": nuevo.id, "message": "Movimiento registrado OK"}


@api_router.post("/movimiento-carreton", response_model=schemas.MovimientoCarretonResponse)
def create_movimiento_carreton(
    registro: schemas.MovimientoCarretonCreate,
    db: Session = Depends(get_db),
    current_user: models.Empleado = Depends(get_current_user),
):
    from logger import sanitize_for_logging

    def reject_movimiento_carreton(detail: str, extra: dict = None):
        payload_snapshot = {
            "fecha": str(registro.fecha) if registro.fecha else None,
            "equipo_id": registro.equipo_id,
            "unidad_negocio_id": registro.unidad_negocio_id,
            "hora_inicio_viaje": str(registro.hora_inicio_viaje) if registro.hora_inicio_viaje else None,
            "km_inicial": registro.km_inicial,
            "km_final": registro.km_final,
            "permitir_km_inicial_menor": registro.permitir_km_inicial_menor,
            "estado_carga": registro.estado_carga,
            "tipo_maquina_transportada": registro.tipo_maquina_transportada,
            "usuario": registro.usuario,
            "origen_carreton": registro.origen_carreton,
            "destino_carreton": registro.destino_carreton,
        }
        app_logger.warning(
            f"ValidaciÃ³n rechazada en movimiento-carreton: {detail}",
            extra={
                'extra_data': {
                    'payload': sanitize_for_logging(payload_snapshot),
                    'validation': sanitize_for_logging(extra or {}),
                }
            }
        )
        notify_critical_api_error(
            endpoint="/api/movimiento-carreton",
            method="POST",
            status_code=400,
            error=detail,
            details={
                "payload": payload_snapshot,
                "validation": extra or {},
            },
        )
        raise HTTPException(status_code=400, detail=detail)

    fecha_movimiento = registro.fecha or date.today()
    periodo = f"{fecha_movimiento.year}{fecha_movimiento.month:02d}"

    estado_carga_raw = (registro.estado_carga or "").strip()
    try:
        estado_carga_reparado = estado_carga_raw.encode("latin1").decode("utf-8")
    except UnicodeError:
        estado_carga_reparado = estado_carga_raw
    estado_carga_clave = (
        unicodedata.normalize("NFKD", estado_carga_reparado.casefold())
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    estados_validos = {
        "vacio": "Vacío",
        "cargado": "Cargado",
    }
    if estado_carga_clave not in estados_validos:
        reject_movimiento_carreton("Estado de carga invÃ¡lido", {"estado_carga": registro.estado_carga})

    tipo_maquina_transportada = (registro.tipo_maquina_transportada or "").strip()
    if not tipo_maquina_transportada:
        reject_movimiento_carreton("Tipo de mÃ¡quina transportada requerido")

    try:
        km_inicial = float(registro.km_inicial)
        km_final = float(registro.km_final)
    except (TypeError, ValueError):
        reject_movimiento_carreton("Los KM deben ser numÃ©ricos")

    if km_inicial < 0 or km_final < 0:
        reject_movimiento_carreton("Los KM no pueden ser negativos", {"km_inicial": km_inicial, "km_final": km_final})
    if km_final <= km_inicial:
        reject_movimiento_carreton("El KM final debe ser mayor al KM inicial", {"km_inicial": km_inicial, "km_final": km_final})

    equipo = db.query(models.Equipo).filter(models.Equipo.id == registro.equipo_id).first()
    if not equipo:
        reject_movimiento_carreton("MÃ³vil no encontrado", {"equipo_id": registro.equipo_id})

    unidad = db.query(models.UnidadNegocio).filter(models.UnidadNegocio.id == registro.unidad_negocio_id).first()
    if not unidad:
        reject_movimiento_carreton("Unidad de negocio no encontrada", {"unidad_negocio_id": registro.unidad_negocio_id})

    ultimo_movimiento = (
        db.query(models.TableroProduccion)
        .filter(
            models.TableroProduccion.equipo_id == registro.equipo_id,
            models.TableroProduccion.tabla == "movimiento_carreton",
        )
        .order_by(models.TableroProduccion.fecha.desc(), models.TableroProduccion.id.desc())
        .first()
    )

    if ultimo_movimiento is not None:
        ultimo_km_final = float(ultimo_movimiento.hr_fin or 0)
        if km_inicial < ultimo_km_final:
            validation_details = {
                "km_inicial": km_inicial,
                "ultimo_km_final": ultimo_km_final,
                "equipo_id": registro.equipo_id,
                "confirmado_por_usuario": registro.permitir_km_inicial_menor,
            }
            if not registro.permitir_km_inicial_menor:
                reject_movimiento_carreton(
                    f"El KM inicial no puede ser menor al último KM final registrado ({ultimo_km_final:.2f})",
                    validation_details,
                )
            app_logger.warning(
                "Movimiento carretón con KM inicial menor confirmado por el usuario",
                extra={"extra_data": sanitize_for_logging(validation_details)},
            )

    usuario = registro.usuario or ""
    try:
        empleado_id = int(usuario)
    except (TypeError, ValueError):
        reject_movimiento_carreton("Usuario invÃ¡lido o no autenticado", {"usuario": registro.usuario})

    empleado = db.query(models.Empleado).filter(models.Empleado.id == empleado_id).first()
    if not empleado:
        reject_movimiento_carreton("Empleado no encontrado", {"empleado_id": empleado_id})

    nuevo_registro = models.TableroProduccion(
        fecha=fecha_movimiento,
        unidad_negocio_id=registro.unidad_negocio_id,
        empleado_id=empleado_id,
        equipo_id=registro.equipo_id,
        hr_inicio=km_inicial,
        hr_fin=km_final,
        produccion=km_final - km_inicial,
        unidad_produccion_id=7,
        observaciones=tipo_maquina_transportada,
        coeficiente=1.0,
        altura=0.0,
        ancho=0.0,
        cantidad_estibas=0.0,
        largo_madera=0.0,
        remito=0,
        carros=0,
        hora=datetime.now().time(),
        turno="dia",
        cliente_id=1,
        proveedor_id=None,
        plantas=0,
        predio_id=1,
        hrs_no_operativas=0,
        carga_piso=0,
        tipo_operacion_id=22,
        lenia_seca=0,
        carga_rollo=0,
        carga_lenia=0,
        fecha_corte=fecha_movimiento,
        periodo=periodo,
        tarifa=0.0,
        tarifa_empresa=0.0,
        origen_destino_id=1,
        tabla="movimiento_carreton",
        codigo_tabla=0,
        origen=estados_validos[estado_carga_clave],
        remito2=0,
        modificado=False,
        usuario=str(empleado_id),
        remito_proveedor=None,
        remito_fgpy=None,
        hora_inicio_viaje=registro.hora_inicio_viaje,
        origen_carreton=(registro.origen_carreton or ""),
        destino_carreton=(registro.destino_carreton or ""),
        hora_fin_viaje=None,
        neto_origen=0.0,
        bruto_destino=0.0,
        tara_destino=0.0,
        neto_destino=0.0,
    )

    try:
        db.add(nuevo_registro)
        db.commit()
        db.refresh(nuevo_registro)
    except SQLAlchemyError as e:
        db.rollback()
        app_logger.error(f"Error guardando movimiento de carretÃ³n: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo guardar el movimiento de carretÃ³n")

    log_user_action(
        user_id=empleado_id,
        action="registro_movimiento_carreton",
        details={
            "tablero_produccion_id": nuevo_registro.id,
            "equipo_id": registro.equipo_id,
            "unidad_negocio_id": registro.unidad_negocio_id,
            "estado_carga": estados_validos[estado_carga_clave],
        },
    )

    return {"id": nuevo_registro.id, "message": "Movimiento de carretÃ³n registrado OK"}

@api_router.get("/movimientos-combustible")
def read_movimientos_combustible(
    fecha_desde: date,
    fecha_hasta: date,
    equipo_id: Optional[int] = None,
    patente: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.Empleado = Depends(get_current_user),
):
    if fecha_desde > fecha_hasta:
        raise HTTPException(status_code=400, detail="Rango de fechas invÃ¡lido")

    query = db.query(models.MovimientoCombustible)

    if patente:
        query = query.join(models.Equipo, models.MovimientoCombustible.equipo_id == models.Equipo.id)
        query = query.filter(models.Equipo.patente == patente)
    elif equipo_id is not None:
        query = query.filter(models.MovimientoCombustible.equipo_id == equipo_id)

    movimientos = (
        query.filter(
            models.MovimientoCombustible.fecha >= fecha_desde,
            models.MovimientoCombustible.fecha <= fecha_hasta,
        )
        .order_by(models.MovimientoCombustible.fecha.asc(), models.MovimientoCombustible.id.asc())
        .all()
    )
    
    return [
        {
            "id": m.id,
            "fecha": m.fecha,
            "equipo_id": m.equipo_id,
            "km_hora": float(m.km_hora or 0),
            "litros": float(m.ingreso or 0) if float(m.ingreso or 0) > 0 else float(m.egreso or 0),
        }
        for m in movimientos
    ]


@api_router.get("/movimientos-carreton", response_model=List[schemas.MovimientoCarretonItem])
def read_movimientos_carreton(
    chofer_id: int,
    fecha_desde: date,
    fecha_hasta: date,
    db: Session = Depends(get_db),
    current_user: models.Empleado = Depends(get_current_user),
):
    ensure_same_user(chofer_id, current_user)

    if fecha_desde > fecha_hasta:
        raise HTTPException(status_code=400, detail="Rango de fechas invÃ¡lido")

    registros = (
        db.query(models.TableroProduccion, models.Empleado, models.Equipo, models.UnidadNegocio)
        .outerjoin(models.Empleado, models.TableroProduccion.empleado_id == models.Empleado.id)
        .outerjoin(models.Equipo, models.TableroProduccion.equipo_id == models.Equipo.id)
        .outerjoin(models.UnidadNegocio, models.TableroProduccion.unidad_negocio_id == models.UnidadNegocio.id)
        .filter(
            models.TableroProduccion.empleado_id == chofer_id,
            models.TableroProduccion.fecha >= fecha_desde,
            models.TableroProduccion.fecha <= fecha_hasta,
            models.TableroProduccion.tabla == "movimiento_carreton",
        )
        .order_by(models.TableroProduccion.fecha.desc(), models.TableroProduccion.id.desc())
        .all()
    )

    return [
        {
            "id": tablero.id,
            "fecha": tablero.fecha,
            "patente": equipo.patente if equipo else "",
            "unidad_negocio": unidad.descripcion if unidad and unidad.descripcion else "",
            "hora_inicio_viaje": tablero.hora_inicio_viaje,
            "origen_carreton": tablero.origen_carreton,
            "destino_carreton": tablero.destino_carreton,
            "km_inicial": float(tablero.hr_inicio or 0),
            "km_final": float(tablero.hr_fin or 0),
            "estado_carga": tablero.origen,
            "tipo_maquina_transportada": tablero.observaciones,
            "chofer": f"{empleado.apellido} {empleado.nombre}" if empleado else "",
        }
        for tablero, empleado, equipo, unidad in registros
    ]


@api_router.get("/movimientos-carreton/ultimo", response_model=Optional[schemas.MovimientoCarretonUltimoItem])
def read_ultimo_movimiento_carreton(
    equipo_id: int,
    db: Session = Depends(get_db),
    current_user: models.Empleado = Depends(get_current_user),
):
    ultimo = (
        db.query(models.TableroProduccion)
        .filter(
            models.TableroProduccion.equipo_id == equipo_id,
            models.TableroProduccion.tabla == "movimiento_carreton",
        )
        .order_by(models.TableroProduccion.fecha.desc(), models.TableroProduccion.id.desc())
        .first()
    )

    if ultimo is None:
        return None

    return {
        "id": ultimo.id,
        "equipo_id": ultimo.equipo_id,
        "fecha": ultimo.fecha,
        "km_final": float(ultimo.hr_fin or 0),
        "hora_inicio_viaje": ultimo.hora_inicio_viaje,
    }


# --- Endpoints de administraciÃ³n y monitoreo ---

def _round_float(value, digits=2):
    return round(float(value or 0), digits)


def _date_range_filter(column, fecha_desde: date, fecha_hasta: date):
    return column >= fecha_desde, column <= fecha_hasta


def _ranking_item(
    label,
    count,
    total,
    item_id=None,
    kind=None,
    overall_total=0,
    units=None,
    days=None,
    fuel_liters=0,
    fuel_days=None,
):
    total_value = _round_float(total)
    count_value = int(count or 0)
    item = {
        "label": label or "Sin dato",
        "count": count_value,
        "total": total_value,
    }
    if item_id is not None:
        item["id"] = int(item_id)
    if kind:
        item["kind"] = kind
        item["average"] = _round_float(total_value / count_value if count_value else 0)
        item["share"] = _round_float((total_value / float(overall_total or 0)) * 100 if overall_total else 0)
        item["units"] = units or []
        item["days"] = days or []
        item["fuel_liters"] = _round_float(fuel_liters)
        item["fuel_days"] = fuel_days or []
    return item


def _transport_unidad_filter():
    descripcion = func.lower(func.coalesce(models.UnidadNegocio.descripcion, ""))
    return and_(
        descripcion.like("%transporte%"),
        or_(
            descripcion.like("%chip%"),
            descripcion.like("%rollo%"),
            descripcion.like("%carreton%"),
            descripcion.like("%carretón%"),
        ),
    )


def _non_carreton_record_filter():
    return or_(
        models.TableroProduccion.tabla.is_(None),
        models.TableroProduccion.tabla != "movimiento_carreton",
    )


def _ranking_units(db: Session, fecha_desde: date, fecha_hasta: date, entity_filter):
    rows = (
        db.query(
            models.UnidadNegocio.descripcion,
            func.count(models.TableroProduccion.id),
            func.coalesce(func.sum(models.TableroProduccion.produccion), 0),
        )
        .join(models.UnidadNegocio, models.TableroProduccion.unidad_negocio_id == models.UnidadNegocio.id)
        .filter(
            *_date_range_filter(models.TableroProduccion.fecha, fecha_desde, fecha_hasta),
            _transport_unidad_filter(),
            _non_carreton_record_filter(),
            entity_filter,
        )
        .group_by(models.UnidadNegocio.descripcion)
        .order_by(func.coalesce(func.sum(models.TableroProduccion.produccion), 0).desc())
        .all()
    )
    return [_ranking_item(descripcion, count, total) for descripcion, count, total in rows]


def _ranking_days(db: Session, fecha_desde: date, fecha_hasta: date, entity_filter):
    rows = (
        db.query(
            models.TableroProduccion.fecha,
            func.count(models.TableroProduccion.id),
            func.coalesce(func.sum(models.TableroProduccion.produccion), 0),
        )
        .join(models.UnidadNegocio, models.TableroProduccion.unidad_negocio_id == models.UnidadNegocio.id)
        .filter(
            *_date_range_filter(models.TableroProduccion.fecha, fecha_desde, fecha_hasta),
            _transport_unidad_filter(),
            _non_carreton_record_filter(),
            entity_filter,
        )
        .group_by(models.TableroProduccion.fecha)
        .order_by(models.TableroProduccion.fecha.asc())
        .all()
    )
    return [
        {
            "fecha": fecha.isoformat() if fecha else "",
            "count": int(count or 0),
            "total": _round_float(total),
            "average": _round_float(float(total or 0) / int(count or 0) if count else 0),
        }
        for fecha, count, total in rows
    ]


def _fuel_days(db: Session, fecha_desde: date, fecha_hasta: date, entity_filter):
    rows = (
        db.query(
            models.MovimientoCombustible.fecha,
            func.coalesce(func.sum(models.MovimientoCombustible.ingreso), 0),
        )
        .filter(
            *_date_range_filter(models.MovimientoCombustible.fecha, fecha_desde, fecha_hasta),
            entity_filter,
        )
        .group_by(models.MovimientoCombustible.fecha)
        .order_by(models.MovimientoCombustible.fecha.asc())
        .all()
    )
    return [
        {
            "fecha": fecha.isoformat() if fecha else "",
            "litros": _round_float(litros),
        }
        for fecha, litros in rows
    ]


def _fuel_liters(db: Session, fecha_desde: date, fecha_hasta: date, entity_filter):
    return _round_float(
        db.query(func.coalesce(func.sum(models.MovimientoCombustible.ingreso), 0))
        .filter(
            *_date_range_filter(models.MovimientoCombustible.fecha, fecha_desde, fecha_hasta),
            entity_filter,
        )
        .scalar()
    )


def build_admin_dashboard_summary(db: Session, fecha_desde: date, fecha_hasta: date):
    transport_filter = _transport_unidad_filter()
    non_carreton_filter = _non_carreton_record_filter()
    viajes_query = (
        db.query(models.TableroProduccion)
        .join(models.UnidadNegocio, models.TableroProduccion.unidad_negocio_id == models.UnidadNegocio.id)
        .filter(
            *_date_range_filter(models.TableroProduccion.fecha, fecha_desde, fecha_hasta),
            transport_filter,
            non_carreton_filter,
        )
    )
    viajes = int(viajes_query.count() or 0)
    toneladas = _round_float(viajes_query.with_entities(func.coalesce(func.sum(models.TableroProduccion.produccion), 0)).scalar())
    promedio_toneladas = _round_float(toneladas / viajes if viajes else 0)

    litros = _round_float(
        db.query(func.coalesce(func.sum(models.MovimientoCombustible.ingreso), 0))
        .join(models.UnidadNegocio, models.MovimientoCombustible.unidad_negocio_id == models.UnidadNegocio.id)
        .filter(
            *_date_range_filter(models.MovimientoCombustible.fecha, fecha_desde, fecha_hasta),
            transport_filter,
        )
        .scalar()
    )

    movimientos_carreton = int(
        db.query(models.TableroProduccion)
        .join(models.UnidadNegocio, models.TableroProduccion.unidad_negocio_id == models.UnidadNegocio.id)
        .filter(
            *_date_range_filter(models.TableroProduccion.fecha, fecha_desde, fecha_hasta),
            transport_filter,
            models.TableroProduccion.tabla == "movimiento_carreton",
        )
        .count()
        or 0
    )

    por_equipo = (
        db.query(
            models.Equipo.id,
            models.Equipo.patente,
            func.count(models.TableroProduccion.id),
            func.coalesce(func.sum(models.TableroProduccion.produccion), 0),
        )
        .outerjoin(models.Equipo, models.TableroProduccion.equipo_id == models.Equipo.id)
        .join(models.UnidadNegocio, models.TableroProduccion.unidad_negocio_id == models.UnidadNegocio.id)
        .filter(
            *_date_range_filter(models.TableroProduccion.fecha, fecha_desde, fecha_hasta),
            transport_filter,
            non_carreton_filter,
        )
        .group_by(models.Equipo.id, models.Equipo.patente)
        .order_by(func.coalesce(func.sum(models.TableroProduccion.produccion), 0).desc())
        .limit(5)
        .all()
    )
    por_chofer = (
        db.query(
            models.Empleado.id,
            models.Empleado.apellido,
            models.Empleado.nombre,
            func.count(models.TableroProduccion.id),
            func.coalesce(func.sum(models.TableroProduccion.produccion), 0),
        )
        .outerjoin(models.Empleado, models.TableroProduccion.empleado_id == models.Empleado.id)
        .join(models.UnidadNegocio, models.TableroProduccion.unidad_negocio_id == models.UnidadNegocio.id)
        .filter(
            *_date_range_filter(models.TableroProduccion.fecha, fecha_desde, fecha_hasta),
            transport_filter,
            non_carreton_filter,
        )
        .group_by(models.Empleado.id, models.Empleado.apellido, models.Empleado.nombre)
        .order_by(func.coalesce(func.sum(models.TableroProduccion.produccion), 0).desc())
        .limit(5)
        .all()
    )
    por_unidad = (
        db.query(
            models.UnidadNegocio.descripcion,
            func.count(models.TableroProduccion.id),
            func.coalesce(func.sum(models.TableroProduccion.produccion), 0),
        )
        .outerjoin(models.UnidadNegocio, models.TableroProduccion.unidad_negocio_id == models.UnidadNegocio.id)
        .filter(
            *_date_range_filter(models.TableroProduccion.fecha, fecha_desde, fecha_hasta),
            transport_filter,
            non_carreton_filter,
        )
        .group_by(models.UnidadNegocio.descripcion)
        .order_by(func.coalesce(func.sum(models.TableroProduccion.produccion), 0).desc())
        .limit(5)
        .all()
    )

    return {
        "period": {
            "fecha_desde": fecha_desde.isoformat(),
            "fecha_hasta": fecha_hasta.isoformat(),
        },
        "kpis": {
            "viajes": viajes,
            "toneladas": toneladas,
            "promedio_toneladas_por_viaje": promedio_toneladas,
            "litros": litros,
            "movimientos_carreton": movimientos_carreton,
        },
        "rankings": {
            "por_equipo": [
                _ranking_item(
                    patente,
                    count,
                    total,
                    item_id=equipo_id,
                    kind="equipo",
                    overall_total=toneladas,
                    units=_ranking_units(
                        db,
                        fecha_desde,
                        fecha_hasta,
                        models.TableroProduccion.equipo_id == equipo_id,
                    ),
                    days=_ranking_days(
                        db,
                        fecha_desde,
                        fecha_hasta,
                        models.TableroProduccion.equipo_id == equipo_id,
                    ),
                    fuel_liters=_fuel_liters(
                        db,
                        fecha_desde,
                        fecha_hasta,
                        models.MovimientoCombustible.equipo_id == equipo_id,
                    ),
                    fuel_days=_fuel_days(
                        db,
                        fecha_desde,
                        fecha_hasta,
                        models.MovimientoCombustible.equipo_id == equipo_id,
                    ),
                )
                for equipo_id, patente, count, total in por_equipo
            ],
            "por_chofer": [
                _ranking_item(
                    " ".join(part for part in (apellido, nombre) if part),
                    count,
                    total,
                    item_id=empleado_id,
                    kind="chofer",
                    overall_total=toneladas,
                    units=_ranking_units(
                        db,
                        fecha_desde,
                        fecha_hasta,
                        models.TableroProduccion.empleado_id == empleado_id,
                    ),
                    days=_ranking_days(
                        db,
                        fecha_desde,
                        fecha_hasta,
                        models.TableroProduccion.empleado_id == empleado_id,
                    ),
                    fuel_liters=_fuel_liters(
                        db,
                        fecha_desde,
                        fecha_hasta,
                        models.MovimientoCombustible.usuario == str(empleado_id),
                    ),
                    fuel_days=_fuel_days(
                        db,
                        fecha_desde,
                        fecha_hasta,
                        models.MovimientoCombustible.usuario == str(empleado_id),
                    ),
                )
                for empleado_id, apellido, nombre, count, total in por_chofer
            ],
            "por_unidad_negocio": [_ranking_item(descripcion, count, total) for descripcion, count, total in por_unidad],
        },
        "alerts": {
            "blocked_records_note": "Los pendientes locales no son visibles en backend hasta sincronizar.",
        },
    }


@api_router.get("/admin/dashboard-summary")
def get_admin_dashboard_summary(
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    current_user: models.Empleado = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    fecha_hasta = fecha_hasta or today
    fecha_desde = fecha_desde or date(today.year, today.month, 1)

    if fecha_desde > fecha_hasta:
        raise HTTPException(status_code=400, detail="Rango de fechas invÃ¡lido")

    return build_admin_dashboard_summary(db, fecha_desde, fecha_hasta)


@api_router.get("/admin/health")
def health_check():
    """Endpoint de health check para monitoreo"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "service": "registro_viajes"
    }


@api_router.get("/admin/scheduled-jobs")
def get_scheduled_jobs(current_user: models.Empleado = Depends(get_current_user)):
    """Obtiene informaciÃ³n sobre las tareas programadas"""
    try:
        jobs = task_scheduler.get_scheduled_jobs()
        return {"jobs": jobs, "count": len(jobs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo tareas: {str(e)}")


@api_router.post("/admin/test-report")
def send_test_report(current_user: models.Empleado = Depends(get_current_user)):
    """EnvÃ­a un reporte de prueba inmediatamente (requiere autenticaciÃ³n en producciÃ³n)"""
    try:
        task_scheduler.send_test_report()
        return {"message": "Reporte de prueba enviado. Verifica el email."}
    except Exception as e:
        app_logger.error(f"Error enviando reporte de prueba: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@api_router.get("/admin/client-log-summary")
def get_client_log_summary(
    category: Optional[str] = Query(default=None, max_length=40),
    page: Optional[str] = Query(default=None, max_length=300),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: models.Empleado = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Resumen admin de errores frontend recientes, sanitizados y persistidos con retencion."""
    _apply_client_log_retention(db)
    db.commit()
    records = (
        db.query(models.ClientLogSummary)
        .order_by(models.ClientLogSummary.created_at.desc(), models.ClientLogSummary.id.desc())
        .limit(CLIENT_LOG_SUMMARY_MAX_ITEMS)
        .all()
    )
    items = [_client_log_record_to_item(record) for record in records]
    items = _filter_client_log_summary_items(items, category=category, page=page, date_from=date_from, date_to=date_to)
    return {
        "items": items,
        "count": len(items),
        "max_items": CLIENT_LOG_SUMMARY_MAX_ITEMS,
        "filters": {
            "category": category,
            "page": page,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    }


@api_router.delete("/admin/client-log-summary")
def clear_client_log_summary(
    category: Optional[str] = Query(default=None, max_length=40),
    page: Optional[str] = Query(default=None, max_length=300),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: models.Empleado = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Limpia los errores frontend ya revisados."""
    if not _has_client_log_filters(category=category, page=page, date_from=date_from, date_to=date_to):
        cleared = db.query(models.ClientLogSummary).count()
        db.query(models.ClientLogSummary).delete(synchronize_session=False)
        db.commit()
        client_log_summary_items.clear()
        return {"success": True, "cleared": cleared}

    cleared = _clear_filtered_client_log_summary(
        db,
        category=category,
        page=page,
        date_from=date_from,
        date_to=date_to,
    )
    db.commit()
    client_log_summary_items.clear()
    return {
        "success": True,
        "cleared": cleared,
        "filters": {
            "category": category,
            "page": page,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    }


# --- Endpoints de logging del cliente (frontend) ---

MAX_CLIENT_LOGS_PER_BATCH = 50
MAX_CLIENT_LOG_FIELD_LENGTH = 1000
MAX_CLIENT_LOG_EXTRA_ITEMS = 25
CLIENT_LOG_SUMMARY_MAX_ITEMS = int(os.getenv("CLIENT_LOG_SUMMARY_MAX_ITEMS", "200"))
CLIENT_LOG_RETENTION_DAYS = int(os.getenv("CLIENT_LOG_RETENTION_DAYS", "15"))
client_log_summary_items = []


def _truncate_client_log_value(value, max_length=MAX_CLIENT_LOG_FIELD_LENGTH):
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value[:max_length]
    if isinstance(value, list):
        return [_truncate_client_log_value(item, max_length) for item in value[:MAX_CLIENT_LOG_EXTRA_ITEMS]]
    if isinstance(value, dict):
        return {
            str(key)[:80]: _truncate_client_log_value(item, max_length)
            for key, item in list(value.items())[:MAX_CLIENT_LOG_EXTRA_ITEMS]
        }
    return str(value)[:max_length]


def _summarize_client_logs(logs):
    error_count = 0
    warnings_count = 0
    categories = {}
    suggested_actions = []

    for log_entry in logs:
        level = (log_entry.level or "").lower()
        message = f"{log_entry.message or ''} {log_entry.error_message or ''}".lower()

        if level == "error" or log_entry.error_name or log_entry.error_message:
            error_count += 1
        elif level in ("warning", "warn"):
            warnings_count += 1

        if "network error" in message or "failed to fetch" in message:
            categories["network"] = categories.get("network", 0) + 1
        elif "401" in message or "unauthorized" in message or "no autenticado" in message:
            categories["auth"] = categories.get("auth", 0) + 1
        elif "500" in message or "internal server" in message:
            categories["server"] = categories.get("server", 0) + 1
        elif "quota" in message or "indexeddb" in message or "localstorage" in message:
            categories["storage"] = categories.get("storage", 0) + 1
        elif level == "error" or log_entry.error_name or log_entry.error_message:
            categories["frontend"] = categories.get("frontend", 0) + 1

    if categories.get("network"):
        suggested_actions.append("Verificar conectividad del dispositivo y URL/API configurada.")
    if categories.get("auth"):
        suggested_actions.append("Revisar expiracion de sesion; pedir reingreso si el token ya no es valido.")
    if categories.get("server"):
        suggested_actions.append("Revisar logs del backend para el endpoint que devolvio HTTP 500.")
    if categories.get("storage"):
        suggested_actions.append("Revisar almacenamiento offline/IndexedDB/localStorage del dispositivo.")
    if categories.get("frontend"):
        suggested_actions.append("Revisar componente, ruta y stack del error frontend.")

    return {
        "errors": error_count,
        "warnings": warnings_count,
        "categories": categories,
    }, suggested_actions


def _build_client_log_samples(logs, max_samples=5):
    samples = []
    for log_entry in logs:
        level = (log_entry.level or "").lower()
        is_relevant = level in ("error", "warning", "warn", "critical") or log_entry.error_name or log_entry.error_message
        if not is_relevant:
            continue

        samples.append(sanitize_for_logging({
            "level": _truncate_client_log_value(log_entry.level, 40),
            "message": _truncate_client_log_value(log_entry.message, 500),
            "page": _truncate_client_log_value(log_entry.page, 300),
            "component": _truncate_client_log_value(log_entry.component, 120),
            "event_type": _truncate_client_log_value(log_entry.event_type, 120),
            "error_name": _truncate_client_log_value(log_entry.error_name, 120),
            "error_message": _truncate_client_log_value(log_entry.error_message, 500),
            "extra": _truncate_client_log_value(log_entry.extra, 500),
        }))

        if len(samples) >= max_samples:
            break

    return samples


def _client_log_json_dumps(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def _client_log_json_loads(value, fallback):
    try:
        return json.loads(value) if value else fallback
    except Exception:
        return fallback


def _client_log_record_to_item(record):
    return {
        "timestamp": record.created_at.isoformat() if record.created_at else None,
        "summary": _client_log_json_loads(record.summary_json, {}),
        "suggested_actions": _client_log_json_loads(record.suggested_actions_json, []),
        "samples": _client_log_json_loads(record.samples_json, []),
    }


def _filter_client_log_summary_items(items, category=None, page=None, date_from=None, date_to=None):
    normalized_category = (category or "").strip().lower()
    normalized_page = (page or "").strip().lower()
    filtered = []

    for item in items:
        if normalized_category:
            categories = item.get("summary", {}).get("categories", {})
            has_category = any(str(name).lower() == normalized_category and count for name, count in categories.items())
            if not has_category:
                continue

        if normalized_page:
            samples = item.get("samples") or []
            matching_samples = [
                sample
                for sample in samples
                if normalized_page in str(sample.get("page") or "").lower()
            ]
            if not matching_samples:
                continue
            item = {**item, "samples": matching_samples}

        if date_from or date_to:
            try:
                item_date = datetime.fromisoformat(str(item.get("timestamp"))).date()
            except Exception:
                continue
            if date_from and item_date < date_from:
                continue
            if date_to and item_date > date_to:
                continue

        filtered.append(item)

    return filtered


def _has_client_log_filters(category=None, page=None, date_from=None, date_to=None):
    return any([
        bool((category or "").strip()),
        bool((page or "").strip()),
        date_from is not None,
        date_to is not None,
    ])


def _client_log_sample_matches_page(sample, page):
    normalized_page = (page or "").strip().lower()
    if not normalized_page:
        return False
    return normalized_page in str(sample.get("page") or "").lower()


def _summarize_client_log_sample_dicts(samples):
    error_count = 0
    warnings_count = 0
    categories = {}
    suggested_actions = []

    for sample in samples:
        level = str(sample.get("level") or "").lower()
        message = f"{sample.get('message') or ''} {sample.get('error_message') or ''}".lower()
        has_error = level == "error" or sample.get("error_name") or sample.get("error_message")

        if has_error:
            error_count += 1
        elif level in ("warning", "warn"):
            warnings_count += 1

        if "network error" in message or "failed to fetch" in message:
            categories["network"] = categories.get("network", 0) + 1
        elif "401" in message or "unauthorized" in message or "no autenticado" in message:
            categories["auth"] = categories.get("auth", 0) + 1
        elif "500" in message or "internal server" in message:
            categories["server"] = categories.get("server", 0) + 1
        elif "quota" in message or "indexeddb" in message or "localstorage" in message:
            categories["storage"] = categories.get("storage", 0) + 1
        elif has_error:
            categories["frontend"] = categories.get("frontend", 0) + 1

    if categories.get("network"):
        suggested_actions.append("Verificar conectividad del dispositivo y URL/API configurada.")
    if categories.get("auth"):
        suggested_actions.append("Revisar expiracion de sesion; pedir reingreso si el token ya no es valido.")
    if categories.get("server"):
        suggested_actions.append("Revisar logs del backend para el endpoint que devolvio HTTP 500.")
    if categories.get("storage"):
        suggested_actions.append("Revisar almacenamiento offline/IndexedDB/localStorage del dispositivo.")
    if categories.get("frontend"):
        suggested_actions.append("Revisar componente, ruta y stack del error frontend.")

    return {
        "errors": error_count,
        "warnings": warnings_count,
        "categories": categories,
    }, suggested_actions


def _clear_filtered_client_log_summary(db: Session, category=None, page=None, date_from=None, date_to=None):
    cleared = 0
    records = (
        db.query(models.ClientLogSummary)
        .order_by(models.ClientLogSummary.created_at.desc(), models.ClientLogSummary.id.desc())
        .all()
    )

    for record in records:
        item = _client_log_record_to_item(record)
        if not _filter_client_log_summary_items([item], category=category, page=page, date_from=date_from, date_to=date_to):
            continue

        if page:
            samples = item.get("samples") or []
            remaining_samples = [
                sample
                for sample in samples
                if not _client_log_sample_matches_page(sample, page)
            ]
            if remaining_samples:
                summary, suggested_actions = _summarize_client_log_sample_dicts(remaining_samples)
                record.samples_json = _client_log_json_dumps(remaining_samples)
                record.summary_json = _client_log_json_dumps(summary)
                record.suggested_actions_json = _client_log_json_dumps(suggested_actions)
                cleared += 1
                continue

        db.delete(record)
        cleared += 1

    return cleared


def _apply_client_log_retention(db: Session):
    cutoff = datetime.now() - timedelta(days=CLIENT_LOG_RETENTION_DAYS)
    db.query(models.ClientLogSummary).filter(models.ClientLogSummary.created_at < cutoff).delete(synchronize_session=False)

    overflow_records = (
        db.query(models.ClientLogSummary.id)
        .order_by(models.ClientLogSummary.created_at.desc(), models.ClientLogSummary.id.desc())
        .offset(CLIENT_LOG_SUMMARY_MAX_ITEMS)
        .all()
    )
    overflow_ids = [record.id for record in overflow_records]
    if overflow_ids:
        db.query(models.ClientLogSummary).filter(models.ClientLogSummary.id.in_(overflow_ids)).delete(synchronize_session=False)


def _remember_client_log_summary(logs, summary, suggested_actions, db: Session):
    if summary.get("errors", 0) <= 0 and summary.get("warnings", 0) <= 0:
        return None

    samples = _build_client_log_samples(logs)
    item = {
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "suggested_actions": suggested_actions,
        "samples": samples,
    }

    record = models.ClientLogSummary(
        created_at=datetime.now(),
        summary_json=_client_log_json_dumps(summary),
        suggested_actions_json=_client_log_json_dumps(suggested_actions),
        samples_json=_client_log_json_dumps(samples),
    )
    db.add(record)
    _apply_client_log_retention(db)
    db.commit()

    client_log_summary_items.append(item)
    if len(client_log_summary_items) > CLIENT_LOG_SUMMARY_MAX_ITEMS:
        del client_log_summary_items[:-CLIENT_LOG_SUMMARY_MAX_ITEMS]

    return item


@api_router.post("/logs/client", response_model=schemas.ClientLogResponse)
def receive_client_logs(log_batch: schemas.ClientLogBatch, db: Session = Depends(get_db)):
    """
    Recibe logs del frontend (aplicaciÃ³n mÃ³vil/PWA).
    Los logs se almacenan en el sistema de logging centralizado.
    """
    try:
        logs_to_process = log_batch.logs[:MAX_CLIENT_LOGS_PER_BATCH]
        logs_count = len(logs_to_process)
        dropped_count = max(len(log_batch.logs) - logs_count, 0)
        device_info = sanitize_for_logging(_truncate_client_log_value(log_batch.device_info))
        error_summary, suggested_actions = _summarize_client_logs(logs_to_process)

        if dropped_count:
            app_logger.warning(
                f"Client log batch limitado: {logs_count} procesados, {dropped_count} descartados"
            )
        
        
        # Procesar cada log
        for log_entry in logs_to_process:
            # Preparar datos adicionales
            extra_data = {
                'type': 'client_log',
                'event_type': _truncate_client_log_value(log_entry.event_type, 120),
                'page': _truncate_client_log_value(log_entry.page, 300),
                'component': _truncate_client_log_value(log_entry.component, 120),
                'user_id': _truncate_client_log_value(log_entry.user_id, 80),
                'user_agent': _truncate_client_log_value(log_entry.user_agent, 300),
            }
            
            # Agregar informaciÃ³n de dispositivo si existe
            if device_info:
                extra_data['device_info'] = device_info
            
            # Agregar mÃ©tricas de rendimiento
            if log_entry.duration_ms:
                extra_data['duration_ms'] = log_entry.duration_ms
            
            # Agregar contexto adicional
            if log_entry.extra:
                extra_data['extra'] = sanitize_for_logging(_truncate_client_log_value(log_entry.extra))

            # If client provided a user_id, try to resolve employee name and set request context
            try:
                if log_entry.user_id:
                    # user_id may be string; convert to int when possible
                    try:
                        uid = int(str(log_entry.user_id))
                    except Exception:
                        uid = None
                    if uid:
                        empleado = db.query(models.Empleado).filter(models.Empleado.id == uid).first()
                        if empleado:
                            extra_data['user_name'] = f"{empleado.apellido} {empleado.nombre}"
                            try:
                                set_request_context(chofer=extra_data['user_name'])
                            except Exception:
                                pass
            except Exception:
                pass
            
            # Si es un error, incluir detalles del error
            if log_entry.error_name or log_entry.error_message:
                extra_data['error'] = {
                    'name': _truncate_client_log_value(log_entry.error_name, 120),
                    'message': _truncate_client_log_value(log_entry.error_message, 500),
                    'stack': _truncate_client_log_value(log_entry.error_stack, 1000)
                }
                
                # Registrar como error
                app_logger.error(
                    f"Frontend Error: {_truncate_client_log_value(log_entry.error_name, 120)}: {_truncate_client_log_value(log_entry.error_message, 500)}",
                    extra={'extra_data': extra_data}
                )
            else:
                # Registrar segÃºn el nivel
                level = log_entry.level.lower()
                log_message = (
                    f"Frontend [{_truncate_client_log_value(log_entry.event_type, 120)}]: "
                    f"{_truncate_client_log_value(log_entry.message, 500)}"
                )
                
                if level == 'error':
                    app_logger.error(log_message, extra={'extra_data': extra_data})
                elif level == 'warning':
                    app_logger.warning(log_message, extra={'extra_data': extra_data})
                elif level == 'critical':
                    app_logger.critical(log_message, extra={'extra_data': extra_data})
                else:
                    app_logger.info(log_message, extra={'extra_data': extra_data})
                
        
        log_system_event(
            f"Recibidos {logs_count} logs del cliente",
            severity="info",
            details={'count': logs_count, 'dropped': dropped_count, 'summary': error_summary, 'device': device_info}
        )

        _remember_client_log_summary(logs_to_process, error_summary, suggested_actions, db)
        
        return schemas.ClientLogResponse(
            success=True,
            message="Logs recibidos correctamente",
            logs_received=logs_count,
            error_summary=error_summary,
            suggested_actions=suggested_actions,
        )
        
    except Exception as e:
        app_logger.error(f"Error procesando logs del cliente: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error procesando logs: {str(e)}")
    finally:
        try:
            clear_request_context()
        except Exception:
            pass


# Include API router
@api_router.get("/app-version")
def get_app_version():
    """Devuelve la versiÃ³n/release del backend y opcional informaciÃ³n para que el cliente sepa si debe actualizar/sincronizar."""
    release = os.getenv('SENTRY_RELEASE') or os.getenv('APP_VERSION') or os.getenv('RELEASE') or 'unknown'
    deployed_at = os.getenv('DEPLOYED_AT')  # optional env var set by deploy process
    return {"release": release, "deployed_at": deployed_at}

# Include API router
app.include_router(api_router)

# SPA fallback: MUST BE LAST - serve index.html for client-side routes (e.g., /login)
# This catch-all route serves the frontend SPA and must be defined after all API routes
@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    if not FRONTEND_SPA_ROOT.exists():
        raise HTTPException(status_code=404, detail="Frontend no disponible")

    requested_file = FRONTEND_SPA_ROOT / full_path
    if requested_file.exists() and requested_file.is_file():
        return FileResponse(requested_file)

    index_file = FRONTEND_SPA_ROOT / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    raise HTTPException(status_code=404, detail="Frontend no disponible")
