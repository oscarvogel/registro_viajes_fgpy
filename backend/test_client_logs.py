#!/usr/bin/env python
"""Script para testear el endpoint de logs del cliente"""

import requests
import json
from datetime import datetime

# URL del endpoint
API_URL = "http://localhost:8000/api/logs/client"

# Payload de prueba
payload = {
    "logs": [
        {
            "timestamp": datetime.now().isoformat(),
            "level": "info",
            "message": "Log de prueba desde script Python",
            "event_type": "test",
            "page": "/test-page",
            "component": "test_script",
            "user_id": None,
            "user_agent": "Python Test Script",
            "duration_ms": None,
            "error_name": None,
            "error_message": None,
            "error_stack": None,
            "extra": {"test": True}
        },
        {
            "timestamp": datetime.now().isoformat(),
            "level": "error",
            "message": "Error de prueba",
            "event_type": "error_test",
            "page": "/test-page",
            "component": "test_script",
            "user_id": 1,
            "user_agent": "Python Test Script",
            "duration_ms": 150,
            "error_name": "TestError",
            "error_message": "Este es un error de prueba",
            "error_stack": "Stack trace simulado",
            "extra": {"test": True, "error_code": 500}
        }
    ],
    "device_info": {
        "platform": "Python Test",
        "version": "1.0.0"
    }
}

print("[TEST] Enviando logs de prueba al backend...")
print(f"URL: {API_URL}")
print(f"Payload: {json.dumps(payload, indent=2)}\n")

try:
    response = requests.post(API_URL, json=payload)
    
    print(f"[OK] Status Code: {response.status_code}")
    print(f"[RESPUESTA] {response.json()}")
    
    if response.status_code == 200:
        print("\n[OK] ¡Logs enviados correctamente!")
        print("Revisa la consola del backend (terminal uvicorn) para ver los logs impresos.")
    else:
        print(f"\n[ERROR] {response.status_code}")
        
except requests.exceptions.ConnectionError:
    print("[ERROR] No se pudo conectar al backend.")
    print("Asegúrate de que el backend esté corriendo en http://localhost:8000")
except Exception as e:
    print(f"[ERROR] Error inesperado: {e}")
