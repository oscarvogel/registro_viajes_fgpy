"""
Sistema de logging centralizado para la aplicación de registro de viajes.
Captura logs en archivos rotativos con diferentes niveles.
"""
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime
import json
import traceback
import copy
import re
from typing import Any
import contextvars
import html

# Directorios de logs
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Formatos de logging
DETAILED_FORMAT = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

JSON_FORMAT = logging.Formatter(
    '%(asctime)s|%(name)s|%(levelname)s|%(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class JsonFormatter(logging.Formatter):
    """Formateador JSON para logs estructurados"""
    def format(self, record):
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Agregar campos extras si existen
        if hasattr(record, 'extra_data'):
            log_data['extra'] = record.extra_data

        # Add per-request context (chofer/vehiculo) if available
        try:
            ctx = _log_request_context.get()
            if ctx:
                # merge into top level for easier searching
                if 'chofer' in ctx:
                    log_data['chofer'] = ctx.get('chofer')
                if 'vehiculo' in ctx:
                    log_data['vehiculo'] = ctx.get('vehiculo')
        except LookupError:
            pass
            
        return json.dumps(log_data, ensure_ascii=False)


def setup_logger(name: str, level=logging.INFO):
    """
    Configura un logger con múltiples handlers:
    - Archivo general con rotación diaria
    - Archivo de errores con rotación por tamaño
    - Archivo JSON para análisis automatizado
    - Consola para desarrollo
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Evitar duplicados
    if logger.handlers:
        return logger
    
    # 1. Handler de archivo general (rotación diaria, mantiene 30 días)
    general_handler = TimedRotatingFileHandler(
        LOG_DIR / "app.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    general_handler.setLevel(logging.INFO)
    general_handler.setFormatter(DETAILED_FORMAT)
    logger.addHandler(general_handler)
    
    # 2. Handler de errores (rotación por tamaño, 10MB, 10 archivos)
    error_handler = RotatingFileHandler(
        LOG_DIR / "errors.log",
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=10,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(DETAILED_FORMAT)
    logger.addHandler(error_handler)
    
    # 3. Handler JSON para procesamiento automatizado
    json_handler = TimedRotatingFileHandler(
        LOG_DIR / "app_json.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    json_handler.setLevel(logging.INFO)
    json_handler.setFormatter(JsonFormatter())
    logger.addHandler(json_handler)
    
    # 4. Handler de consola (solo para desarrollo)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(DETAILED_FORMAT)
    logger.addHandler(console_handler)
    
    return logger


# Logger principal de la aplicación
app_logger = setup_logger("registro_viajes")


def _redact_connection_string(s: str) -> str:
    # redact password in URLs like mysql+mysqlconnector://user:pass@host/db
    try:
        return re.sub(r"(://[^:/@]+:)[^@]+(@)", r"\1REDACTED\2", s)
    except Exception:
        return s


def sanitize_for_logging(obj: Any) -> Any:
    """Recursively redact sensitive fields from objects before logging.

    Replaces values for keys like 'password','smtp_password','secret','token','api_key',
    and redacts passwords inside connection strings.
    """
    sensitive_keys = {"password", "passwd", "smtp_password", "secret", "token", "access_token", "api_key", "authorization", "smtp_pass", "db_password", "passwd"}

    if obj is None:
        return None

    # Primitive types
    if isinstance(obj, str):
        # redact obvious connection strings
        return _redact_connection_string(obj)

    if isinstance(obj, (int, float, bool)):
        return obj

    # Lists / tuples
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_logging(v) for v in obj]

    # Dict-like
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if any(sk in kl for sk in sensitive_keys):
                out[k] = "REDACTED"
            else:
                out[k] = sanitize_for_logging(v)
        return out

    # For other objects, try to convert to dict via __dict__ then sanitize
    try:
        if hasattr(obj, "__dict__"):
            return sanitize_for_logging(vars(obj))
    except Exception:
        pass

    # Fallback: stringify but escape HTML to avoid injection in email/log viewers
    try:
        return html.escape(str(obj))
    except Exception:
        return "[UNSERIALIZABLE]"


def log_api_request(endpoint: str, method: str, user_id: str = None, status_code: int = None, 
                    duration_ms: float = None, error: str = None):
    """Registra una petición API con detalles estructurados"""
    extra_data = {
        'type': 'api_request',
        'endpoint': endpoint,
        'method': method,
        'user_id': user_id,
        'status_code': status_code,
        'duration_ms': duration_ms,
    }
    
    if error:
        app_logger.error(f"API Error: {method} {endpoint} - {error}", 
                        extra={'extra_data': extra_data})
    else:
        app_logger.info(f"API: {method} {endpoint} - {status_code} ({duration_ms:.2f}ms)",
                       extra={'extra_data': extra_data})


# Per-request logging context (chofer / vehiculo)
_log_request_context: contextvars.ContextVar = contextvars.ContextVar('log_request_context', default={})

def set_request_context(**kwargs):
    """Set key/value pairs for the current request's logging context.

    Example: set_request_context(chofer='Perez Juan', vehiculo='ABC123')
    """
    ctx = _log_request_context.get().copy() if _log_request_context.get() else {}
    ctx.update(kwargs)
    _log_request_context.set(ctx)

def clear_request_context():
    _log_request_context.set({})

def get_request_context():
    return _log_request_context.get() or {}


def log_database_operation(operation: str, table: str, record_id: str = None, 
                          user_id: str = None, success: bool = True, error: str = None):
    """Registra operaciones de base de datos"""
    extra_data = {
        'type': 'db_operation',
        'operation': operation,
        'table': table,
        'record_id': record_id,
        'user_id': user_id,
        'success': success,
    }
    
    if not success:
        app_logger.error(f"DB Error: {operation} on {table} - {error}",
                        extra={'extra_data': extra_data})
    else:
        app_logger.info(f"DB: {operation} on {table}",
                       extra={'extra_data': extra_data})


def log_user_action(user_id: str, action: str, details: dict = None):
    """Registra acciones de usuario"""
    extra_data = {
        'type': 'user_action',
        'user_id': user_id,
        'action': action,
        'details': details or {}
    }
    
    app_logger.info(f"User Action: {user_id} - {action}",
                   extra={'extra_data': extra_data})


def log_system_event(event: str, severity: str = "info", details: dict = None):
    """Registra eventos del sistema"""
    extra_data = {
        'type': 'system_event',
        'event': event,
        'details': details or {}
    }
    
    level = getattr(logging, severity.upper(), logging.INFO)
    app_logger.log(level, f"System: {event}", extra={'extra_data': extra_data})


# Inicializar logger al importar
app_logger.info("Sistema de logging inicializado")
