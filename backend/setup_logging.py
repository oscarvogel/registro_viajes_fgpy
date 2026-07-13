#!/usr/bin/env python3
"""
Script de instalación y configuración del sistema de logging y reportes.
Ejecutar: python setup_logging.py
"""
import os
import sys
from pathlib import Path


def print_header(text):
    """Imprime un encabezado decorado"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def print_success(text):
    """Imprime mensaje de éxito"""
    print(f"✅ {text}")


def print_error(text):
    """Imprime mensaje de error"""
    print(f"❌ {text}")


def print_info(text):
    """Imprime mensaje informativo"""
    print(f"ℹ️  {text}")


def check_dependencies():
    """Verifica si las dependencias están instaladas"""
    print_header("Verificando dependencias")
    
    required = [
        'fastapi',
        'uvicorn',
        'sqlalchemy',
        'apscheduler',
        'python-dotenv',
    ]
    
    missing = []
    for package in required:
        try:
            __import__(package.replace('-', '_'))
            print_success(f"{package} instalado")
        except ImportError:
            missing.append(package)
            print_error(f"{package} NO instalado")
    
    return missing


def install_dependencies(missing):
    """Instala dependencias faltantes"""
    if not missing:
        return True
    
    print_header("Instalando dependencias faltantes")
    print_info(f"Paquetes a instalar: {', '.join(missing)}")
    
    import subprocess
    
    try:
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', 
            '-r', 'requirements.txt'
        ])
        print_success("Dependencias instaladas correctamente")
        return True
    except subprocess.CalledProcessError:
        print_error("Error instalando dependencias")
        return False


def create_env_file():
    """Crea o verifica el archivo .env"""
    print_header("Configurando variables de entorno")
    
    env_example = Path('.env.example')
    env_file = Path('.env')
    
    if not env_example.exists():
        print_error(".env.example no encontrado")
        return False
    
    if env_file.exists():
        print_info(".env ya existe. No se sobrescribirá.")
        print_info("Si necesitas reconfigurarlo, edita .env manualmente")
        return True
    
    # Copiar ejemplo
    env_file.write_text(env_example.read_text())
    print_success(".env creado desde .env.example")
    
    # Solicitar configuración básica
    print("\n📧 Configuración de Email SMTP")
    print("-" * 60)
    
    smtp_user = input("Email SMTP (ej: tu_email@gmail.com): ").strip()
    smtp_password = input("Password/App Password: ").strip()
    report_email = input("Email para reportes [oscar@forestalgaruhape.com.ar]: ").strip()
    
    if not report_email:
        report_email = "oscar@forestalgaruhape.com.ar"
    
    # Actualizar .env
    content = env_file.read_text()
    content = content.replace('tu_email@gmail.com', smtp_user)
    content = content.replace('tu_password_o_app_password', smtp_password)
    
    if smtp_user:
        content = content.replace('SMTP_FROM_EMAIL=tu_email@gmail.com', 
                                 f'SMTP_FROM_EMAIL={smtp_user}')
    
    env_file.write_text(content)
    
    print_success("Configuración guardada en .env")
    print_info("⚠️  Mantén este archivo seguro y no lo subas a Git")
    
    return True


def create_logs_directory():
    """Crea el directorio de logs si no existe"""
    print_header("Creando directorio de logs")
    
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)
    
    print_success(f"Directorio de logs: {logs_dir.absolute()}")
    return True


def test_logging_system():
    """Prueba que el sistema de logging funciona"""
    print_header("Probando sistema de logging")
    
    try:
        from logger import app_logger, log_system_event
        
        log_system_event("Sistema de logging instalado y probado", severity="info")
        print_success("Sistema de logging operativo")
        
        logs_dir = Path('logs')
        log_files = list(logs_dir.glob('*.log'))
        
        if log_files:
            print_info(f"Archivos de log creados: {len(log_files)}")
            for log_file in log_files:
                print(f"  - {log_file.name}")
        
        return True
    except Exception as e:
        print_error(f"Error probando logging: {e}")
        return False


def show_next_steps():
    """Muestra los siguientes pasos"""
    print_header("🎉 Instalación Completada")
    
    print("""
Los siguientes pasos:

1. 🚀 Iniciar la aplicación:
   uvicorn main:app --reload

2. ✅ Verificar que funciona:
   curl http://localhost:8000/api/admin/health

3. 📧 Enviar reporte de prueba:
   curl -X POST http://localhost:8000/api/admin/test-report

4. 📋 Ver tareas programadas:
   curl http://localhost:8000/api/admin/scheduled-jobs

5. 📊 Ver logs:
   - backend/logs/app.log          (logs generales)
   - backend/logs/errors.log       (solo errores)
   - backend/logs/app_json.log     (formato JSON)

📧 Los reportes se enviarán automáticamente cada día a las 08:00

📖 Para más información, consulta:
   - QUICK_START.md (guía rápida)
   - LOGGING_README.md (documentación completa)

⚠️  IMPORTANTE:
   - Si usas Gmail, necesitas un App Password (no tu contraseña normal)
   - Activa 2FA en tu cuenta de Google primero
   - Edita .env si necesitas cambiar la configuración
""")


def main():
    """Ejecuta el proceso de instalación"""
    print_header("🔧 Setup Sistema de Logging y Reportes")
    print("Sistema de Registro de Viajes - Forestal Garuhapé")
    
    # Cambiar al directorio backend si es necesario
    backend_dir = Path(__file__).parent
    os.chdir(backend_dir)
    
    # 1. Verificar dependencias
    missing = check_dependencies()
    
    # 2. Instalar si faltan
    if missing:
        response = input("\n¿Instalar dependencias faltantes? (s/n): ").lower()
        if response == 's':
            if not install_dependencies(missing):
                print_error("No se pudo completar la instalación")
                return 1
        else:
            print_info("Instalación cancelada. Instala manualmente con:")
            print("  pip install -r requirements.txt")
            return 1
    
    # 3. Configurar .env
    if not create_env_file():
        return 1
    
    # 4. Crear directorio de logs
    if not create_logs_directory():
        return 1
    
    # 5. Probar sistema
    if not test_logging_system():
        print_error("Advertencia: El sistema de logging no se pudo probar")
        print_info("Verifica la configuración e intenta iniciar la aplicación")
    
    # 6. Mostrar siguiente pasos
    show_next_steps()
    
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n❌ Instalación cancelada por el usuario")
        sys.exit(1)
    except Exception as e:
        print_error(f"Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
