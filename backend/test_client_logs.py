#!/usr/bin/env python
"""Prueba aislada y utilidad manual del endpoint de logs del cliente."""

import json
import unittest
from datetime import datetime
from unittest.mock import Mock

import requests


API_URL = "http://localhost:8000/api/logs/client"


def build_payload(now=None):
    timestamp = (now or datetime.now)().isoformat()
    return {
        "logs": [
            {
                "timestamp": timestamp,
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
                "extra": {"test": True},
            },
            {
                "timestamp": timestamp,
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
                "extra": {"test": True, "error_code": 500},
            },
        ],
        "device_info": {"platform": "Python Test", "version": "1.0.0"},
    }


def send_test_logs(post=requests.post, now=None):
    payload = build_payload(now)
    return payload, post(API_URL, json=payload)


class ClientLogScriptTest(unittest.TestCase):
    def test_payload_is_stable_and_json_serializable(self):
        payload = build_payload(lambda: datetime(2026, 7, 13, 10, 30))
        self.assertEqual(len(payload["logs"]), 2)
        self.assertEqual(payload["logs"][0]["timestamp"], "2026-07-13T10:30:00")
        self.assertEqual(payload["logs"][1]["extra"]["error_code"], 500)
        json.dumps(payload)

    def test_send_uses_injected_post_without_network(self):
        response = Mock(status_code=200)
        post = Mock(return_value=response)
        payload, result = send_test_logs(
            post=post, now=lambda: datetime(2026, 7, 13, 10, 30)
        )
        post.assert_called_once_with(API_URL, json=payload)
        self.assertIs(result, response)


def main():
    print("[TEST] Enviando logs de prueba al backend...")
    try:
        payload, response = send_test_logs()
        print(f"URL: {API_URL}")
        print(f"Payload: {json.dumps(payload, indent=2)}\n")
        print(f"[OK] Status Code: {response.status_code}")
        print(f"[RESPUESTA] {response.json()}")
        if response.status_code == 200:
            print("\n[OK] Logs enviados correctamente!")
            print("Revisa la consola del backend para ver los logs impresos.")
        else:
            print(f"\n[ERROR] {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("[ERROR] No se pudo conectar al backend.")
        print("Asegurate de que el backend este corriendo en http://localhost:8000")
    except Exception as error:
        print(f"[ERROR] Error inesperado: {error}")


if __name__ == "__main__":
    main()
