#!/usr/bin/env python3
"""Deterministic OpenAI-compatible test double for technical acceptance (not a language model).

It records every request and can imitate rate limits, server errors, slow answers,
strict parameter validation, a max_tokens ceiling, a context limit and token-limited
"thinking" responses. Answers are a pure function of the request body.
"""
import argparse, hashlib, json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STANDARD = {"model", "messages", "temperature", "max_tokens", "top_p"}
OFF_HINTS = ("chat_template_kwargs", "enable_thinking", "reasoning")


class State:
    def __init__(self, args):
        self.args, self.lock, self.count, self.log = args, threading.Lock(), 0, []
        self.fail_left = args.fail_first
        os.makedirs(args.record, exist_ok=True)


def thinking_off(body):
    if body.get("enable_thinking") is False:
        return True
    if isinstance(body.get("chat_template_kwargs"), dict) and body["chat_template_kwargs"].get("enable_thinking") is False:
        return True
    return isinstance(body.get("reasoning"), dict) and body["reasoning"].get("enabled") is False


def effort(body):
    """Reasoning effort requested in any of the supported dialects, or ''."""
    for value in (body.get("reasoning_effort"),
                  (body.get("chat_template_kwargs") or {}).get("reasoning_effort") if isinstance(body.get("chat_template_kwargs"), dict) else None,
                  (body.get("reasoning") or {}).get("effort") if isinstance(body.get("reasoning"), dict) else None):
        if isinstance(value, str) and value:
            return value
    return ""


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, status, obj, headers=None):
            raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            if state.args.close:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path.rstrip("/").endswith("/models"):
                return self._send(200, {"data": [{"id": "mock"}]})
            if self.path.endswith("/__stats"):
                with state.lock:
                    return self._send(200, {"count": state.count, "log": state.log})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            a = state.args
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            digest = hashlib.sha256(raw).hexdigest()
            auth = self.headers.get("Authorization", "")
            with state.lock:
                state.count += 1
                number = state.count
                fail = state.fail_left > 0
                if fail:
                    state.fail_left -= 1
            entry = {"n": number, "path": self.path, "sha256": digest, "bytes": len(raw),
                     "auth_ok": auth == "Bearer " + a.key}
            def done(status, kind):
                entry.update(status=status, kind=kind)
                with state.lock:
                    state.log.append(entry)
            if not self.path.endswith("/chat/completions"):
                done(404, "path"); return self._send(404, {"error": "unknown path"})
            if auth != "Bearer " + a.key:
                done(401, "auth"); return self._send(401, {"error": "token_not_found_in_db"})
            try:
                body = json.loads(raw)
            except ValueError:
                done(400, "json"); return self._send(400, {"error": "invalid json"})
            with open(os.path.join(a.record, f"{number:05d}-{digest[:16]}.json"), "wb") as f:
                f.write(raw)
            entry.update(model=body.get("model"), max_tokens=body.get("max_tokens"), temperature=body.get("temperature"),
                         top_p=body.get("top_p"), effort=effort(body), thinking_off=thinking_off(body),
                         extra=sorted(set(body) - STANDARD), prompt_chars=sum(len(m.get("content", "")) for m in body.get("messages", [])))
            if fail:
                status = a.fail_status
                done(status, "injected")
                return self._send(status, {"error": "injected"}, {"Retry-After": "0"} if status == 429 else None)
            if a.strict and set(body) - STANDARD:
                done(400, "strict"); return self._send(400, {"error": {"message": "Unrecognized request argument"}})
            if a.reject_reasoning_object and "reasoning" in body:
                done(422, "reasoning"); return self._send(422, {"error": {"message": "extra fields not permitted"}})
            if a.max_tokens_cap and body.get("max_tokens", 0) > a.max_tokens_cap:
                done(400, "cap"); return self._send(400, {"error": {"message": "max_tokens is too large: %d. This model supports at most %d completion tokens." % (body.get("max_tokens", 0), a.max_tokens_cap)}})
            if a.context_limit and entry["prompt_chars"] > a.context_limit:
                done(400, "context")
                if a.context_detail:   # the wording of a common inference server, with both numbers
                    used, extra = entry["prompt_chars"] // 3, body.get("max_tokens", 0)
                    return self._send(400, {"error": {"message": "This model's maximum context length is %d tokens. However, you requested %d tokens (%d in the messages, %d in the completion). Please reduce the length of the messages or completion." % (a.context_limit // 3, used + extra, used, extra)}})
                return self._send(400, {"error": {"message": "This model's maximum context length is %d tokens. However, you requested more tokens (in the messages and in the completion). Please reduce the length of the messages or completion." % (a.context_limit // 3)}})
            if a.delay:
                time.sleep(a.delay)
            if a.slow_over and entry["prompt_chars"] > a.slow_over:
                time.sleep(a.slow_delay)
            off = thinking_off(body)
            seed = int(digest[:8], 16)
            truncated = False
            if a.truncate == "always":
                truncated = True
            elif a.truncate == "thinking":       # only when thinking is not switched off
                truncated = not off
            elif a.truncate == "some":           # deterministic ~30% of plain requests
                truncated = (not off) and seed % 10 < 3
            elif a.truncate == "big":            # thinking exhausts the budget unless max_tokens is large or thinking off
                truncated = (not off) and body.get("max_tokens", 0) < 4096
            elif a.truncate == "deep":           # long reasoning: fits into 8192 tokens or is shortened by a lower effort
                truncated = (not off) and effort(body) not in ("low", "medium") and body.get("max_tokens", 0) < 8192
            elif a.truncate == "loop":           # a repetition loop of the exact prompt: any budget, cured by another prompt
                last = body.get("messages", [{}])[-1].get("content", "")
                truncated = (not off) and "без долгих рассуждений" not in last
            elif a.truncate == "tail":           # deterministic ~12% of ordinary requests need more than 4096 tokens
                truncated = (not off) and effort(body) not in ("low", "medium") and seed % 25 < 3 and body.get("max_tokens", 0) < 8192
            if truncated:
                done(200, "truncated")
                return self._send(200, {"choices": [{"index": 0, "finish_reason": "length",
                                                    "message": {"role": "assistant", "content": "" if a.empty_on_length else "Оборванный текст без",
                                                                "reasoning_content": "думаю " * 400}}],
                                        "usage": {"prompt_tokens": entry["prompt_chars"] // 3, "completion_tokens": body.get("max_tokens", 0)}})
            if a.empty and seed % 10 < 3 and not off:
                done(200, "empty")
                return self._send(200, {"choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": ""}}]})
            text = (a.prefix or "") + f"Ответ-{digest[:12]}: да, это возможно; \"кавычки\", запятая, перенос\nвторая строка — юникод ₽ кВт·ч."
            if a.think_inline:
                text = "<think>скрытые рассуждения</think>\n\n" + text
            done(200, "ok")
            self._send(200, {"id": "x", "object": "chat.completion",
                             "choices": [{"index": 0, "finish_reason": "stop",
                                          "message": {"role": "assistant", "content": text,
                                                      "reasoning_content": "" if off else "краткое рассуждение"}}],
                             "usage": {"prompt_tokens": entry["prompt_chars"] // 3, "completion_tokens": 60}})
    return Handler


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--key", default="mock-key")
    p.add_argument("--record", required=True)
    p.add_argument("--fail-first", type=int, default=0)
    p.add_argument("--fail-status", type=int, default=429)
    p.add_argument("--strict", action="store_true", help="HTTP 400 for any non-standard request field")
    p.add_argument("--reject-reasoning-object", action="store_true")
    p.add_argument("--max-tokens-cap", type=int, default=0)
    p.add_argument("--context-limit", type=int, default=0, help="prompt characters")
    p.add_argument("--context-detail", action="store_true", help="state window and request tokens in the refusal")
    p.add_argument("--delay", type=float, default=0.0)
    p.add_argument("--slow-over", type=int, default=0, help="prompt characters above which the answer is slow")
    p.add_argument("--slow-delay", type=float, default=0.0)
    p.add_argument("--truncate", choices=["never", "always", "thinking", "some", "big", "deep", "loop", "tail"], default="never")
    p.add_argument("--empty-on-length", action="store_true")
    p.add_argument("--empty", action="store_true")
    p.add_argument("--think-inline", action="store_true")
    p.add_argument("--prefix", default="")
    p.add_argument("--close", action="store_true")
    p.add_argument("--port-file")
    args = p.parse_args()
    state = State(args)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
    server.daemon_threads = True
    if args.port_file:
        with open(args.port_file, "w") as f:
            f.write(str(server.server_address[1]))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
