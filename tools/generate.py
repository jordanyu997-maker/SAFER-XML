#!/usr/bin/env python3
"""调用 LLM 模型生成 HTML，支持 RAG 和 baseline 两种模式。"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from http.client import IncompleteRead
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "generated"
PA11Y_BIN = ROOT / "node_modules" / ".bin" / "pa11y"
DEFAULT_MAX_ROUNDS = 3
MODEL_PROVIDER_CHOICES = ("deepseek", "openai", "anthropic", "ollama")
DEFAULT_API_USER_AGENT = "android-xml-a11y-research/1.0"

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "retrieval"))


class ModelError(RuntimeError):
    """Base class for model provider failures."""

    def __init__(self, message, *, metadata=None):
        super().__init__(message)
        self.metadata = metadata or {}


class ModelConfigurationError(ModelError):
    pass


class ModelAuthenticationError(ModelError):
    pass


class ModelRateLimitError(ModelError):
    pass


class ModelNetworkError(ModelError):
    pass


class ModelServiceError(ModelError):
    pass


class ModelResponseError(ModelError):
    pass


def _api_key(api_key, environment_name, provider_name):
    key = api_key or os.environ.get(environment_name)
    if not key:
        raise ModelConfigurationError(
            f"未设置 {environment_name}。请先执行 "
            f"export {environment_name}='你的Key'。"
        )
    key = key.strip()
    if not key:
        raise ModelConfigurationError(f"{environment_name} 不能为空。")
    if not key.isascii() or any(character.isspace() for character in key):
        raise ModelConfigurationError(
            f"{environment_name} 包含非 ASCII 字符或空白。"
            "请只粘贴 API Key 本身，不要包含引号、说明文字或空格。"
        )
    return key


def _api_url(environment_name, default_base_url, endpoint):
    base_url = os.environ.get(environment_name, default_base_url).rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ModelConfigurationError(
            f"{environment_name} 不是有效的 HTTP(S) 地址: {base_url}"
        )
    if parsed.path.endswith(endpoint):
        return base_url
    return f"{base_url}{endpoint}"


def deepseek_api_key(api_key=None):
    return _api_key(api_key, "DEEPSEEK_API_KEY", "DeepSeek")


def openai_api_key(api_key=None):
    return _api_key(api_key, "OPENAI_API_KEY", "OpenAI")


def anthropic_api_key(api_key=None):
    return _api_key(api_key, "ANTHROPIC_API_KEY", "Anthropic")


def deepseek_api_url():
    return _api_url(
        "DEEPSEEK_BASE_URL",
        "https://api.deepseek.com",
        "/chat/completions",
    )


def openai_api_style():
    style = os.environ.get("OPENAI_API_STYLE", "responses").strip().lower()
    if style not in {"responses", "chat_completions"}:
        raise ModelConfigurationError(
            "OPENAI_API_STYLE 必须是 responses 或 chat_completions。"
        )
    return style


def openai_api_url(style=None):
    style = style or openai_api_style()
    endpoint = "/responses" if style == "responses" else "/chat/completions"
    return _api_url(
        "OPENAI_BASE_URL",
        "https://api.openai.com/v1",
        endpoint,
    )


def anthropic_api_url():
    return _api_url(
        "ANTHROPIC_BASE_URL",
        "https://api.anthropic.com",
        "/v1/messages",
    )


def anthropic_auth_style():
    style = os.environ.get("ANTHROPIC_AUTH_STYLE", "x_api_key").strip().lower()
    if style not in {"x_api_key", "bearer"}:
        raise ModelConfigurationError(
            "ANTHROPIC_AUTH_STYLE 必须是 x_api_key 或 bearer。"
        )
    return style


def anthropic_auth_headers(api_key):
    style = anthropic_auth_style()
    if style == "bearer":
        return {"Authorization": f"Bearer {api_key}"}
    return {"x-api-key": api_key}


def api_client_headers():
    """Return stable, non-secret headers used to identify this API client."""
    headers = {
        "Accept": "application/json",
        "User-Agent": os.environ.get(
            "ANDROID_XML_API_USER_AGENT", DEFAULT_API_USER_AGENT
        ),
    }
    for name, value in headers.items():
        try:
            str(value).encode("latin-1")
        except UnicodeEncodeError as exc:
            raise ModelConfigurationError(
                f"HTTP 请求头 {name} 包含无法编码的字符。"
            ) from exc
    return headers


def validate_model_configuration(provider: str, api_key=None):
    if provider == "deepseek":
        deepseek_api_key(api_key)
        deepseek_api_url()
    elif provider == "openai":
        openai_api_key(api_key)
        openai_api_url()
    elif provider == "anthropic":
        anthropic_api_key(api_key)
        anthropic_api_url()
    elif provider == "ollama":
        if shutil.which("ollama") is None:
            raise ModelConfigurationError("未找到 ollama 命令。")
    else:
        raise ModelConfigurationError(f"不支持的模型提供商: {provider}")


def run_ollama(model: str, prompt: str) -> str:
    result = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ModelServiceError(f"Ollama 调用失败: {result.stderr.strip()}")
    return result.stdout


def _positive_int_environment(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ModelConfigurationError(f"{name} 必须是正整数。") from exc
    if parsed < 1:
        raise ModelConfigurationError(f"{name} 必须是正整数。")
    return parsed


def _boolean_environment(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ModelConfigurationError(
        f"{name} 必须是 true/false、1/0、yes/no 或 on/off。"
    )


def _read_openai_responses_stream(
    response,
    provider_name,
    failure_metadata,
    attempt,
):
    """Read an OpenAI Responses SSE stream into a normal response object."""
    state = {
        "event": None,
        "data_lines": [],
        "text_parts": [],
        "completed": None,
        "last_payload": None,
    }

    def consume_event():
        if not state["data_lines"]:
            state["event"] = None
            return
        raw_data = "\n".join(state["data_lines"])
        event_name = state["event"]
        state["event"] = None
        state["data_lines"] = []
        if raw_data.strip() == "[DONE]":
            return
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise ModelResponseError(
                f"{provider_name} 返回了无法解析的 SSE 数据: "
                f"{raw_data[:500]}",
                metadata=failure_metadata(attempt),
            ) from exc
        if not isinstance(payload, dict):
            return
        state["last_payload"] = payload
        event_type = payload.get("type") or event_name
        if event_type in {
            "error",
            "response.failed",
            "response.incomplete",
        }:
            detail = payload.get("error") or payload.get("response") or payload
            raise ModelServiceError(
                f"{provider_name} 流式响应失败: "
                f"{json.dumps(detail, ensure_ascii=False)[:500]}",
                metadata=failure_metadata(attempt),
            )
        if event_type == "response.output_text.delta":
            delta = payload.get("delta")
            if isinstance(delta, str):
                state["text_parts"].append(delta)
        elif event_type == "response.output_text.done":
            text_value = payload.get("text")
            if isinstance(text_value, str) and not state["text_parts"]:
                state["text_parts"].append(text_value)
        elif event_type == "response.completed":
            completed = payload.get("response")
            state["completed"] = (
                completed if isinstance(completed, dict) else payload
            )
        elif payload.get("status") == "completed" and (
            "output" in payload or "output_text" in payload
        ):
            state["completed"] = payload

    for raw_line in response:
        line = (
            raw_line.decode("utf-8", errors="replace")
            if isinstance(raw_line, bytes)
            else str(raw_line)
        ).rstrip("\r\n")
        if not line:
            consume_event()
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            state["event"] = line[6:].strip()
        elif line.startswith("data:"):
            state["data_lines"].append(line[5:].lstrip())
    consume_event()

    result = state["completed"]
    if not isinstance(result, dict):
        last_payload = state["last_payload"]
        result = dict(last_payload) if isinstance(last_payload, dict) else {}
    streamed_text = "".join(state["text_parts"])
    if streamed_text and not result.get("output_text"):
        result["output_text"] = streamed_text
    if not result or not (
        result.get("output_text") or result.get("output")
    ):
        raise ModelResponseError(
            f"{provider_name} 流式响应未包含文本输出。",
            metadata=failure_metadata(attempt),
        )
    return result


def _post_json(
    provider_name,
    url,
    headers,
    body,
    max_retries,
    timeout,
    response_mode="json",
):
    encoded_body = json.dumps(body).encode("utf-8")
    request_headers = {**api_client_headers(), **headers}
    last_error = None
    last_http_status = None
    last_detail = None
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()

    def failure_metadata(attempts, http_status=None, detail=None):
        return {
            "status": "failed",
            "provider": provider_name.casefold(),
            "requested_model": body.get("model"),
            "resolved_model": None,
            "request_id": None,
            "endpoint": url,
            "started_at": started_at,
            "duration_ms": round(
                (time.perf_counter() - started) * 1000, 3
            ),
            "provider_attempts": attempts,
            "http_status": http_status,
            "error_detail": detail,
            "usage": {},
        }

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            wait = 2 ** attempt
            print(
                f"  {provider_name} 网络重试 ({attempt}/{max_retries})，"
                f"等待 {wait}s...",
                file=sys.stderr,
            )
            time.sleep(wait)

        try:
            request = urllib.request.Request(
                url,
                data=encoded_body,
                headers=request_headers,
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response_mode == "sse":
                    data = _read_openai_responses_stream(
                        response,
                        provider_name,
                        failure_metadata,
                        attempt,
                    )
                else:
                    raw = response.read().decode("utf-8")
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise ModelResponseError(
                            f"{provider_name} 返回了无法解析的 JSON: "
                            f"{raw[:500]}",
                            metadata=failure_metadata(attempt),
                        ) from exc
                response_headers = {
                    str(key).lower(): str(value)
                    for key, value in response.headers.items()
                }
                return {
                    "data": data,
                    "headers": response_headers,
                    "provider_attempts": attempt,
                    "started_at": started_at,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                }
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            last_http_status = exc.code
            last_detail = detail
            if exc.code in {401, 403}:
                raise ModelAuthenticationError(
                    f"{provider_name} API 认证失败 ({exc.code}): {detail}",
                    metadata=failure_metadata(attempt, exc.code, detail),
                ) from exc
            if exc.code == 429:
                last_error = ModelRateLimitError(
                    f"{provider_name} API 请求频率或额度受限 (429): {detail}"
                )
                continue
            if 400 <= exc.code < 500:
                raise ModelServiceError(
                    f"{provider_name} API 请求被拒绝 ({exc.code}): {detail}",
                    metadata=failure_metadata(attempt, exc.code, detail),
                ) from exc
            last_error = exc
        except ModelError:
            raise
        except (IncompleteRead, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc

    if isinstance(last_error, ModelRateLimitError):
        raise ModelRateLimitError(
            str(last_error),
            metadata=failure_metadata(
                max_retries, last_http_status, last_detail
            ),
        ) from last_error
    if isinstance(last_error, urllib.error.HTTPError):
        raise ModelServiceError(
            f"{provider_name} API 服务端错误 ({last_error.code})，"
            f"已重试 {max_retries} 次。",
            metadata=failure_metadata(
                max_retries, last_http_status, last_detail
            ),
        ) from last_error
    raise ModelNetworkError(
        f"无法连接 {provider_name} API，已重试 {max_retries} 次: {last_error}",
        metadata=failure_metadata(max_retries),
    ) from last_error


def model_error_metadata(error, provider=None, requested_model=None):
    """Return non-secret, summary-compatible metadata for a failed call."""
    metadata = dict(getattr(error, "metadata", {}) or {})
    metadata.setdefault("status", "failed")
    metadata.setdefault("provider", provider)
    metadata.setdefault("requested_model", requested_model)
    metadata.setdefault("resolved_model", None)
    metadata.setdefault("request_id", None)
    metadata.setdefault("provider_attempts", 0)
    metadata.setdefault("duration_ms", 0.0)
    metadata.setdefault("usage", {})
    metadata["error_type"] = type(error).__name__
    metadata["error"] = str(error)
    return metadata


def _usage(input_tokens=None, output_tokens=None, total_tokens=None, **extra):
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    result = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
    result.update({key: value for key, value in extra.items() if value is not None})
    return result


def _model_result(
    content,
    provider,
    requested_model,
    response,
    endpoint,
    api_style,
    resolved_model=None,
    request_id=None,
    usage=None,
    finish_reason=None,
    request_options=None,
):
    if not isinstance(content, str) or not content.strip():
        raise ModelResponseError(f"{provider} 返回了空的文本内容。")
    return {
        "content": content,
        "metadata": {
            "provider": provider,
            "requested_model": requested_model,
            "resolved_model": resolved_model or requested_model,
            "request_id": request_id,
            "endpoint": endpoint,
            "api_style": api_style,
            "started_at": response["started_at"],
            "duration_ms": response["duration_ms"],
            "provider_attempts": response["provider_attempts"],
            "usage": usage or _usage(),
            "finish_reason": finish_reason,
            "request_options": request_options or {},
        },
    }


def run_ollama_with_metadata(model: str, prompt: str):
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    content = run_ollama(model, prompt)
    return {
        "content": content,
        "metadata": {
            "provider": "ollama",
            "requested_model": model,
            "resolved_model": model,
            "request_id": None,
            "endpoint": "ollama CLI",
            "api_style": "ollama_cli",
            "started_at": started_at,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "provider_attempts": 1,
            "usage": _usage(),
            "finish_reason": None,
            "request_options": {},
        },
    }


def run_deepseek_api_with_metadata(
    model: str,
    prompt: str,
    api_key=None,
    max_retries=3,
    timeout=180,
):
    api_key = deepseek_api_key(api_key)
    url = deepseek_api_url()
    max_tokens = _positive_int_environment("LLM_MAX_OUTPUT_TOKENS", 65536)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": max_tokens,
    }
    response = _post_json(
        "DeepSeek",
        url,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        body,
        max_retries,
        timeout,
    )
    data = response["data"]
    try:
        choice = data["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelResponseError(
            f"DeepSeek 返回了无法识别的响应: {json.dumps(data)[:500]}"
        ) from exc
    raw_usage = data.get("usage") or {}
    return _model_result(
        content,
        "deepseek",
        model,
        response,
        url,
        "chat_completions",
        resolved_model=data.get("model"),
        request_id=data.get("id") or response["headers"].get("x-request-id"),
        usage=_usage(
            raw_usage.get("prompt_tokens"),
            raw_usage.get("completion_tokens"),
            raw_usage.get("total_tokens"),
            cache_hit_input_tokens=(
                raw_usage.get("prompt_cache_hit_tokens")
                or raw_usage.get("prompt_tokens_details", {}).get("cached_tokens")
            ),
        ),
        finish_reason=choice.get("finish_reason"),
        request_options={
            "temperature": 1.0,
            "top_p": 1.0,
            "max_output_tokens": max_tokens,
        },
    )


def run_deepseek_api(
    model: str,
    prompt: str,
    api_key=None,
    max_retries=3,
    timeout=180,
) -> str:
    """通过 DeepSeek API (OpenAI 兼容) 调用模型，失败自动重试。"""
    return run_deepseek_api_with_metadata(
        model,
        prompt,
        api_key,
        max_retries,
        timeout,
    )["content"]


def run_openai_api_with_metadata(
    model: str,
    prompt: str,
    api_key=None,
    max_retries=3,
    timeout=180,
):
    api_key = openai_api_key(api_key)
    style = openai_api_style()
    url = openai_api_url(style)
    max_tokens = _positive_int_environment("LLM_MAX_OUTPUT_TOKENS", 16384)
    stream = style == "responses" and _boolean_environment(
        "OPENAI_RESPONSES_STREAM", False
    )
    if style == "responses":
        body = {
            "model": model,
            "input": prompt,
            "max_output_tokens": max_tokens,
        }
        if stream:
            body["stream"] = True
    else:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
    response = _post_json(
        "OpenAI",
        url,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        },
        body,
        max_retries,
        timeout,
        response_mode="sse" if stream else "json",
    )
    data = response["data"]
    if style == "responses":
        content = data.get("output_text")
        if not content:
            text_parts = []
            for item in data.get("output", []):
                for block in item.get("content", []):
                    if block.get("type") in {"output_text", "text"}:
                        text_parts.append(block.get("text", ""))
            content = "".join(text_parts)
        raw_usage = data.get("usage") or {}
        usage = _usage(
            raw_usage.get("input_tokens"),
            raw_usage.get("output_tokens"),
            raw_usage.get("total_tokens"),
            cache_hit_input_tokens=(
                raw_usage.get("input_tokens_details", {}).get("cached_tokens")
            ),
        )
        finish_reason = data.get("status")
    else:
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelResponseError(
                f"OpenAI 返回了无法识别的响应: {json.dumps(data)[:500]}"
            ) from exc
        raw_usage = data.get("usage") or {}
        usage = _usage(
            raw_usage.get("prompt_tokens"),
            raw_usage.get("completion_tokens"),
            raw_usage.get("total_tokens"),
            cache_hit_input_tokens=(
                raw_usage.get("prompt_tokens_details", {}).get("cached_tokens")
            ),
        )
        finish_reason = choice.get("finish_reason")
    return _model_result(
        content,
        "openai",
        model,
        response,
        url,
        style,
        resolved_model=data.get("model"),
        request_id=data.get("id") or response["headers"].get("x-request-id"),
        usage=usage,
        finish_reason=finish_reason,
        request_options={
            "max_output_tokens": max_tokens,
            "stream": stream,
        },
    )


def run_anthropic_api_with_metadata(
    model: str,
    prompt: str,
    api_key=None,
    max_retries=3,
    timeout=180,
):
    api_key = anthropic_api_key(api_key)
    url = anthropic_api_url()
    max_tokens = _positive_int_environment("LLM_MAX_OUTPUT_TOKENS", 16384)
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 1.0,
        "top_p": 1.0,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = _post_json(
        "Anthropic",
        url,
        {
            **anthropic_auth_headers(api_key),
            "anthropic-version": os.environ.get(
                "ANTHROPIC_API_VERSION", "2023-06-01"
            ),
            "Content-Type": "application/json",
        },
        body,
        max_retries,
        timeout,
    )
    data = response["data"]
    content = "".join(
        block.get("text", "")
        for block in data.get("content", [])
        if block.get("type") == "text"
    )
    raw_usage = data.get("usage") or {}
    return _model_result(
        content,
        "anthropic",
        model,
        response,
        url,
        "messages",
        resolved_model=data.get("model"),
        request_id=data.get("id") or response["headers"].get("request-id"),
        usage=_usage(
            raw_usage.get("input_tokens"),
            raw_usage.get("output_tokens"),
            cache_creation_input_tokens=raw_usage.get(
                "cache_creation_input_tokens"
            ),
            cache_hit_input_tokens=raw_usage.get("cache_read_input_tokens"),
        ),
        finish_reason=data.get("stop_reason"),
        request_options={
            "auth_style": anthropic_auth_style(),
            "temperature": 1.0,
            "top_p": 1.0,
            "max_output_tokens": max_tokens,
        },
    )


def run_model_with_metadata(provider: str, model: str, prompt: str, api_key=None):
    """统一模型调用入口，并返回文本和可审计调用元数据。"""
    if provider == "ollama":
        return run_ollama_with_metadata(model, prompt)
    if provider == "deepseek":
        return run_deepseek_api_with_metadata(model, prompt, api_key)
    if provider == "openai":
        return run_openai_api_with_metadata(model, prompt, api_key)
    if provider == "anthropic":
        return run_anthropic_api_with_metadata(model, prompt, api_key)
    raise ModelConfigurationError(f"不支持的模型提供商: {provider}")


def run_model(provider: str, model: str, prompt: str, api_key=None) -> str:
    """统一的模型调用入口。"""
    return run_model_with_metadata(provider, model, prompt, api_key)["content"]


import re


def extract_html(text: str) -> str:
    """从模型输出中提取纯 HTML,去掉 markdown 代码块包裹和前后废话。"""
    # 去掉 ```html ... ``` 包裹
    m = re.search(r"```html\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 去掉 ``` ... ``` 包裹（无语言标记）
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 尝试从 <!DOCTYPE 或 <html 开始截取
    for marker in ("<!DOCTYPE", "<html"):
        idx = text.find(marker)
        if idx != -1:
            return text[idx:].strip()
    return text.strip()


def run_pa11y(html_path: str) -> list[dict]:
    result = subprocess.run(
        [str(PA11Y_BIN), "--reporter", "json", "--standard", "WCAG2AA", html_path],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 2):
        print(f"Pa11y 运行失败: {result.stderr}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def format_pa11y_issues(issues: list[dict]) -> str:
    if not issues:
        return ""
    errors = [i for i in issues if i.get("type") == "error"]
    warnings = [i for i in issues if i.get("type") == "warning"]
    lines = []
    if errors:
        lines.append(f"## Errors ({len(errors)} — MUST fix):")
        for idx, issue in enumerate(errors, 1):
            lines.append(
                f"{idx}. [{issue.get('code', '')}] {issue.get('message', '')}\n"
                f"   Context: {issue.get('context', '')[:200]}\n"
            )
    if warnings:
        lines.append(f"## Warnings ({len(warnings)} — should fix):")
        for idx, issue in enumerate(warnings, 1):
            lines.append(
                f"{idx}. [{issue.get('code', '')}] {issue.get('message', '')}\n"
                f"   Context: {issue.get('context', '')[:200]}\n"
            )
    return "\n".join(lines)


def get_exp_dir(exp_num, filename):
    """确定实验目录。同一组实验的 base.html 和 rag.html 放入同一文件夹。"""
    if exp_num is not None:
        d = GENERATED_DIR / str(exp_num)
        d.mkdir(parents=True, exist_ok=True)
        return d
    # 自动递增：找到最大编号，若该编号下目标文件已存在则 +1
    existing = []
    for p in GENERATED_DIR.iterdir():
        if p.is_dir() and p.name.isdigit():
            existing.append(int(p.name))
    num = max(existing) if existing else 0
    if num == 0:
        num = 1
    else:
        # 当前编号下该文件已存在 → 开新编号
        if (GENERATED_DIR / str(num) / filename).exists():
            num += 1
    d = GENERATED_DIR / str(num)
    d.mkdir(parents=True, exist_ok=True)
    return d


def main():
    parser = argparse.ArgumentParser(
        description="调用 LLM 模型生成无障碍前端代码 (支持 DeepSeek API / Ollama)"
    )
    parser.add_argument("request", help="用户需求，例如：生成一个登录表单")
    parser.add_argument(
        "--provider",
        choices=MODEL_PROVIDER_CHOICES,
        default="deepseek",
        help=(
            "模型提供商: deepseek、openai、anthropic 或 ollama "
            "(default: deepseek)"
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help="模型名 (deepseek default: deepseek-v4-pro, ollama default: gemma3:12b)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key（默认读取对应提供商的环境变量）",
    )
    parser.add_argument(
        "--mode",
        choices=["rag", "base"],
        default="rag",
        help="rag = WCAG 知识库增强 + 自动修复闭环; base = 裸模型直接生成 (default: rag)",
    )
    parser.add_argument("--limit", type=int, default=8, help="RAG 检索文档数 (default: 8)")
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS,
                        help=f"最大修复轮数 (default: {DEFAULT_MAX_ROUNDS})")
    parser.add_argument(
        "--save", action="store_true", help="保存最终输出到 generated/ 目录"
    )
    parser.add_argument(
        "--exp", type=int, default=None,
        help="实验编号，保存到 generated/<N>/ (默认自动递增)",
    )
    parser.add_argument(
        "--print-prompt", action="store_true", help="只打印 prompt，不调用模型"
    )
    args = parser.parse_args()

    # 模型默认值
    if args.model is None:
        defaults = {
            "deepseek": "deepseek-v4-pro",
            "openai": "gpt-5",
            "anthropic": "claude-opus-4-20250514",
            "ollama": "gemma3:12b",
        }
        args.model = defaults[args.provider]

    # ==================== 构建 prompt ====================
    if args.mode == "rag":
        from retrieval.build_rag_prompt import build_prompt
        prompt = build_prompt(args.request, limit=args.limit)
    else:
        prompt = (
            "You are a frontend code generation assistant.\n"
            "Generate complete HTML, CSS, and JavaScript for the following request.\n\n"
            f"User request:\n{args.request}\n\n"
            "Output format:\n1. Complete code\n"
        )

    if args.print_prompt:
        print(prompt)
        return

    # ==================== 生成 ====================
    validate_model_configuration(args.provider, args.api_key)
    mode_info = f"提供商: {args.provider}  |  模型: {args.model}  |  模式: {args.mode}"
    if args.mode == "rag":
        mode_info += f"  |  limit: {args.limit}"
    print(mode_info, file=sys.stderr)
    print("生成中...", file=sys.stderr)
    output = run_model(args.provider, args.model, prompt, args.api_key)

    # ==================== baseline 模式：直接输出 ====================
    if args.mode == "base":
        print(output)
        if args.save:
            exp_dir = get_exp_dir(args.exp, "base.html")
            p = exp_dir / "base.html"
            p.write_text(extract_html(output), encoding="utf-8")
            print(f"已保存: {p}", file=sys.stderr)
        return

    # ==================== RAG 模式：自动修复闭环 ====================
    for round_num in range(1, args.max_rounds + 1):
        # -- 跑 Pa11y（用提取后的纯 HTML）--
        print(f"第 {round_num} 轮 Pa11y 检测中...", file=sys.stderr)
        html_only = extract_html(output)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8", delete=False
        ) as f:
            f.write(html_only)
            tmp_path = f.name

        issues = run_pa11y(tmp_path)
        Path(tmp_path).unlink()

        errors = [i for i in issues if i.get("type") == "error"]
        warnings = [i for i in issues if i.get("type") == "warning"]

        print(
            f"Pa11y 检测结果: {len(errors)} errors, {len(warnings)} warnings",
            file=sys.stderr,
        )

        # 通过了，或者已经是最后一轮，直接输出
        if (len(errors) == 0 and len(warnings) == 0) or round_num == args.max_rounds:
            print(output)

            # 打印检测摘要
            print(f"\n{'='*60}", file=sys.stderr)
            if len(errors) == 0 and len(warnings) == 0:
                print(f"✓ Pa11y WCAG2AA 检测通过！", file=sys.stderr)
            else:
                print(f"Pa11y WCAG2AA 检测结果: {len(errors)} errors, {len(warnings)} warnings", file=sys.stderr)
                for issue in errors + warnings:
                    tag = "❌" if issue.get("type") == "error" else "⚠️"
                    print(f"  {tag} {issue.get('message', '')}", file=sys.stderr)
                print(f"已运行 {args.max_rounds} 轮修复，以上为剩余问题。", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)

            if args.save:
                exp_dir = get_exp_dir(args.exp, "rag.html")
                p = exp_dir / "rag.html"
                p.write_text(extract_html(output), encoding="utf-8")
                print(f"已保存: {p}", file=sys.stderr)
            return

        # -- 有问题，修复 --
        issues_text = format_pa11y_issues(issues)
        repair_prompt = (
            "You are an accessibility-focused frontend developer.\n"
            "Your previous code has accessibility issues that MUST be fixed.\n\n"
            f"## Your Previous Code\n```html\n{output}\n```\n\n"
            f"## Accessibility Issues Detected\n{issues_text}\n\n"
            "## Your Task\n"
            "Fix ALL errors and warnings above.\n"
            "- Every error MUST be resolved (missing labels, alt text, ARIA, contrast, etc.)\n"
            "- Keep existing functionality and layout intact.\n"
            "- Output the complete corrected HTML file.\n"
        )
        print(f"修复中...", file=sys.stderr)
        output = run_model(args.provider, args.model, repair_prompt, args.api_key)


if __name__ == "__main__":
    try:
        main()
    except ModelError as exc:
        print(f"模型调用失败: {exc}", file=sys.stderr)
        sys.exit(1)
