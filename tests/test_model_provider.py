import os
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from tools.generate import (
    ModelConfigurationError,
    ModelNetworkError,
    ModelServiceError,
    deepseek_api_url,
    run_anthropic_api_with_metadata,
    run_deepseek_api,
    run_openai_api_with_metadata,
    validate_model_configuration,
)


class FakeResponse:
    def __init__(self, payload, headers=None):
        self.payload = json.dumps(payload).encode("utf-8")
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


class FakeSseResponse:
    def __init__(self, events, headers=None):
        self.payload = events.encode("utf-8")
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def __iter__(self):
        return iter(self.payload.splitlines(keepends=True))


class ModelProviderTests(unittest.TestCase):
    def test_missing_deepseek_key_is_configuration_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ModelConfigurationError, "DEEPSEEK_API_KEY"):
                validate_model_configuration("deepseek")

    def test_api_key_with_non_ascii_text_is_configuration_error(self):
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "sk-test请粘贴密钥"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ModelConfigurationError, "非 ASCII 字符或空白"
            ):
                validate_model_configuration("deepseek")

    def test_api_key_with_whitespace_is_configuration_error(self):
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "sk-test key"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ModelConfigurationError, "非 ASCII 字符或空白"
            ):
                validate_model_configuration("deepseek")

    def test_invalid_base_url_is_configuration_error(self):
        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "test-key",
                "DEEPSEEK_BASE_URL": "not-a-url",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ModelConfigurationError, "HTTP"):
                deepseek_api_url()

    def test_network_failure_has_specific_exception(self):
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "test-key"},
            clear=True,
        ), patch(
            "tools.generate.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            with self.assertRaisesRegex(ModelNetworkError, "无法连接"):
                run_deepseek_api(
                    "test-model",
                    "prompt",
                    max_retries=1,
                    timeout=1,
                )

    def test_server_failure_records_attempts_status_and_duration(self):
        def gateway_timeout(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                504,
                "Gateway Timeout",
                {},
                io.BytesIO(b"upstream timed out"),
            )

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_API_STYLE": "responses",
            },
            clear=True,
        ), patch(
            "tools.generate.urllib.request.urlopen",
            side_effect=gateway_timeout,
        ), patch("tools.generate.time.sleep"):
            with self.assertRaises(ModelServiceError) as context:
                run_openai_api_with_metadata(
                    "requested-model",
                    "prompt",
                    max_retries=3,
                    timeout=1,
                )

        metadata = context.exception.metadata
        self.assertEqual(metadata["status"], "failed")
        self.assertEqual(metadata["provider_attempts"], 3)
        self.assertEqual(metadata["http_status"], 504)
        self.assertEqual(metadata["requested_model"], "requested-model")
        self.assertGreaterEqual(metadata["duration_ms"], 0)
        self.assertIn("upstream timed out", metadata["error_detail"])

    def test_openai_responses_metadata_records_resolved_model_and_usage(self):
        payload = {
            "id": "resp_123",
            "model": "gpt-resolved",
            "status": "completed",
            "output_text": '{"operations": []}',
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
            },
        }
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_API_STYLE": "responses",
            },
            clear=True,
        ), patch(
            "tools.generate.urllib.request.urlopen",
            return_value=FakeResponse(payload, {"x-request-id": "req_123"}),
        ):
            result = run_openai_api_with_metadata("requested-model", "prompt")

        self.assertEqual(result["content"], '{"operations": []}')
        self.assertEqual(result["metadata"]["resolved_model"], "gpt-resolved")
        self.assertEqual(result["metadata"]["usage"]["total_tokens"], 120)
        self.assertEqual(result["metadata"]["request_id"], "resp_123")

    def test_openai_responses_stream_reassembles_text_and_records_transport(self):
        events = """event: response.created
data: {"type":"response.created","response":{"id":"resp_stream"}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","delta":"{\\"operations\\":"}

event: response.output_text.delta
data: {"type":"response.output_text.delta","delta":" []}"}

event: response.completed
data: {"type":"response.completed","response":{"id":"resp_stream","model":"gpt-streamed","status":"completed","usage":{"input_tokens":30,"output_tokens":4,"total_tokens":34}}}

data: [DONE]

"""

        def fake_urlopen(request, timeout):
            body = json.loads(request.data.decode("utf-8"))
            self.assertTrue(body["stream"])
            self.assertEqual(
                request.get_header("Accept"), "text/event-stream"
            )
            return FakeSseResponse(events, {"x-request-id": "req_stream"})

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_API_STYLE": "responses",
                "OPENAI_RESPONSES_STREAM": "true",
            },
            clear=True,
        ), patch(
            "tools.generate.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            result = run_openai_api_with_metadata(
                "requested-model", "prompt"
            )

        self.assertEqual(result["content"], '{"operations": []}')
        self.assertEqual(result["metadata"]["resolved_model"], "gpt-streamed")
        self.assertEqual(result["metadata"]["usage"]["total_tokens"], 34)
        self.assertEqual(result["metadata"]["request_id"], "resp_stream")
        self.assertTrue(result["metadata"]["request_options"]["stream"])

    def test_anthropic_messages_metadata_records_usage(self):
        payload = {
            "id": "msg_123",
            "model": "claude-resolved",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"operations": []}'}],
            "usage": {"input_tokens": 80, "output_tokens": 12},
        }
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "test-key"},
            clear=True,
        ), patch(
            "tools.generate.urllib.request.urlopen",
            return_value=FakeResponse(payload, {"request-id": "req_456"}),
        ):
            result = run_anthropic_api_with_metadata(
                "requested-claude", "prompt"
            )

        self.assertEqual(result["content"], '{"operations": []}')
        self.assertEqual(
            result["metadata"]["resolved_model"], "claude-resolved"
        )
        self.assertEqual(result["metadata"]["usage"]["total_tokens"], 92)
        self.assertEqual(result["metadata"]["request_id"], "msg_123")

    def test_anthropic_gateway_can_use_bearer_authentication(self):
        payload = {
            "id": "msg_456",
            "model": "claude-gateway-model",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"operations": []}'}],
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }

        def fake_urlopen(request, timeout):
            self.assertEqual(
                request.get_header("Authorization"), "Bearer test-key"
            )
            self.assertIsNone(request.get_header("X-api-key"))
            self.assertEqual(
                request.get_header("User-agent"),
                "android-xml-a11y-research/1.0",
            )
            return FakeResponse(payload)

        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "test-key",
                "ANTHROPIC_AUTH_STYLE": "bearer",
            },
            clear=True,
        ), patch(
            "tools.generate.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            result = run_anthropic_api_with_metadata(
                "requested-claude", "prompt"
            )

        self.assertEqual(
            result["metadata"]["request_options"]["auth_style"], "bearer"
        )


if __name__ == "__main__":
    unittest.main()
