"""Small OpenAI-compatible client using only the Python standard library."""
import http.client
import json
import math
import random
import re
import socket
import ssl
import sys
import threading
import time
from urllib.parse import urlsplit

from settings import Settings


_DIAGNOSTIC_LOCK = threading.Lock()
_RECOVERY_INSTRUCTION = (
    "Предыдущая генерация не поместилась в лимит. Сформируй ответ заново, "
    "кратко и полностью, в исходно запрошенном формате. Сохрани подтверждённые "
    "факты и существенные условия; убери повторы и необязательные пояснения. "
    "Не выводи рассуждения. Используй те же исходные сообщения и источники."
)


class ModelError(RuntimeError):
    """Safe, typed diagnostic: never contains a URL, key or server response body."""
    def __init__(self, code, *, status=None, retryable=False):
        self.code, self.status, self.retryable = code, status, retryable
        super().__init__(code + (f" (HTTP {status})" if status else ""))


class HTTPTransport:
    def post(self, url, headers, payload, timeout):
        parts = urlsplit(url)
        connection_type = (http.client.HTTPSConnection if parts.scheme == "https"
                           else http.client.HTTPConnection)
        conn = connection_type(parts.hostname, parts.port, timeout=timeout)
        end = time.monotonic() + timeout
        response = None
        try:
            conn.request("POST", parts.path or "/", body=payload, headers=headers)
            # getresponse() detaches conn.sock for Connection: close responses.
            # Keep the socket reference so the remaining deadline still applies
            # while reading their body, rather than resetting the full timeout.
            response_socket = conn.sock

            def apply_remaining_timeout():
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                if response_socket:
                    response_socket.settimeout(remaining)

            apply_remaining_timeout()
            response = conn.getresponse()
            chunks, size = [], 0
            while not response.isclosed():
                apply_remaining_timeout()
                block = response.read1(65536)
                if not block:
                    break
                size += len(block)
                if size > 1_048_576:
                    raise ModelError("response_too_large")
                chunks.append(block)
            return response.status, dict(response.getheaders()), b"".join(chunks)
        finally:
            if response is not None:
                response.close()
            conn.close()


class LLMClient:
    def __init__(self, settings: Settings, transport=None, sleep=time.sleep):
        self.settings = settings
        self.transport = transport or HTTPTransport()
        self.sleep = sleep

    @staticmethod
    def _decode(raw, *, recovery=False):
        try:
            data = json.loads(raw)
            choice = data["choices"][0]
            if not isinstance(choice, dict):
                raise ValueError()
            finish = choice.get("finish_reason")
            event = {"event": "llm_response", "recovery": recovery,
                     "finish_reason": finish if finish in (
                         "stop", "length", "tool_calls", "content_filter", "function_call") else "other"}
            usage = data.get("usage")
            if isinstance(usage, dict):
                for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    value = usage.get(name)
                    if type(value) is int and 0 <= value <= 1_000_000_000:
                        event[name] = value
                details = usage.get("completion_tokens_details")
                value = details.get("reasoning_tokens") if isinstance(details, dict) else None
                if value is None:
                    value = usage.get("reasoning_tokens")
                if type(value) is int and 0 <= value <= 1_000_000_000:
                    event["reasoning_tokens"] = value
            # Whitelisted metadata only; no text, reasoning, keys or URLs.
            with _DIAGNOSTIC_LOCK:
                print(json.dumps(event), file=sys.stderr, flush=True)
            if finish == "length":
                raise ModelError("truncated_response", retryable=False)
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise ValueError()
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S | re.I).strip()
            if re.search(r"</think>", content, re.I):
                content = re.split(r"</think>", content, flags=re.I)[-1].strip()
            if not content or re.search(r"<think>", content, re.I):
                raise ModelError("empty_response", retryable=True)
            return content
        except (KeyError, IndexError, TypeError, ValueError, UnicodeError):
            raise ModelError("invalid_response", retryable=True) from None

    def _recover_truncation(self, messages, endpoint, headers, deadline):
        """One changed request, within the original token cap and deadline."""
        cfg = self.settings
        remaining = cfg.timeout if deadline is None else deadline - time.monotonic()
        if remaining < min(15.0, cfg.timeout):
            raise ModelError("truncated_response", retryable=False)
        body = json.dumps({"model": cfg.model,
                           "messages": list(messages) + [{"role": "user", "content": _RECOVERY_INSTRUCTION}],
                           "temperature": cfg.temperature, "max_tokens": cfg.max_tokens},
                          ensure_ascii=False).encode("utf-8")
        try:
            status, _, raw = self.transport.post(
                endpoint, headers, body, min(cfg.timeout, remaining))
            if status != 200:
                raise ModelError("api_error", status=status, retryable=False)
            return self._decode(raw, recovery=True)
        except ModelError as exc:
            raise ModelError(exc.code, status=exc.status, retryable=False) from None
        except (OSError, socket.timeout, ssl.SSLError, http.client.HTTPException):
            raise ModelError("transport_error", retryable=False) from None

    def complete(self, messages, *, deadline=None):
        cfg = self.settings
        body = json.dumps({"model": cfg.model, "messages": messages,
                           "temperature": cfg.temperature, "max_tokens": cfg.max_tokens},
                          ensure_ascii=False).encode("utf-8")
        headers = {"Authorization": "Bearer " + cfg.api_key,
                   "Content-Type": "application/json", "Accept": "application/json"}
        endpoint = cfg.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        last = ModelError("unavailable", retryable=True)
        for attempt in range(cfg.attempts):
            remaining = cfg.timeout if deadline is None else deadline - time.monotonic()
            if remaining <= 0:
                raise ModelError("deadline_exceeded")
            retry_after = 0.0
            try:
                status, response_headers, raw = self.transport.post(
                    endpoint, headers, body, min(cfg.timeout, remaining))
                if status != 200:
                    try:
                        retry_after = float(next((v for k, v in response_headers.items()
                                                  if k.lower() == "retry-after"), "0"))
                    except (ValueError, TypeError):
                        retry_after = 0.0
                    if not math.isfinite(retry_after):
                        retry_after = 0.0
                    raise ModelError("api_error", status=status,
                                     retryable=status in (408, 429) or 500 <= status <= 599)
                try:
                    return self._decode(raw)
                except ModelError as exc:
                    if exc.code == "truncated_response":
                        return self._recover_truncation(messages, endpoint, headers, deadline)
                    raise
            except ModelError as exc:
                last = exc
            except (OSError, socket.timeout, ssl.SSLError, http.client.HTTPException):
                last = ModelError("transport_error", retryable=True)
            if not last.retryable or attempt + 1 >= cfg.attempts:
                raise last from None
            pause = max(min(max(retry_after, 0.0), 15.0),
                        min(0.6 * (2 ** attempt) + random.uniform(0, 0.2), 5.0))
            if deadline is not None and time.monotonic() + pause >= deadline:
                raise ModelError("deadline_exceeded")
            self.sleep(pause)
        raise last
