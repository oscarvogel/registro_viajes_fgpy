import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess
import sys
import textwrap

from backend.minimax_vision import (
    MiniMaxVisionClient,
    MiniMaxVisionConfigurationError,
    MiniMaxVisionError,
    _SubprocessExecutor,
    _argv,
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
        self.assertEqual(call["argv"], ["uvx", "minimax-coding-plan-mcp", "-y"])
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

    def test_json_parse_error_discards_sensitive_payload_from_entire_exception_chain(self):
        sensitive = "MINIMAX_API_KEY=top-secret provider payload"
        response = {"result": {"content": [{"type": "text", "text": sensitive}]}}
        with self.assertRaises(MiniMaxVisionError) as caught:
            self.client(FakeExecutor(response)).analyze(self.image)

        pending = [caught.exception]
        seen = set()
        while pending:
            error = pending.pop()
            if error is None or id(error) in seen:
                continue
            seen.add(id(error))
            exposed = [str(error), repr(error), repr(error.args), repr(getattr(error, "doc", None))]
            self.assertTrue(all("top-secret" not in value for value in exposed))
            pending.extend([error.__cause__, error.__context__])
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

    def test_malformed_content_entries_are_sanitized_errors(self):
        for entry in (1, "top-secret", None, [], ["top-secret"]):
            with self.subTest(entry=entry):
                response = {"result": {"content": [entry]}}
                with self.assertRaises(MiniMaxVisionError) as caught:
                    self.client(FakeExecutor(response)).analyze(self.image)
                self.assertNotIsInstance(caught.exception, AttributeError)
                self.assertNotIn("top-secret", str(caught.exception))
                self.assertNotIn("top-secret", repr(caught.exception.__cause__))
                self.assertNotIn("top-secret", repr(caught.exception.__context__))

    def test_executor_failures_are_explicit_and_sanitized(self):
        for error in (TimeoutError("top-secret timeout"), OverflowError("top-secret oversized")):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(MiniMaxVisionError) as caught:
                    self.client(FakeExecutor(error=error)).analyze(self.image)
                self.assertNotIn("top-secret", str(caught.exception))
                self.assertNotIn("top-secret", repr(caught.exception.__cause__))

    def test_executor_domain_error_is_recreated_without_foreign_secret(self):
        foreign = MiniMaxVisionError("MINIMAX_API_KEY=top-secret raw response")
        with self.assertRaises(MiniMaxVisionError) as caught:
            self.client(FakeExecutor(error=foreign)).analyze(self.image)
        error = caught.exception
        exposed = (str(error), repr(error), repr(error.args), repr(error.__cause__), repr(error.__context__))
        self.assertTrue(all("top-secret" not in value for value in exposed))
        self.assertIsNot(error, foreign)
        self.assertEqual(str(error), "No se pudo ejecutar MiniMax Vision")

    def test_schema_requires_all_fields_and_types(self):
        invalid_values = []
        for key in VALID:
            value = dict(VALID)
            value.pop(key)
            invalid_values.append(value)
        invalid_values.extend([
            {**VALID, "confidence": []},
            {**VALID, "warnings": "none"},
            {**VALID, "peso_bruto": []},
        ])
        for value in invalid_values:
            with self.subTest(keys=value.keys()):
                with self.assertRaises(MiniMaxVisionError):
                    self.client(FakeExecutor(tool_response(value))).analyze(self.image)

    def test_mcp_tool_error_rejects_even_valid_looking_content(self):
        response = {"result": {"isError": True, "content": [{"type": "text", "text": json.dumps(VALID)}]}}
        with self.assertRaises(MiniMaxVisionError):
            self.client(FakeExecutor(response)).analyze(self.image)

    def test_result_must_be_object(self):
        for result in (None, [], "top-secret"):
            with self.subTest(result=result):
                with self.assertRaises(MiniMaxVisionError) as caught:
                    self.client(FakeExecutor({"result": result})).analyze(self.image)
                self.assertNotIn("top-secret", repr(caught.exception))

    def test_schema_rejects_extra_keys_nonfinite_and_bad_confidence(self):
        values = [
            {**VALID, "extra": "unexpected"},
            {**VALID, "peso_bruto": float("inf")},
            {**VALID, "peso_bruto": "NaN"},
            {**VALID, "confidence": {"unknown": 0.5}},
            {**VALID, "confidence": {"fecha_remision": 1.1}},
            {**VALID, "confidence": {"fecha_remision": float("nan")}},
        ]
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(MiniMaxVisionError):
                    self.client(FakeExecutor(tool_response(value))).analyze(self.image)

    def test_json_constants_nan_and_infinity_are_rejected(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            raw = json.dumps(VALID).replace("12000", constant, 1)
            with self.subTest(constant=constant):
                with self.assertRaises(MiniMaxVisionError):
                    self.client(FakeExecutor({"result": {"content": [{"type": "text", "text": raw}]}})).analyze(self.image)

    def test_weight_strings_are_boundary_values_not_normalized_here(self):
        value = {**VALID, "peso_bruto": "12.000,50"}
        self.assertEqual(self.client(FakeExecutor(tool_response(value))).analyze(self.image)["peso_bruto"], "12.000,50")

    def test_invalid_runtime_configuration_fails_before_executor(self):
        for kwargs in ({"timeout_seconds": 0}, {"max_output_bytes": 0}, {"command": []}):
            executor = FakeExecutor(tool_response())
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(MiniMaxVisionConfigurationError):
                    self.client(executor, **kwargs).analyze(self.image)
                self.assertEqual(executor.calls, [])

    def test_defaults_are_bounded_and_configurable(self):
        executor = FakeExecutor(tool_response())
        with patch.dict(os.environ, {
            "MINIMAX_VISION_TIMEOUT_SECONDS": "12",
            "MINIMAX_VISION_MAX_OUTPUT_BYTES": "2048",
        }):
            self.client(executor).analyze(self.image)
        self.assertEqual(executor.calls[0]["timeout_seconds"], 12)
        self.assertEqual(executor.calls[0]["max_output_bytes"], 2048)

    def test_timeout_closes_all_process_streams_when_both_waits_fail(self):
        class Stream:
            def __init__(self):
                self.closed = False

            def write(self, value):
                return len(value)

            def flush(self):
                pass

            def close(self):
                self.closed = True

            def __iter__(self):
                return iter(())

        class Process:
            def __init__(self):
                self.stdin, self.stdout, self.stderr = Stream(), Stream(), Stream()
                self.wait_count = 0

            def poll(self):
                return None

            def terminate(self):
                pass

            def kill(self):
                pass

            def wait(self, timeout):
                self.wait_count += 1
                raise subprocess.TimeoutExpired("top-secret", timeout)

        process = Process()
        with patch("backend.minimax_vision.subprocess.Popen", return_value=process):
            with self.assertRaises(MiniMaxVisionError) as caught:
                MiniMaxVisionClient(api_key="top-secret", timeout_seconds=1e-9).analyze(self.image)
        self.assertIn("tiempo limite", str(caught.exception))
        self.assertNotIn("top-secret", str(caught.exception))
        self.assertEqual(process.wait_count, 2)
        self.assertTrue(all(stream.closed for stream in (process.stdin, process.stdout, process.stderr)))

    def test_command_parser_supports_json_argv_and_windows_quotes(self):
        self.assertEqual(_argv('["C:\\\\Program Files\\\\uvx.exe", "arg with spaces", "-y"]'), [
            "C:\\Program Files\\uvx.exe", "arg with spaces", "-y",
        ])
        if os.name == "nt":
            self.assertEqual(_argv('"C:\\Program Files\\uvx.exe" "arg with spaces" -y'), [
                "C:\\Program Files\\uvx.exe", "arg with spaces", "-y",
            ])

    def test_real_fake_mcp_handshake_and_large_stderr(self):
        response = _SubprocessExecutor()(
            argv=self._fake_mcp_argv("normal"), messages=self._protocol_messages(),
            env=os.environ.copy(), timeout_seconds=10, max_output_bytes=256 * 1024,
        )
        self.assertEqual(response["id"], 2)
        self.assertEqual(response["result"]["content"][0]["text"], "{}")

    def test_newline_free_oversized_stdout_is_bounded(self):
        with self.assertRaises(OverflowError):
            _SubprocessExecutor()(
                argv=self._fake_mcp_argv("oversize"), messages=self._protocol_messages(),
                env=os.environ.copy(), timeout_seconds=10, max_output_bytes=4096,
            )

    def test_valid_final_response_cannot_race_later_oversized_stderr(self):
        for attempt in range(5):
            with self.subTest(attempt=attempt):
                with self.assertRaises(OverflowError):
                    _SubprocessExecutor()(
                        argv=self._fake_mcp_argv("late_stderr"), messages=self._protocol_messages(),
                        env=os.environ.copy(), timeout_seconds=10, max_output_bytes=4096,
                    )

    def test_windows_process_group_and_tree_kill_are_requested(self):
        if os.name != "nt":
            self.skipTest("Windows-specific process tree contract")
        process = type("Process", (), {
            "pid": 4321, "stdin": None, "stdout": None, "stderr": None,
            "poll": lambda self: None,
            "terminate": lambda self: None,
            "kill": lambda self: None,
            "wait": lambda self, timeout: None,
        })()
        with patch("backend.minimax_vision.subprocess.Popen", return_value=process) as popen, \
                patch("backend.minimax_vision.subprocess.run") as run:
            with self.assertRaises(MiniMaxVisionError):
                MiniMaxVisionClient(api_key="safe", timeout_seconds=1e-9).analyze(self.image)
        self.assertTrue(popen.call_args.kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP)
        self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "4321", "/T", "/F"])
        self.assertFalse(run.call_args.kwargs["shell"])

    @staticmethod
    def _protocol_messages():
        from backend.minimax_vision import _messages
        return _messages(Path("image.jpg"))

    @staticmethod
    def _fake_mcp_argv(mode):
        code = textwrap.dedent(r'''
            import json, sys
            mode = sys.argv[1]
            if mode == "oversize":
                sys.stdout.buffer.write(b"x" * 20000); sys.stdout.buffer.flush()
                sys.stdin.read(); raise SystemExit
            init = json.loads(sys.stdin.readline())
            if mode != "late_stderr":
                sys.stderr.buffer.write(b"e" * 65536); sys.stderr.buffer.flush()
            print(json.dumps({"jsonrpc":"2.0","id":init["id"],"result":{}}), flush=True)
            notification = json.loads(sys.stdin.readline())
            call = json.loads(sys.stdin.readline())
            assert notification["method"] == "notifications/initialized"
            assert call["method"] == "tools/call"
            print(json.dumps({"jsonrpc":"2.0","id":call["id"],"result":{"content":[{"type":"text","text":"{}"}]}}), flush=True)
            if mode == "late_stderr":
                sys.stderr.buffer.write(b"z" * 100000); sys.stderr.buffer.flush()
        ''')
        return [sys.executable, "-u", "-c", code, mode]


if __name__ == "__main__":
    unittest.main()
