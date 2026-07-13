"""
Recopilador de métricas y analizador de logs.
Procesa archivos de log para generar estadísticas de uso.
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Any
import re

from logger import LOG_DIR, app_logger


class MetricsCollector:
    """Recopila y analiza métricas del sistema desde los logs"""
    
    def __init__(self):
        self.log_dir = LOG_DIR
        
    def collect_daily_metrics(self, date: datetime = None) -> Dict[str, Any]:
        """
        Recopila métricas del día especificado (o el día anterior si no se especifica).
        
        Args:
            date: Fecha para la cual recopilar métricas (default: ayer)
            
        Returns:
            Diccionario con todas las métricas recopiladas
        """
        if date is None:
            date = datetime.now() - timedelta(days=1)
        
        # Definir período
        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        app_logger.info(f"Recopilando métricas del {start_date} al {end_date}")
        
        # Recopilar datos de diferentes fuentes
        json_logs = self._parse_json_logs(start_date, end_date)
        error_logs = self._parse_error_logs(start_date, end_date)
        
        # Calcular métricas
        metrics = {
            'period': {
                'start': start_date.strftime('%d/%m/%Y %H:%M'),
                'end': end_date.strftime('%d/%m/%Y %H:%M'),
            },
            'metrics': self._calculate_general_metrics(json_logs),
            'performance': self._calculate_performance_metrics(json_logs),
            'top_endpoints': self._get_top_endpoints(json_logs),
            'top_users': self._get_top_users(json_logs),
            'errors': error_logs,
            'system_health': self._assess_system_health(json_logs, error_logs),
        }
        
        app_logger.info(f"Métricas recopiladas: {metrics['metrics']['total_requests']} peticiones, "
                       f"{metrics['metrics']['error_count']} errores")
        
        return metrics
    
    def _parse_json_logs(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Parsea los logs JSON dentro del rango de fechas"""
        logs = []
        
        # Leer archivo JSON del día
        json_log_files = [
            self.log_dir / "app_json.log",
        ]
        
        # Incluir archivos rotados si existen
        for i in range(1, 8):  # Buscar hasta 7 días atrás
            rotated_file = self.log_dir / f"app_json.log.{start_date.strftime('%Y-%m-%d')}"
            if rotated_file.exists():
                json_log_files.append(rotated_file)
        
        json_log_files = list(dict.fromkeys(json_log_files))

        for log_file in json_log_files:
            if not log_file.exists():
                continue
                
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            log_entry = json.loads(line)
                            timestamp = datetime.fromisoformat(log_entry.get('timestamp', ''))
                            
                            if start_date <= timestamp <= end_date:
                                logs.append(log_entry)
                        except (json.JSONDecodeError, ValueError) as e:
                            # Ignorar líneas mal formadas
                            continue
            except Exception as e:
                app_logger.error(f"Error leyendo {log_file}: {e}")
        
        return logs
    
    def _parse_error_logs(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Parsea los logs de errores dentro del rango de fechas"""
        errors = []
        error_log_file = self.log_dir / "errors.log"
        
        if not error_log_file.exists():
            return errors
        
        try:
            with open(error_log_file, 'r', encoding='utf-8') as f:
                current_error = None
                
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Buscar líneas con formato de log
                    match = re.match(
                        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (.+?) - (ERROR|CRITICAL) - (.+?):(\d+) - (.+)',
                        line
                    )
                    
                    if match:
                        # Si hay un error anterior, guardarlo
                        if current_error:
                            errors.append(current_error)
                        
                        timestamp_str, logger_name, level, function, line_no, message = match.groups()
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        
                        if start_date <= timestamp <= end_date:
                            current_error = {
                                'timestamp': timestamp.strftime('%d/%m/%Y %H:%M:%S'),
                                'level': level,
                                'logger': logger_name,
                                'function': function,
                                'line': line_no,
                                'message': message,
                                'module': logger_name.split('.')[-1] if '.' in logger_name else logger_name,
                            }
                        else:
                            current_error = None
                    elif current_error:
                        # Agregar líneas adicionales al mensaje (traceback, etc.)
                        current_error['message'] += '\n' + line
                
                # Agregar último error si existe
                if current_error:
                    errors.append(current_error)
                    
        except Exception as e:
            app_logger.error(f"Error leyendo errors.log: {e}")
        
        return errors
    
    def _calculate_general_metrics(self, logs: List[Dict]) -> Dict[str, int]:
        """Calcula métricas generales del sistema"""
        metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'error_count': 0,
            'unique_users': 0,
            'trips_created': 0,
            'fuel_loads': 0,
            'frontend_errors': 0,
            'frontend_events': 0,
        }
        
        users = set()
        
        for log in logs:
            extra = log.get('extra', {})
            log_type = extra.get('type', '')
            
            if log_type == 'api_request':
                metrics['total_requests'] += 1
                
                status_code = extra.get('status_code', 0)
                if 200 <= status_code < 400:
                    metrics['successful_requests'] += 1
                elif status_code >= 400:
                    metrics['error_count'] += 1
                
                user_id = extra.get('user_id')
                if user_id:
                    users.add(user_id)
            
            elif log_type == 'client_log':
                # Métricas del frontend
                metrics['frontend_events'] += 1
                
                user_id = extra.get('user_id')
                if user_id:
                    users.add(user_id)
                
                # Contar errores del frontend
                if log.get('level') in ['ERROR', 'CRITICAL'] or extra.get('event_type') in ['error', 'api_error', 'vue_error']:
                    metrics['frontend_errors'] += 1
            
            elif log_type == 'user_action':
                user_id = extra.get('user_id')
                if user_id:
                    users.add(user_id)
                
                action = extra.get('action', '')
                if 'trip' in action.lower() and 'create' in action.lower():
                    metrics['trips_created'] += 1
                elif 'fuel' in action.lower() and 'load' in action.lower():
                    metrics['fuel_loads'] += 1
            
            elif log.get('level') in ['ERROR', 'CRITICAL']:
                metrics['error_count'] += 1
        
        metrics['unique_users'] = len(users)
        
        return metrics
    
    def _calculate_performance_metrics(self, logs: List[Dict]) -> Dict[str, float]:
        """Calcula métricas de rendimiento"""
        durations = []
        
        for log in logs:
            extra = log.get('extra', {})
            if extra.get('type') == 'api_request':
                duration = extra.get('duration_ms')
                if duration is not None:
                    durations.append(duration)
        
        if not durations:
            return {
                'avg_response_time': 0,
                'max_response_time': 0,
                'min_response_time': 0,
            }
        
        return {
            'avg_response_time': sum(durations) / len(durations),
            'max_response_time': max(durations),
            'min_response_time': min(durations),
        }
    
    def _get_top_endpoints(self, logs: List[Dict], limit: int = 10) -> List[Dict]:
        """Obtiene los endpoints más usados"""
        endpoint_stats = defaultdict(lambda: {'count': 0, 'durations': []})
        
        for log in logs:
            extra = log.get('extra', {})
            if extra.get('type') == 'api_request':
                endpoint = extra.get('endpoint', 'unknown')
                method = extra.get('method', 'GET')
                key = f"{method}:{endpoint}"
                
                endpoint_stats[key]['count'] += 1
                endpoint_stats[key]['method'] = method
                endpoint_stats[key]['path'] = endpoint
                
                duration = extra.get('duration_ms')
                if duration is not None:
                    endpoint_stats[key]['durations'].append(duration)
        
        # Convertir a lista y calcular promedios
        result = []
        for key, stats in endpoint_stats.items():
            avg_time = sum(stats['durations']) / len(stats['durations']) if stats['durations'] else 0
            result.append({
                'method': stats['method'],
                'path': stats['path'],
                'count': stats['count'],
                'avg_time': avg_time,
            })
        
        # Ordenar por cantidad de peticiones
        result.sort(key=lambda x: x['count'], reverse=True)
        return result[:limit]
    
    def _get_top_users(self, logs: List[Dict], limit: int = 10) -> List[Dict]:
        """Obtiene los usuarios más activos"""
        user_actions = Counter()
        
        for log in logs:
            extra = log.get('extra', {})
            user_id = extra.get('user_id')
            
            if user_id:
                user_actions[user_id] += 1
        
        result = [
            {'user_id': user_id, 'action_count': count}
            for user_id, count in user_actions.most_common(limit)
        ]
        
        return result
    
    def _assess_system_health(self, logs: List[Dict], errors: List[Dict]) -> Dict[str, Any]:
        """Evalúa la salud general del sistema"""
        total_requests = sum(1 for log in logs if log.get('extra', {}).get('type') == 'api_request')
        error_count = len(errors)
        
        if total_requests == 0:
            error_rate = 0
        else:
            error_rate = (error_count / total_requests) * 100
        
        # Determinar estado de salud
        if error_rate < 1:
            health_status = 'excellent'
            health_message = 'Sistema funcionando óptimamente'
        elif error_rate < 5:
            health_status = 'good'
            health_message = 'Sistema funcionando correctamente'
        elif error_rate < 10:
            health_status = 'warning'
            health_message = 'Sistema con advertencias, revisar errores'
        else:
            health_status = 'critical'
            health_message = 'Sistema con problemas críticos, requiere atención'
        
        return {
            'status': health_status,
            'message': health_message,
            'error_rate': round(error_rate, 2),
            'total_errors': error_count,
            'total_requests': total_requests,
        }


# Instancia global del recopilador
metrics_collector = MetricsCollector()
