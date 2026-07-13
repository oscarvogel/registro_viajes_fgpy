import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.minimax_vision import (
    MiniMaxVisionClient,
    MiniMaxVisionConfigurationError,
    MiniMaxVisionError,
)


VALID = {
    "fecha_remision": "2026-07-13",
    "remito_tipo": "001",
    "remito_sucursal": "002",
    "remito_numero": "0000123",
    "proveedor_candidato": "Proveedor SA",
    "peso_bruto": 12000,
    "tara": 4000,
    "neto": 8000,
    "unidad_peso": "kg",
    "patente_observada": "ABC123",
    "chofer_observado": "Ana Perez",
    "confidence": {"fecha_remision": 0.9, "remito_numero": 0.8},
    "warnings": [],
}


class FakeExecutor:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def __call__(self, **kwargs):
        safe = {key: value for key, value in kwargs.items() if key != "env"}
        safe["key_in_env"] = bool(kwargs["env"].get("MINIMAX_API_KEY"))
        self.calls.append(safe)
        if self.error:
            raise self.error
        return self.response


def tool_response(value=VALID):
    return {"result": {"content": [{"type": "text", "text": json.dumps(value)}]}}


class MiniMaxVisionClientTests(unittest.TestCase):
    def setUp(self):
        self.image = Path(tempfile.gettempdir()) / "remito image.jpg"

    def client(self, executor, **kwargs):
        return MiniMaxVisionClient(api_key="top-secret", executor=executor, **kwargs)

    def test_valid_content_returns_object_with_remito(self):
        result = self.client(FakeExecutor(tool_response())).analyze(self.image)
        self.assertEqual(result["remito_numero"], "0000123")

    def test_secret_only_reaches_child_environment(self):
        executor = FakeExecutor(tool_response())
        self.client(executor, command='uvx "minimax-coding-plan-mcp" -y').analyze(self.image)
        call = executor.calls[0]
        self.assertEqual(call["argv"], ["uvx", '"minimax-coding-plan-mcp"', "-y"] if os.name == "nt" else ["uvx", "minimax-coding-plan-mcp", "-y"])
        self.assertTrue(call["key_in_env"])
        self.assertNotIn("top-secret", repr(call))
        self.assertNotIn("top-secret", repr(self.client(executor)))

    def test_missing_key_is_configuration_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MiniMaxVisionConfigurationError):
                MiniMaxVisionClient(executor=FakeExecutor(tool_response())).analyze(self.image)

    def test_path_and_contract_prompt_are_sent_to_understand_image(self):
        executor = FakeExecutor(tool_response())
        self.client(executor).analyze(self.image)
        messages = executor.calls[0]["messages"]
        call = next(message for message in messages if message.get("method") == "tools/call")
        self.assertEqual(call["params"]["name"], "understand_image")
        self.assertEqual(call["params"]["arguments"]["image_source"], str(self.image))
        prompt = call["params"]["arguments"]["prompt"]
        self.assertIn("fecha_remision", prompt)
        self.assertIn("OCR no elige", prompt)
        self.assertNotIn("top-secret", json.dumps(messages))

    def test_single_json_fence_is_accepted(self):
        response = {"result": {"content": [{"type": "text", "text": "```json\n" + json.dumps(VALID) + "\n```"}]}}
        self.assertEqual(self.client(FakeExecutor(response)).analyze(self.image), VALID)

    def test_invalid_provider_responses_are_sanitized_errors(self):
        cases = [
            {"result": {"content": [{"type": "text", "text": "not json top-secret"}]}},
            tool_response([]),
            tool_response(3),
            {"result": {}},
            {"error": {"message": "top-secret provider failure"}},
        ]
        for response in cases:
            with self.subTest(response=repr(response)[:30]):
                with self.assertRaises(MiniMaxVisionError) as caught:
                    self.client(FakeExecutor(response)).analyze(self.image)
                self.assertNotIn("top-secret", str(caught.exception))
                self.assertNotIn("not json", str(caught.exception))

    def test_executor_failures_are_explicit_and_sanitized(self):
        for error in (TimeoutError("top-secret timeout"), OverflowError("top-secret oversized")):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(MiniMaxVisionError) as caught:
                    self.client(FakeExecutor(error=error)).analyze(self.image)
                self.assertNotIn("top-secret", str(caught.exception))
                self.assertNotIn("top-secret", repr(caught.exception.__cause__))

    def test_schema_requires_all_fields_and_types(self):
        invalid_values = []
        for key in VALID:
            value = dict(VALID)
            value.pop(key)
            invalid_values.append(value)
        invalid_values.extend([
            {**VALID, "confidence": []},
            {**VALID, "warnings": "none"},
            {**VALID, "peso_bruto": "12000"},
        ])
        for value in invalid_values:
            with self.subTest(keys=value.keys()):
                with self.assertRaises(MiniMaxVisionError):
                    self.client(FakeExecutor(tool_response(value))).analyze(self.image)

    def test_defaults_are_bounded_and_configurable(self):
        executor = FakeExecutor(tool_response())
        with patch.dict(os.environ, {
            "MINIMAX_VISION_TIMEOUT_SECONDS": "12",
            "MINIMAX_VISION_MAX_OUTPUT_BYTES": "2048",
        }):
            self.client(executor).analyze(self.image)
        self.assertEqual(executor.calls[0]["timeout_seconds"], 12)
        self.assertEqual(executor.calls[0]["max_output_bytes"], 2048)


if __name__ == "__main__":
    unittest.main()
