import argparse
import os
import smtplib
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent


REQUIRED_ENV = [
    "DATABASE_URL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM_EMAIL",
    "REPORT_EMAIL",
]

RECOMMENDED_ENV = [
    "ALERT_EMAIL",
    "ENABLE_ERROR_ALERT_EMAILS",
    "DAILY_REPORT_TIME",
    "SENTRY_DSN",
    "SENTRY_ENV",
    "SENTRY_RELEASE",
    "APP_ENV",
    "JWT_SECRET_KEY",
    "JWT_ALGORITHM",
    "JWT_EXPIRE_MINUTES",
    "AUTH_ENFORCEMENT_MODE",
]


def mask_value(name, value):
    if value is None or value == "":
        return "<missing>"

    sensitive = ("PASSWORD", "SECRET", "TOKEN", "DATABASE_URL", "DSN", "SMTP_USER", "EMAIL")
    if any(part in name.upper() for part in sensitive):
        return "<set>"

    return value


def print_result(ok, label, detail=""):
    status = "OK" if ok else "FAIL"
    line = f"[{status}] {label}"
    if detail:
        line += f" - {detail}"
    print(line)


def print_env_template():
    print(
        """# Required
DATABASE_URL=mysql+mysqlconnector://USUARIO:PASSWORD@HOST/BASE
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=usuario@example.com
SMTP_PASSWORD=password_o_app_password
SMTP_FROM_EMAIL=usuario@example.com
REPORT_EMAIL=destino_reportes@example.com

# Recommended
ALERT_EMAIL=destino_alertas@example.com
ENABLE_ERROR_ALERT_EMAILS=true
DAILY_REPORT_TIME=08:00
SENTRY_DSN=https://PUBLIC_KEY@oXXXX.ingest.sentry.io/PROJECT_ID
SENTRY_ENV=production
SENTRY_RELEASE=2026.05.24
APP_ENV=production
JWT_SECRET_KEY=generar_una_clave_larga_aleatoria
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=720
AUTH_ENFORCEMENT_MODE=compat
"""
    )


def check_environment(strict, allow_sqlite):
    ok = True

    print("== Variables de entorno ==")
    for name in REQUIRED_ENV:
        value = os.getenv(name)
        present = bool(value)
        print_result(present, name, mask_value(name, value))
        ok = ok and present

    for name in RECOMMENDED_ENV:
        value = os.getenv(name)
        present = bool(value)
        print_result(present or not strict, name, mask_value(name, value) if present else "recommended")
        if strict:
            ok = ok and present

    database_url = os.getenv("DATABASE_URL", "")
    if database_url.startswith("sqlite") and not allow_sqlite:
        print_result(False, "DATABASE_URL no debe ser SQLite en produccion", "use MySQL en el servidor")
        ok = False

    return ok


def check_imports():
    print("\n== Imports backend ==")
    try:
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
        import uvicorn  # noqa: F401

        print_result(True, "Dependencias principales")
    except Exception as exc:
        print_result(False, "Dependencias principales", str(exc))
        return False

    try:
        import main  # noqa: F401

        print_result(True, "Import main.py")
        return True
    except Exception as exc:
        print_result(False, "Import main.py", str(exc))
        return False


def check_database():
    print("\n== Base de datos ==")
    try:
        from sqlalchemy import text
        from database import engine

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        print_result(True, "Conexion DATABASE_URL", "SELECT 1")
        return True
    except Exception as exc:
        print_result(False, "Conexion DATABASE_URL", str(exc))
        return False


def check_health(url):
    print("\n== Health check HTTP ==")
    if not url:
        print_result(True, "Health check omitido")
        return True

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read(500).decode("utf-8", errors="replace")
            ok = 200 <= response.status < 300
            print_result(ok, url, f"status={response.status} body={body}")
            return ok
    except urllib.error.HTTPError as exc:
        print_result(False, url, f"status={exc.code}")
    except Exception as exc:
        print_result(False, url, str(exc))

    return False


def check_smtp_login():
    print("\n== SMTP login ==")
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")

    if not host or not user or not password:
        print_result(False, "SMTP login", "faltan SMTP_HOST, SMTP_USER o SMTP_PASSWORD")
        return False

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
        print_result(True, "SMTP login", f"{host}:{port} user={user}")
        return True
    except Exception as exc:
        print_result(False, "SMTP login", str(exc))
        return False


def main():
    parser = argparse.ArgumentParser(description="Verifica configuracion de produccion de Registro Viajes.")
    parser.add_argument("--health-url", default="http://127.0.0.1:8000/api/admin/health")
    parser.add_argument("--skip-db", action="store_true", help="No verifica conexion a base de datos.")
    parser.add_argument("--smtp-login", action="store_true", help="Intenta login SMTP real, sin enviar email.")
    parser.add_argument("--strict", action="store_true", help="Falla si faltan variables recomendadas.")
    parser.add_argument("--allow-sqlite", action="store_true", help="Permite DATABASE_URL sqlite para pruebas locales.")
    parser.add_argument("--no-dotenv", action="store_true", help="No carga backend/.env; util para comprobar solo entorno real.")
    parser.add_argument("--print-env-template", action="store_true", help="Imprime plantilla de variables y sale.")
    args = parser.parse_args()

    if args.print_env_template:
        print_env_template()
        return 0

    if not args.no_dotenv:
        load_dotenv(ROOT_DIR / ".env")

    checks = [
        check_environment(args.strict, args.allow_sqlite),
        check_imports(),
        True if args.skip_db else check_database(),
        check_health(args.health_url),
    ]

    if args.smtp_login:
        checks.append(check_smtp_login())

    print("\n== Resultado ==")
    if all(checks):
        print_result(True, "Servidor listo para esta verificacion")
        return 0

    print_result(False, "Hay puntos para corregir antes de continuar")
    return 1


if __name__ == "__main__":
    sys.exit(main())
