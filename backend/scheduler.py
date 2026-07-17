"""
Scheduler para tareas automatizadas del sistema.
Ejecuta el envío de reportes diarios y otras tareas programadas.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

from logger import app_logger
from metrics_collector import metrics_collector
from email_service import email_service

load_dotenv()


class TaskScheduler:
    """Gestiona tareas programadas del sistema"""
    
    def __init__(self, scheduler=None):
        self.scheduler = scheduler or BackgroundScheduler()
        self.report_time = os.getenv("DAILY_REPORT_TIME", "08:00")  # Hora para enviar reporte (HH:MM)
        
    def start(self):
        """Inicia el scheduler con todas las tareas configuradas"""
        # Parsear hora del reporte
        try:
            hour, minute = map(int, self.report_time.split(':'))
        except ValueError:
            app_logger.warning(f"Formato de hora inválido: {self.report_time}. Usando 08:00 por defecto.")
            hour, minute = 8, 0
        
        # Programar reporte diario
        self.scheduler.add_job(
            func=self.send_daily_report,
            trigger=CronTrigger(hour=hour, minute=minute),
            id='daily_report',
            name='Envío de reporte diario',
            replace_existing=True
        )

        if os.getenv("VIAJE_IMAGE_STORAGE_DIR") and os.getenv("IMAGE_TOKEN_SECRET"):
            cleanup_time = os.getenv("TRIP_IMAGE_CLEANUP_TIME", "03:00")
            try:
                cleanup_hour, cleanup_minute = map(int, cleanup_time.split(':'))
                if not (0 <= cleanup_hour <= 23 and 0 <= cleanup_minute <= 59):
                    raise ValueError
            except ValueError:
                cleanup_hour, cleanup_minute = 3, 0
                app_logger.warning("Formato de hora de limpieza de imágenes inválido. Usando 03:00.")
            self.scheduler.add_job(
                func=self.cleanup_trip_images_job,
                trigger=CronTrigger(hour=cleanup_hour, minute=cleanup_minute),
                id="trip_image_cleanup",
                name="Limpieza de evidencias de viaje",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        
        # Programar limpieza de logs antiguos (mensual, primer día del mes a las 2 AM)
        self.scheduler.add_job(
            func=self.cleanup_old_logs,
            trigger=CronTrigger(day=1, hour=2, minute=0),
            id='log_cleanup',
            name='Limpieza de logs antiguos',
            replace_existing=True
        )
        
        # Iniciar scheduler
        self.scheduler.start()
        app_logger.info(f"Scheduler iniciado. Reporte diario programado para las {hour:02d}:{minute:02d}")
        
    def stop(self):
        """Detiene el scheduler"""
        self.scheduler.shutdown()
        app_logger.info("Scheduler detenido")
    
    def send_daily_report(self):
        """Tarea: Enviar reporte diario por email"""
        app_logger.info("Iniciando generación de reporte diario...")
        
        try:
            # Recopilar métricas del día anterior
            metrics = metrics_collector.collect_daily_metrics()
            
            # Enviar email con el reporte
            success = email_service.send_daily_report(metrics)
            
            if success:
                app_logger.info("Reporte diario enviado exitosamente")
            else:
                app_logger.error("Error al enviar el reporte diario")
                
        except Exception as e:
            app_logger.error(f"Error generando/enviando reporte diario: {str(e)}", exc_info=True)
    
    def cleanup_old_logs(self):
        """Tarea: Limpiar logs antiguos (más de 60 días)"""
        app_logger.info("Iniciando limpieza de logs antiguos...")
        
        try:
            from pathlib import Path
            from datetime import timedelta
            
            log_dir = Path(__file__).parent / "logs"
            cutoff_date = datetime.now() - timedelta(days=60)
            
            deleted_count = 0
            for log_file in log_dir.glob("*.log.*"):
                # Verificar fecha de modificación
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    log_file.unlink()
                    deleted_count += 1
                    app_logger.info(f"Eliminado log antiguo: {log_file.name}")
            
            app_logger.info(f"Limpieza completada. {deleted_count} archivos eliminados.")
            
        except Exception as e:
            app_logger.error(f"Error en limpieza de logs: {str(e)}", exc_info=True)

    def cleanup_trip_images_job(self):
        """Run image cleanup with lazy configuration and DB dependencies."""
        if not os.getenv("VIAJE_IMAGE_STORAGE_DIR") or not os.getenv("IMAGE_TOKEN_SECRET"):
            app_logger.info("Limpieza de evidencias omitida: almacenamiento no configurado")
            return
        db = None
        try:
            from database import SessionLocal
            from image_storage import ImageStorage
            from trip_image_cleanup import cleanup_trip_images

            db = SessionLocal()
            result = cleanup_trip_images(db, ImageStorage(), datetime.now(timezone.utc))
            app_logger.info(
                "Limpieza de evidencias completada: vencidas=%d temporales=%d huérfanas=%d inválidas=%d errores=%d",
                result.expired_deleted, result.temp_deleted, result.orphan_deleted,
                result.invalid_promotions, len(result.errors),
            )
            for code in result.errors:
                app_logger.warning("Limpieza de evidencias: %s", code)
        except Exception:
            app_logger.error("Limpieza de evidencias falló")
        finally:
            if db is not None:
                db.close()
    
    def send_test_report(self):
        """Envía un reporte de prueba inmediatamente (útil para testing)"""
        app_logger.info("Enviando reporte de prueba...")
        self.send_daily_report()
    
    def get_scheduled_jobs(self):
        """Retorna información sobre las tareas programadas"""
        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time.strftime('%d/%m/%Y %H:%M:%S') if job.next_run_time else 'N/A'
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': next_run,
            })
        return jobs


# Instancia global del scheduler
task_scheduler = TaskScheduler()
