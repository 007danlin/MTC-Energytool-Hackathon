"""OpenAI-compatible chat client on the standard library.

Differences from the A2 client:
* a completed HTTP 200 exchange is always returned with its finish_reason, so the
  caller can recover a token-limited or empty generation instead of losing the row;
* optional reasoning hints and sampling settings are sent in several API dialects and
  silently dropped when the service rejects them (HTTP 400/422), remembering what it accepts;
* a rejected max_tokens steps down a ladder (8192 -> 4096 -> platform value) instead of
  falling straight to the platform value;
* rate-limit and server-error answers have their own, more patient retry budget.
Diagnostics never contain the address, the key, prompts or response bodies.
"""
from dataclasses import dataclass
import http.client
import json
import math
import random
import re
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit


class ModelError(RuntimeError):
    def __init__(self, code, *, status=None, retryable=False, context_overflow=False, window=None, limit=0):
        self.code, self.status, self.retryable = code, status, retryable
        self.context_overflow = context_overflow
        self.window = window    # (window tokens, prompt tokens) read from a context refusal, if the service states them
        self.limit = limit      # completion budget of the refused request
        super().__init__(code + (f" (HTTP {status})" if status else ""))


@dataclass
class Completion:
    content: str
    finish_reason: str
    reasoning_chars: int
    completion_tokens: int
    prompt_tokens: int
    elapsed: float

    @property
    def truncated(self):
        return self.finish_reason == "length"

    @property
    def usable(self):
        return bool(self.content) and not self.truncated


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
                if size > 4_194_304:
                    raise ModelError("response_too_large")
                chunks.append(block)
            return response.status, dict(response.getheaders()), b"".join(chunks)
        finally:
            if response is not None:
                response.close()
            conn.close()


# Reasoning hints, most complete dialect first. An empty dict means "send nothing".
def _hint_variants(level):
    if level in ("low", "medium"):
        return ({"reasoning_effort": level, "reasoning": {"effort": level},
                 "chat_template_kwargs": {"reasoning_effort": level}},
                {"reasoning_effort": level, "chat_template_kwargs": {"reasoning_effort": level}},
                {"reasoning_effort": level},
                {"reasoning": {"effort": level}},
                {})
    if level == "off":
        return ({"chat_template_kwargs": {"enable_thinking": False}, "enable_thinking": False,
                 "reasoning": {"enabled": False}},
                {"chat_template_kwargs": {"enable_thinking": False}, "enable_thinking": False},
                {"chat_template_kwargs": {"enable_thinking": False}},
                {"enable_thinking": False},
                {"reasoning": {"enabled": False}},
                {})
    return ({},)


OVERFLOW = re.compile(rb"context|prompt is too long|too many tokens|maximum.{0,40}length|max_model_len|"
                      rb"input.{0,20}(?:tokens|length)|reduce the length", re.I)
LIMIT = re.compile(rb"max_tokens|max_completion_tokens|max_new_tokens|completion tokens", re.I)
WINDOW = re.compile(rb"(?:context length|context window|context size|max_model_len|maximum input)\D{0,40}?(\d{4,7})", re.I)


def _window(text, limit, *, explicit_only=False):
    """(window tokens, prompt tokens) from a context refusal that states both numbers, else None."""
    found = WINDOW.search(text)
    if not found:
        return None
    window = int(found.group(1))
    stated = re.search(rb"(\d{3,7})\s+(?:in the messages|input tokens)", text, re.I)
    if stated:
        prompt = int(stated.group(1))
    else:
        if explicit_only:
            return None
        larger = [int(n) for n in re.findall(rb"\d{4,7}", text) if int(n) > window]
        if not larger:
            return None
        prompt = max(larger)
        if re.search(rb"completion|max_tokens|output", text, re.I):
            prompt -= limit
    return (window, prompt) if window >= 2000 and prompt >= 1000 else None


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # some services return typed content parts
        return "".join(p.get("text", "") for p in content if isinstance(p, dict) and isinstance(p.get("text"), str))
    return ""


class LLMClient:
    def __init__(self, settings, transport=None, sleep=time.sleep):
        self.settings = settings
        self.transport = transport or HTTPTransport()
        self.sleep = sleep
        self._lock = threading.Lock()
        self._variant = {}            # reasoning level -> index of the accepted hint variant
        self._max_tokens_cap = None   # learned ceiling for max_tokens, if the service rejects larger values
        self._sampling_ok = True      # False after the service refused the optional sampling fields
        self.calls = 0
        self.rate_limited = 0         # HTTP 429 answers seen in this run (read by the pace controller)

    # ---- learned service limits -------------------------------------------
    def _variant_index(self, level):
        with self._lock:
            return self._variant.get(level, 0)

    def _reject_variant(self, level, index):
        with self._lock:
            if self._variant.get(level, 0) == index:
                self._variant[level] = index + 1

    def _cap(self, value):
        with self._lock:
            return value if self._max_tokens_cap is None else min(value, self._max_tokens_cap)

    def _lower_cap(self, rejected):
        """The service refused `rejected` completion tokens: remember the next smaller step, if any."""
        cfg = self.settings
        lower = [step for step in (8192, 4096, cfg.max_tokens) if step < rejected]
        if not lower:
            return False
        with self._lock:
            if self._max_tokens_cap is None or max(lower) < self._max_tokens_cap:
                self._max_tokens_cap = max(lower)
        return True

    def _sampling(self, reasoning):
        """Optional sampling fields for a thinking generation (empty unless configured in this build)."""
        cfg = self.settings
        with self._lock:
            allowed = self._sampling_ok
        if reasoning == "off" or cfg.think_temperature < 0:
            return {}
        fields = {"temperature": cfg.think_temperature}
        if allowed and 0 < cfg.think_top_p <= 1:
            fields["top_p"] = cfg.think_top_p
        return fields

    # ---- request -------------------------------------------------------------
    def chat(self, messages, *, deadline=None, max_tokens=None, reasoning="default", attempts=None, timeout=None):
        cfg = self.settings
        attempts = cfg.attempts if attempts is None else max(1, min(attempts, cfg.attempts))
        timeout = cfg.timeout if timeout is None else min(timeout, cfg.timeout)
        requested = cfg.max_tokens if max_tokens is None else max_tokens
        variants = _hint_variants(reasoning)
        headers = {"Authorization": "Bearer " + cfg.api_key,
                   "Content-Type": "application/json", "Accept": "application/json"}
        endpoint = cfg.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        last = ModelError("unavailable", retryable=True)
        attempt = 0            # transport failures and unusable answers
        status_attempt = 0     # rate-limit and server-error answers: a separate, more patient budget
        status_attempts = max(attempts, cfg.attempts + 2)
        degradations = 0
        local_limit = None     # a one-call reduction when a larger budget does not fit the context window
        while attempt < attempts and status_attempt < status_attempts:
            remaining = timeout if deadline is None else deadline - time.monotonic()
            if remaining <= 0:
                raise ModelError("deadline_exceeded")
            index = min(self._variant_index(reasoning), len(variants) - 1)
            limit = self._cap(requested if local_limit is None else min(requested, local_limit))
            payload = {"model": cfg.model, "messages": messages,
                       "temperature": cfg.temperature, "max_tokens": limit}
            sampling = self._sampling(reasoning)
            payload.update(sampling)
            payload.update(variants[index])
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            retry_after = 0.0
            started = time.monotonic()
            status_failure = False
            try:
                with self._lock:
                    self.calls += 1
                status, response_headers, raw = self.transport.post(
                    endpoint, headers, body, min(timeout, remaining))
                if status == 200:
                    return self._parse(raw, time.monotonic() - started)
                if status in (400, 404, 413, 422) and degradations < 12:
                    # The service refused the request shape. Undo our optional additions one at a
                    # time, the likeliest cause first; this does not consume a transport attempt.
                    degradations += 1
                    text = raw[:4000]
                    about_context = status == 413 or bool(OVERFLOW.search(text))
                    about_limit = bool(LIMIT.search(text))
                    stated = _window(text, limit, explicit_only=True) if about_context else None
                    stated_overflow = stated is not None and stated[1] + limit > stated[0]
                    if about_limit and stated_overflow:
                        # Keep N2's output-budget ladder for this request, but a
                        # prompt-dependent refusal does not establish a global cap.
                        lower = [step for step in (8192, 4096, cfg.max_tokens) if step < limit]
                        if lower:
                            local_limit = max(lower)
                            continue
                    overflow = about_context and (not about_limit or stated_overflow)
                    extras = bool(variants[index]) or "top_p" in sampling
                    if overflow and status != 413 and limit > cfg.main_max_tokens:
                        # The prompt plus a budget above the ordinary one does not fit: reduce it for this call only.
                        local_limit = cfg.main_max_tokens
                        continue
                    if status == 413 or (overflow and (not extras or stated_overflow)):
                        # The prompt itself does not fit: the caller sizes the context to the window.
                        raise ModelError("bad_request", status=status, context_overflow=True,
                                         window=_window(text, limit), limit=limit)
                    if about_limit and self._lower_cap(limit):
                        continue
                    if "top_p" in sampling:
                        with self._lock:
                            self._sampling_ok = False
                        continue
                    if variants[index]:
                        self._reject_variant(reasoning, index)
                        continue
                    if limit > cfg.max_tokens and self._lower_cap(limit):
                        continue
                    raise ModelError("bad_request", status=status, context_overflow=about_context,
                                     window=_window(text, limit) if about_context else None, limit=limit)
                try:
                    retry_after = float(next((v for k, v in response_headers.items()
                                              if k.lower() == "retry-after"), "0"))
                except (ValueError, TypeError):
                    retry_after = 0.0
                if not math.isfinite(retry_after):
                    retry_after = 0.0
                status_failure = status in (408, 409, 425, 429) or 500 <= status <= 599
                if status == 429:
                    with self._lock:
                        self.rate_limited += 1
                raise ModelError("api_error", status=status, retryable=status_failure)
            except ModelError as exc:
                last = exc
            except (socket.timeout, TimeoutError):
                # Repeating a request that already took a long limit would usually take as long:
                # the caller continues with a shorter request instead.
                last = ModelError("timeout", retryable=min(timeout, remaining) < 45)
            except (OSError, ssl.SSLError, http.client.HTTPException):
                last = ModelError("transport_error", retryable=True)
            if status_failure:
                status_attempt += 1
                step, exhausted = status_attempt, status_attempt >= status_attempts
            else:
                attempt += 1
                step, exhausted = attempt, attempt >= attempts
            if not last.retryable or exhausted:
                raise last from None
            pause = max(min(max(retry_after, 0.0), 15.0),
                        min(0.6 * (2 ** (step - 1)) + random.uniform(0, 0.2), 5.0))
            if deadline is not None and time.monotonic() + pause >= deadline:
                raise ModelError("deadline_exceeded")
            self.sleep(pause)
        raise last

    @staticmethod
    def _parse(raw, elapsed):
        try:
            data = json.loads(raw)
            choice = data["choices"][0]
            message = choice.get("message") or {}
            content = _text(message.get("content"))
            reasoning = _text(message.get("reasoning_content")) or _text(message.get("reasoning"))
            finish = choice.get("finish_reason") or ""
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        except (KeyError, IndexError, TypeError, ValueError, UnicodeError, AttributeError):
            raise ModelError("invalid_response", retryable=True) from None
        # Some deployments leave visible thinking inside content.
        inline = re.findall(r"<think>(.*?)</think>", content, flags=re.S | re.I)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.S | re.I).strip()
        if re.search(r"</think>", content, re.I):
            head, _, content = content.rpartition("</think>")
            inline.append(head)
            content = content.strip()
        if re.search(r"<think>", content, re.I):
            # Thinking was opened and never closed: there is no final answer.
            inline.append(content)
            content = ""

        def count(key):
            value = usage.get(key)
            return value if isinstance(value, int) else 0

        return Completion(content, str(finish), len(reasoning) + sum(len(x) for x in inline),
                          count("completion_tokens"), count("prompt_tokens"), elapsed)
