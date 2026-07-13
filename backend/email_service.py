"""
Servicio de envío de emails para reportes del sistema.
Soporta emails HTML con datos de logs y métricas.
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

from logger import app_logger
import html

load_dotenv()


class EmailService:
    """Servicio para envío de emails con reportes del sistema"""
    
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", self.smtp_user)
        self.report_recipient = os.getenv("REPORT_EMAIL", "oscar@forestalgaruhape.com.ar")
        self.alert_recipient = os.getenv("ALERT_EMAIL", self.report_recipient)
        self.alert_cooldown_minutes = int(os.getenv("ALERT_COOLDOWN_MINUTES", "15"))
        self._last_alert_sent: Dict[str, datetime] = {}
        
    def send_email(self, to_email: str, subject: str, html_body: str, 
                   text_body: str = None, attachments: List[Path] = None) -> bool:
        """
        Envía un email con contenido HTML y opcionalmente adjuntos.
        
        Args:
            to_email: Destinatario
            subject: Asunto del email
            html_body: Cuerpo del email en HTML
            text_body: Cuerpo alternativo en texto plano
            attachments: Lista de rutas de archivos a adjuntar
            
        Returns:
            True si el envío fue exitoso, False en caso contrario
        """
        try:
            # Validar configuración
            if not self.smtp_user or not self.smtp_password:
                app_logger.error("Configuración SMTP incompleta. Verifica SMTP_USER y SMTP_PASSWORD")
                return False
            
            # Crear mensaje
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            msg['Date'] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
            
            # Agregar cuerpo texto plano (fallback)
            if text_body:
                part1 = MIMEText(text_body, 'plain', 'utf-8')
                msg.attach(part1)
            
            # Agregar cuerpo HTML
            part2 = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(part2)
            
            # Agregar adjuntos si existen
            if attachments:
                for attachment_path in attachments:
                    if attachment_path.exists():
                        with open(attachment_path, 'rb') as f:
                            part = MIMEApplication(f.read(), Name=attachment_path.name)
                            part['Content-Disposition'] = f'attachment; filename="{attachment_path.name}"'
                            msg.attach(part)
            
            # Enviar email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            app_logger.info(f"Email enviado exitosamente a {to_email}: {subject}")
            return True
            
        except Exception as e:
            app_logger.error(f"Error enviando email a {to_email}: {str(e)}", exc_info=True)
            return False
    
    def send_daily_report(self, report_data: dict) -> bool:
        """
        Envía el reporte diario con métricas del sistema.
        
        Args:
            report_data: Diccionario con datos del reporte
            
        Returns:
            True si el envío fue exitoso
        """
        subject = f"Reporte Diario - Sistema Registro de Viajes - {datetime.now().strftime('%d/%m/%Y')}"
        
        html_body = self._generate_report_html(report_data)
        text_body = self._generate_report_text(report_data)
        
        return self.send_email(
            to_email=self.report_recipient,
            subject=subject,
            html_body=html_body,
            text_body=text_body
        )

    def _can_send_alert(self, dedupe_key: str) -> bool:
        """Evita spam de alertas repetidas dentro de una ventana de tiempo."""
        now = datetime.now()
        last_sent = self._last_alert_sent.get(dedupe_key)
        if last_sent is None:
            self._last_alert_sent[dedupe_key] = now
            return True

        if now - last_sent >= timedelta(minutes=self.alert_cooldown_minutes):
            self._last_alert_sent[dedupe_key] = now
            return True

        return False

    def send_critical_error_alert(
        self,
        title: str,
        error: str,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        dedupe_key: Optional[str] = None,
    ) -> bool:
        """Envía alerta inmediata por errores críticos de producción (con anti-spam)."""
        if not self.alert_recipient:
            app_logger.warning("ALERT_EMAIL no configurado: alerta crítica omitida")
            return False

        key = dedupe_key or f"{method or 'N/A'}|{endpoint or 'N/A'}|{status_code or 'N/A'}|{title}"
        if not self._can_send_alert(key):
            app_logger.warning(f"Alerta suprimida por cooldown para clave={key}")
            return False

        timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        details = details or {}
        # Escape details to avoid HTML injection
        details_html = "".join(
            f"<li><strong>{html.escape(str(k))}:</strong> {html.escape(str(v))}</li>" for k, v in details.items()
        )
        details_text = "\n".join(f"- {k}: {v}" for k, v in details.items())

        subject = f"[ALERTA PRODUCCION] {title}"
        html_body = f"""
        <html>
        <body style=\"font-family: Arial, sans-serif;\"> 
            <h2 style=\"color: #b42318;\">Alerta Crítica - Registro de Viajes</h2>
            <p><strong>Fecha/Hora:</strong> {timestamp}</p>
            <p><strong>Título:</strong> {title}</p>
            <p><strong>Endpoint:</strong> {endpoint or 'N/A'}</p>
            <p><strong>Método:</strong> {method or 'N/A'}</p>
            <p><strong>Status:</strong> {status_code or 'N/A'}</p>
            <p><strong>Error:</strong> {html.escape(str(error))}</p>
            <h3>Detalles</h3>
            <ul>
                {details_html or '<li>Sin detalles adicionales</li>'}
            </ul>
            <p style=\"color: #667085; font-size: 12px;\">Esta alerta se deduplica por {self.alert_cooldown_minutes} minutos para evitar spam.</p>
        </body>
        </html>
        """

        text_body = (
            "ALERTA CRITICA - REGISTRO DE VIAJES\n"
            f"Fecha/Hora: {timestamp}\n"
            f"Titulo: {title}\n"
            f"Endpoint: {endpoint or 'N/A'}\n"
            f"Metodo: {method or 'N/A'}\n"
            f"Status: {status_code or 'N/A'}\n"
            f"Error: {error}\n\n"
            "Detalles:\n"
            f"{details_text or '- Sin detalles adicionales'}\n"
        )

        sent = self.send_email(
            to_email=self.alert_recipient,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

        if sent:
            app_logger.warning(f"Alerta crítica enviada a {self.alert_recipient}: {title}")

        return sent
    
    def _generate_report_html(self, data: dict) -> str:
        """Genera el HTML del reporte diario"""
        
        # Extraer datos
        period = data.get('period', {})
        metrics = data.get('metrics', {})
        errors = data.get('errors', [])
        top_endpoints = data.get('top_endpoints', [])
        top_users = data.get('top_users', [])
        performance = data.get('performance', {})
        
        # Construir HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px; }}
                .container {{ max-width: 800px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; margin-top: 30px; border-left: 4px solid #3498db; padding-left: 10px; }}
                .metric {{ display: inline-block; margin: 10px 20px 10px 0; padding: 15px; background-color: #ecf0f1; border-radius: 5px; min-width: 150px; }}
                .metric-label {{ font-size: 12px; color: #7f8c8d; text-transform: uppercase; }}
                .metric-value {{ font-size: 28px; font-weight: bold; color: #2c3e50; }}
                .error {{ background-color: #ffe6e6; padding: 10px; margin: 10px 0; border-left: 4px solid #e74c3c; }}
                .warning {{ background-color: #fff3cd; padding: 10px; margin: 10px 0; border-left: 4px solid #f39c12; }}
                .success {{ background-color: #d4edda; padding: 10px; margin: 10px 0; border-left: 4px solid #27ae60; }}
                table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
                th {{ background-color: #3498db; color: white; padding: 12px; text-align: left; }}
                td {{ padding: 10px; border-bottom: 1px solid #ecf0f1; }}
                tr:hover {{ background-color: #f8f9fa; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ecf0f1; color: #7f8c8d; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📊 Reporte Diario - Sistema Registro de Viajes</h1>
                <p><strong>Período:</strong> {period.get('start', 'N/A')} - {period.get('end', 'N/A')}</p>
                
                <h2>📈 Métricas Generales</h2>
                <div>
                    <div class="metric">
                        <div class="metric-label">Total Peticiones</div>
                        <div class="metric-value">{metrics.get('total_requests', 0):,}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Peticiones Exitosas</div>
                        <div class="metric-value">{metrics.get('successful_requests', 0):,}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Errores Backend</div>
                        <div class="metric-value" style="color: #e74c3c;">{metrics.get('error_count', 0):,}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Errores Frontend</div>
                        <div class="metric-value" style="color: #e67e22;">{metrics.get('frontend_errors', 0):,}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Eventos Frontend</div>
                        <div class="metric-value">{metrics.get('frontend_events', 0):,}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Usuarios Activos</div>
                        <div class="metric-value">{metrics.get('unique_users', 0):,}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Viajes Registrados</div>
                        <div class="metric-value">{metrics.get('trips_created', 0):,}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Cargas Combustible</div>
                        <div class="metric-value">{metrics.get('fuel_loads', 0):,}</div>
                    </div>
                </div>
                
                <h2>⚡ Rendimiento</h2>
                <div class="{"success" if performance.get("avg_response_time", 999) < 500 else "warning"}">
                    <strong>Tiempo de Respuesta Promedio:</strong> {performance.get('avg_response_time', 0):.2f} ms<br>
                    <strong>Tiempo Máximo:</strong> {performance.get('max_response_time', 0):.2f} ms<br>
                    <strong>Tiempo Mínimo:</strong> {performance.get('min_response_time', 0):.2f} ms
                </div>
        """
        
        # Endpoints más usados
        if top_endpoints:
            html += """
                <h2>🔝 Endpoints Más Usados</h2>
                <table>
                    <tr>
                        <th>Endpoint</th>
                        <th>Método</th>
                        <th>Peticiones</th>
                        <th>Tiempo Promedio</th>
                    </tr>
            """
            for endpoint in top_endpoints[:10]:
                html += f"""
                    <tr>
                        <td>{endpoint.get('path', 'N/A')}</td>
                        <td>{endpoint.get('method', 'N/A')}</td>
                        <td>{endpoint.get('count', 0):,}</td>
                        <td>{endpoint.get('avg_time', 0):.2f} ms</td>
                    </tr>
                """
            html += "</table>"
        
        # Usuarios más activos
        if top_users:
            html += """
                <h2>👥 Usuarios Más Activos</h2>
                <table>
                    <tr>
                        <th>Usuario</th>
                        <th>Acciones</th>
                    </tr>
            """
            for user in top_users[:10]:
                html += f"""
                    <tr>
                        <td>{user.get('user_id', 'N/A')}</td>
                        <td>{user.get('action_count', 0):,}</td>
                    </tr>
                """
            html += "</table>"
        
        # Errores recientes
        if errors:
            html += f"""
                <h2>❌ Errores Recientes ({len(errors)} errores)</h2>
            """
            for error in errors[:10]:  # Mostrar solo los 10 más recientes
                html += f"""
                <div class="error">
                    <strong>{error.get('timestamp', 'N/A')}</strong><br>
                    <strong>Tipo:</strong> {error.get('level', 'ERROR')}<br>
                    <strong>Mensaje:</strong> {error.get('message', 'N/A')}<br>
                    <strong>Ubicación:</strong> {error.get('module', 'N/A')} - {error.get('function', 'N/A')}:{error.get('line', 'N/A')}
                </div>
                """
        else:
            html += """
                <h2>✅ Errores</h2>
                <div class="success">
                    No se registraron errores en el período.
                </div>
            """
        
        # Footer
        html += f"""
                <div class="footer">
                    <p>Este reporte fue generado automáticamente el {datetime.now().strftime('%d/%m/%Y a las %H:%M:%S')}</p>
                    <p>Sistema de Registro de Viajes - Forestal Garuhapé</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _generate_report_text(self, data: dict) -> str:
        """Genera versión texto plano del reporte"""
        period = data.get('period', {})
        metrics = data.get('metrics', {})
        errors = data.get('errors', [])
        
        text = f"""
REPORTE DIARIO - SISTEMA REGISTRO DE VIAJES
============================================

Período: {period.get('start', 'N/A')} - {period.get('end', 'N/A')}

MÉTRICAS GENERALES
------------------
Total Peticiones: {metrics.get('total_requests', 0):,}
Peticiones Exitosas: {metrics.get('successful_requests', 0):,}
Errores: {metrics.get('error_count', 0):,}
Usuarios Activos: {metrics.get('unique_users', 0):,}
Viajes Registrados: {metrics.get('trips_created', 0):,}
Cargas Combustible: {metrics.get('fuel_loads', 0):,}

ERRORES
-------
Total de errores: {len(errors)}

Generado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
        """
        
        return text


# Instancia global del servicio
email_service = EmailService()
