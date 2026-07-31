"""Boundary adapter for MiniMax Vision through its MCP stdio server."""

from __future__ import annotations

import json
import math
import os
import queue
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class MiniMaxVisionError(RuntimeError):
    """A safe, domain-level MiniMax Vision failure."""


class MiniMaxVisionConfigurationError(MiniMaxVisionError):
    """MiniMax Vision is not configured correctly."""


class MiniMaxVisionTimeoutError(MiniMaxVisionError):
    """The provider execution exceeded its configured deadline."""


@dataclass(frozen=True)
class VisionSchema:
    """Esquema parametrizable para validar la respuesta JSON de MiniMax.

    - ``required``: conjunto exacto de claves que el JSON debe tener.
    - ``text_fields``: claves que deben ser string o null.
    - ``weight_fields``: claves numericas (Decimal-compatible); default vacio.
    """

    required: frozenset
    text_fields: frozenset
    weight_fields: frozenset = frozenset()

    @property
    def confidence_fields(self) -> frozenset:
        return self.text_fields | self.weight_fields


PROMPT = """Analiza la imagen para precargar un viaje. Devuelve EXCLUSIVAMENTE un unico objeto JSON,
sin prosa ni markdown, con estas claves exactas: fecha_remision; fecha_remito; fecha_ticket;
remito_tipo; remito_sucursal; remito_numero; cliente_candidato; proveedor_candidato; peso_bruto;
tara; neto; unidad_peso; patente_observada; chofer_observado; confidence (objeto por campo,
solo para las claves de datos anteriores y con valores entre 0 y 1); warnings (array de textos).
Usa null cuando un dato no sea visible. Conserva los pesos y su unidad tal como se observan.
Para la fecha, fecha_remito debe salir de la NOTA DE REMISION/remito principal (Fecha de Emision,
Fecha de expedicion o Fecha de inicio del traslado). fecha_ticket debe salir del ticket de balanza,
especialmente del campo FECHA SALIDA. En fecha_remision priorizar fecha_remito si es visible y legible;
si fecha_remito no esta visible o no es legible, usar fecha_ticket. No uses la fecha actual.
Para cliente_candidato toma la razon social de DESTINATARIO DE LA MERCADERIA.
Para proveedor_candidato toma la razon social de REMITENTE DE LA MERCADERIA.
No intercambies destinatario y remitente. En un numero como 002-003-0003677,
remito_tipo son los primeros 3 digitos (002), remito_sucursal los siguientes 3 (003) y
remito_numero los ultimos 7 (0003677); devuelve solo digitos en cada parte.
Devuelve cada peso como texto copiando todos los digitos y separadores impresos, sin convertirlo
ni reinterpretarlo: si el ticket muestra 49.690,00 kg devuelve "49.690,00", nunca 49.69.
OCR no elige cliente, proveedor, chofer, patente ni unidad: solo informa texto observado.
No normalices datos de negocio ni inventes valores."""

FUEL_TICKET_PROMPT = """Analiza la imagen de un ticket de carga de combustible de estacion de servicio.
Devuelve EXCLUSIVAMENTE un unico objeto JSON, sin prosa ni markdown, con estas claves exactas:
fecha; hora; litros; km_hora; remito; ruc_emisor; razon_social_emisor; producto;
nro_tarjeta; confidence (objeto por campo, solo para las claves de datos anteriores y con valores
entre 0 y 1); warnings (array de textos).
Usa null cuando un dato no sea visible. Lee SOLO lo que esta impreso en la imagen; no inventes.

Para fecha usa la impresa en el ticket (DD/MM/YYYY). Si viene como DD/MM/YY (dos digitos para el
anio), completa el siglo asumiendo 20YY.
Para hora usa HH:MM:SS o HH:MM tal como aparezca; si no se ve, null.
Para litros toma el valor del campo Cantidad (o Cantidad 1) impreso en el ticket. Copia los
digitos y separadores tal cual aparecen; no conviertas unidades.
Para km_hora toma el valor del campo "Km. del vehiculo" o "Km del vehiculo" del ticket; es el
odometro del camion, normalmente de 4 a 6 digitos sin decimales.
Para remito toma el numero del campo "Comprobante Nro" o "BOLETA" del ticket. En el sistema
paraguayo INFONET suele ser de 7 digitos; copia solo digitos.
Para ruc_emisor copia el RUC de la estacion tal como aparece (formato paraguayo XXXXXXXX-Y o
XXXXXXXX/Y). Si no se distingue, null.
Para razon_social_emisor copia la razon social visible (PETROBRAS, LIDER EXPRESS, etc.).
Para producto copia el nombre del combustible tal cual (DIESEL EURO 5 S-50, NAFTA GRID, etc.).
Para nro_tarjeta copia el numero de tarjeta de flota; si esta enmascarado como *********0334,
copia solo los ultimos 4 digitos en un string aparte o el valor completo si esta visible.

confidence por campo entre 0 y 1 segun cuan legible este cada dato (1 = cristalino, 0 = ilegible).
warnings: array de strings cortos describiendo problemas (ej. "imagen borrosa", "ticket cortado",
"sin RUC visible")."""

FUEL_REMITO_INTERNO_PROMPT = """Analiza la imagen de un remito interno manuscrito de combustible.
Devuelve EXCLUSIVAMENTE un unico objeto JSON, sin prosa ni markdown, con estas claves exactas:
fecha; hora; litros; kilometros; remito; lugar_carga; patente_observada; firmante; contacto;
tipo; confidence (objeto por campo, solo para las claves de datos anteriores y con valores entre
0 y 1); warnings (array de textos).
Usa null cuando un dato no sea visible. Los campos manuscritos son los mas ruidosos: leelos
caritativo y refleja baja confianza (0.3-0.6) cuando la letra no sea clara.

Para fecha toma la del campo Fecha del remito (formato DD/MM/YY o DD/MM/YYYY).
Para hora toma la del campo Hora (HH:MM si aparece, si no null).
Para litros toma el valor del campo Litros manuscrito. Acepta enteros o decimales con punto
o coma como separador.
Para kilometros toma el valor del campo Kilometros manuscrito. Es la distancia recorrida o el
odometro, no asumas cual: refleja lo que diga el papel.
Para remito toma el numero del campo "N" o "No" del remito (6 digitos tipicamente).
Para lugar_carga transcribe el lugar escrito a mano (mejor esfuerzo, refleja confianza baja si
no se lee).
Para patente_observada transcribe la patente escrita a mano (formato ABC123).
Para firmante transcribe el nombre del firmante ("Recib Conforme" / "Aclaracion").
Para contacto copia el email o telefono si aparecen en el membrete.
Para tipo copia el valor del campo TIPO (ej. "INTERNO/GASOIL", "INTERNO/NAFTA"); refleja solo
lo que diga el papel.

confidence por campo entre 0 y 1. Para campos manuscritos usa 0.3-0.6 cuando la letra sea
regular, 0.1-0.3 cuando sea ilegible. Para campos impresos del membrete 0.8-1.0.
warnings: array de strings describiendo problemas (ej. "letra ilegible en lugar_carga", "foto
inclinada", "falta el campo Hora")."""


def _trip_schema() -> VisionSchema:
    required = {
        "fecha_remision", "fecha_remito", "fecha_ticket",
        "remito_tipo", "remito_sucursal", "remito_numero",
        "cliente_candidato", "proveedor_candidato",
        "peso_bruto", "tara", "neto", "unidad_peso",
        "patente_observada", "chofer_observado",
        "confidence", "warnings",
    }
    text_fields = {
        "fecha_remision", "fecha_remito", "fecha_ticket",
        "remito_tipo", "remito_sucursal", "remito_numero",
        "cliente_candidato", "proveedor_candidato",
        "unidad_peso", "patente_observada", "chofer_observado",
    }
    weight_fields = {"peso_bruto", "tara", "neto"}
    return VisionSchema(
        required=frozenset(required),
        text_fields=frozenset(text_fields),
        weight_fields=frozenset(weight_fields),
    )


def _fuel_ticket_schema() -> VisionSchema:
    required = {
        "fecha", "hora", "litros", "km_hora", "remito",
        "ruc_emisor", "razon_social_emisor", "producto",
        "nro_tarjeta", "confidence", "warnings",
    }
    text_fields = {
        "fecha", "hora", "litros", "km_hora", "remito",
        "ruc_emisor", "razon_social_emisor", "producto",
        "nro_tarjeta",
    }
    return VisionSchema(
        required=frozenset(required),
        text_fields=frozenset(text_fields),
    )


def _fuel_remito_schema() -> VisionSchema:
    required = {
        "fecha", "hora", "litros", "kilometros", "remito",
        "lugar_carga", "patente_observada", "firmante", "contacto",
        "tipo", "confidence", "warnings",
    }
    text_fields = {
        "fecha", "hora", "litros", "kilometros", "remito",
        "lugar_carga", "patente_observada", "firmante", "contacto",
        "tipo",
    }
    return VisionSchema(
        required=frozenset(required),
        text_fields=frozenset(text_fields),
    )


TRIP_SCHEMA = _trip_schema()
FUEL_TICKET_SCHEMA = _fuel_ticket_schema()
FUEL_REMITO_SCHEMA = _fuel_remito_schema()


def _argv(command: str | list[str]) -> list[str]:
    if isinstance(command, list):
        result = list(command)
    else:
        stripped = command.strip()
        if stripped.startswith("["):
            try:
                result = json.loads(stripped)
            except json.JSONDecodeError:
                raise MiniMaxVisionConfigurationError("Comando MiniMax Vision invalido") from None
        elif os.name == "nt":
            import ctypes
            argc = ctypes.c_int()
            parser = ctypes.windll.shell32.CommandLineToArgvW
            parser.restype = ctypes.POINTER(ctypes.c_wchar_p)
            pointer = parser(stripped, ctypes.byref(argc))
            if not pointer:
                raise MiniMaxVisionConfigurationError("Comando MiniMax Vision invalido")
            try:
                result = [pointer[index] for index in range(argc.value)]
            finally:
                ctypes.windll.kernel32.LocalFree(pointer)
        else:
            result = shlex.split(command, posix=True)
    if not result or any(not isinstance(item, str) or not item for item in result):
        raise MiniMaxVisionConfigurationError("Comando MiniMax Vision invalido")
    return result


def _messages(image: Path, prompt: str) -> list[dict[str, Any]]:
    return [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "registro-viajes", "version": "1.0"},
        }},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "understand_image",
            "arguments": {"image_source": str(image), "prompt": PROMPT},
        }},
    ]


class _SubprocessExecutor:
    def __call__(self, *, argv, messages, env, timeout_seconds, max_output_bytes):
        process_options = {"start_new_session": True} if os.name != "nt" else {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
        }
        proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, shell=False, **process_options,
        )
        pgid = getattr(proc, "pid", None) if os.name != "nt" else None
        chunks: queue.Queue[Any] = queue.Queue(maxsize=32)
        budget_lock = threading.Lock()
        overflow_event = threading.Event()
        total = 0

        def reader(kind, stream):
            nonlocal total
            try:
                while True:
                    read_chunk = getattr(stream, "read1", stream.read)
                    data = read_chunk(4096)
                    if not data:
                        break
                    with budget_lock:
                        total += len(data)
                        exceeded = total > max_output_bytes
                        if exceeded:
                            overflow_event.set()
                    chunks.put(("overflow" if exceeded else kind, b"" if exceeded else data))
                    if exceeded:
                        break
            except Exception:
                chunks.put(("eof", kind))
            finally:
                chunks.put(("eof", kind))

        readers = [
            threading.Thread(target=reader, args=("stdout", proc.stdout), daemon=True),
            threading.Thread(target=reader, args=("stderr", proc.stderr), daemon=True),
        ]
        for thread in readers:
            thread.start()
        deadline = time.monotonic() + timeout_seconds
        stdout_buffer = bytearray()
        try:
            for index in (0, 2):
                if index == 2:
                    self._send(proc, messages[1])
                self._send(proc, messages[index])
                expected_id = messages[index]["id"]
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    try:
                        kind, data = chunks.get(timeout=remaining)
                    except queue.Empty as exc:
                        raise TimeoutError from exc
                    if kind == "overflow":
                        raise OverflowError
                    if kind != "stdout":
                        continue
                    stdout_buffer.extend(data)
                    while b"\n" in stdout_buffer:
                        raw, _, remainder = stdout_buffer.partition(b"\n")
                        stdout_buffer[:] = remainder
                        try:
                            response = json.loads(raw.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                        if response.get("id") == expected_id:
                            break
                    else:
                        continue
                    break
                if "error" in response:
                    break
        finally:
            try:
                if proc.stdin:
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass
                if proc.poll() is None:
                    try:
                        if os.name == "nt" and getattr(proc, "pid", None):
                            subprocess.run(
                                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                shell=False, check=False, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=2,
                            )
                        elif os.name != "nt" and getattr(proc, "pid", None):
                            import signal
                            os.killpg(proc.pid, signal.SIGTERM)
                        else:
                            proc.terminate()
                    except Exception:
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                    try:
                        proc.wait(timeout=2)
                    except Exception:
                        try:
                            if os.name != "nt" and getattr(proc, "pid", None):
                                import signal
                                os.killpg(proc.pid, signal.SIGKILL)
                            else:
                                proc.kill()
                        except Exception:
                            pass
                        try:
                            proc.wait(timeout=2)
                        except Exception:
                            pass
                if pgid is not None:
                    try:
                        import signal
                        os.killpg(pgid, getattr(signal, "SIGKILL", 9))
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                drain_deadline = time.monotonic() + 2
                while any(thread.is_alive() for thread in readers) and time.monotonic() < drain_deadline:
                    try:
                        chunks.get(timeout=0.02)
                    except queue.Empty:
                        pass
                for thread in readers:
                    thread.join(timeout=max(0, drain_deadline - time.monotonic()))
            finally:
                for handle in (proc.stdin, proc.stdout, proc.stderr):
                    if handle:
                        try:
                            handle.close()
                        except Exception:
                            pass
        if overflow_event.is_set():
            raise OverflowError
        return response

    @staticmethod
    def _send(proc, message):
        proc.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        proc.stdin.flush()


class MiniMaxVisionClient:
    def __init__(
        self, api_key: str | None = None, executor: Callable[..., dict] | None = None,
        command: str | list[str] | None = None, timeout_seconds: float | None = None,
        max_output_bytes: int | None = None,
    ):
        self._api_key = api_key
        self._executor = executor or _SubprocessExecutor()
        self._command = command
        self._timeout = timeout_seconds
        self._max_output = max_output_bytes

    def __repr__(self):
        return f"{type(self).__name__}(configured={bool(self._api_key or os.getenv('MINIMAX_API_KEY'))})"

    def analyze(
        self,
        image_path: Path,
        prompt: str | None = None,
        schema: VisionSchema | None = None,
    ) -> dict[str, Any]:
        used_prompt = prompt if prompt is not None else PROMPT
        used_schema = schema if schema is not None else TRIP_SCHEMA
        key = self._api_key or os.getenv("MINIMAX_API_KEY")
        if not key:
            raise MiniMaxVisionConfigurationError("MINIMAX_API_KEY no esta configurada")
        command = self._command if self._command is not None else os.getenv("MINIMAX_VISION_COMMAND", "uvx minimax-coding-plan-mcp -y")
        try:
            argv = _argv(command)
            timeout = float(self._timeout if self._timeout is not None else os.getenv("MINIMAX_VISION_TIMEOUT_SECONDS", "90"))
            maximum = int(self._max_output if self._max_output is not None else os.getenv("MINIMAX_VISION_MAX_OUTPUT_BYTES", str(1024 * 1024)))
            if not math.isfinite(timeout) or timeout <= 0 or maximum <= 0:
                raise ValueError
        except (TypeError, ValueError, MiniMaxVisionConfigurationError):
            raise MiniMaxVisionConfigurationError("Configuracion MiniMax Vision invalida") from None
        failure = None
        timed_out = False
        response = None
        try:
            env = os.environ.copy()
            env["MINIMAX_API_KEY"] = key
            env["MINIMAX_API_HOST"] = os.getenv("MINIMAX_API_HOST") or "https://api.minimax.io"
            response = self._executor(
                argv=argv, messages=_messages(Path(image_path), used_prompt), env=env,
                timeout_seconds=timeout, max_output_bytes=maximum,
            )
        except MiniMaxVisionError:
            failure = "No se pudo ejecutar MiniMax Vision"
        except TimeoutError:
            failure = "MiniMax Vision excedio el tiempo limite"
            timed_out = True
        except OverflowError:
            failure = "MiniMax Vision excedio el limite de salida"
        except Exception:
            failure = "Fallo la comunicacion con MiniMax Vision"
        if failure is not None:
            if timed_out:
                raise MiniMaxVisionTimeoutError(failure)
            raise MiniMaxVisionError(failure)
        return _parse_response(response, used_schema)


def _parse_response(response: Any, schema: VisionSchema) -> dict[str, Any]:
    parsed = None
    try:
        if not isinstance(response, dict) or "error" in response:
            raise ValueError
        result = response["result"]
        if not isinstance(result, dict) or result.get("isError") is True:
            raise ValueError
        content = result["content"]
        if not isinstance(content, list) or not all(isinstance(item, dict) for item in content):
            raise TypeError
        texts = [item["text"] for item in content if item.get("type") == "text" and isinstance(item.get("text"), str)]
        if len(texts) != 1:
            raise ValueError
        text = texts[0].strip()
        fenced = re.fullmatch(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fenced:
            text = fenced.group(1)
        value = json.loads(text, parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
        if not isinstance(value, dict):
            raise ValueError
        _validate(value, schema)
        parsed = {key: value[key] for key in schema.required}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass
    if parsed is None:
        raise MiniMaxVisionError("Respuesta MiniMax Vision invalida")
    return parsed


def _validate(value: dict[str, Any], schema: VisionSchema) -> None:
    if set(value) != set(schema.required):
        raise ValueError
    if any(value[key] is not None and not isinstance(value[key], str) for key in schema.text_fields):
        raise TypeError
    if any(
        value[key] is not None and (
            isinstance(value[key], bool)
            or not isinstance(value[key], (int, float, str))
            or (isinstance(value[key], (int, float)) and not math.isfinite(value[key]))
            or (isinstance(value[key], str) and value[key].strip().lower() in {
                "nan", "+nan", "-nan", "inf", "+inf", "-inf",
                "infinity", "+infinity", "-infinity",
            })
        )
        for key in schema.weight_fields
    ):
        raise TypeError
    confidence_fields = schema.confidence_fields
    if not isinstance(value["confidence"], dict) or not all(
        key in confidence_fields
        and score is not None
        and not isinstance(score, bool)
        and isinstance(score, (int, float))
        and math.isfinite(score)
        and 0 <= score <= 1
        for key, score in value["confidence"].items()
    ):
        raise TypeError
    if not isinstance(value["warnings"], list) or not all(isinstance(item, str) for item in value["warnings"]):
        raise TypeError
