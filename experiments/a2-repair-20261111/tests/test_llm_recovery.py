import contextlib
import io
import json
import unittest
from unittest.mock import patch

from llm_client import LLMClient, ModelError
from settings import Settings


def response(content="Готовый ответ", finish="stop", usage=None):
    data = {"choices": [{"message": {"content": content}, "finish_reason": finish}]}
    if usage is not None:
        data["usage"] = usage
    return 200, {}, json.dumps(data).encode()


class Transport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def post(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers,
                           "body": json.loads(payload), "timeout": timeout})
        value = self.replies.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Settings("http://localhost:1234/v1", "private-key", "test-model",
                            max_tokens=128, timeout=90, attempts=3)
        self.messages = [{"role": "system", "content": "Return the requested format"},
                         {"role": "user", "content": '{"sources":["full source"],"question":"test"}'}]
        self.logs = io.StringIO()
        redirect = contextlib.redirect_stderr(self.logs)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)

    def client(self, replies, cfg=None):
        t = Transport(replies)
        return LLMClient(cfg or self.cfg, t, sleep=lambda _: None), t

    def test_one_changed_recovery_preserves_context_cap_and_format(self):
        client, t = self.client([response("unfinished", "length"), response('{"answer":"готово"}')])
        original = json.loads(json.dumps(self.messages))
        with patch("llm_client.time.monotonic", return_value=100):
            answer = client.complete(self.messages, deadline=150)
        self.assertEqual(answer, '{"answer":"готово"}')
        self.assertEqual(self.messages, original)
        self.assertEqual(len(t.calls), 2)
        self.assertEqual(t.calls[1]["body"]["messages"][:-1], original)
        self.assertNotIn("unfinished", json.dumps(t.calls[1]["body"]))
        self.assertNotEqual(t.calls[0]["body"], t.calls[1]["body"])
        for call in t.calls:
            self.assertEqual(set(call["body"]), {"model", "messages", "temperature", "max_tokens"})
            self.assertEqual(call["body"]["max_tokens"], 128)
            self.assertEqual(call["timeout"], 50)
            self.assertEqual(call["url"], "http://localhost:1234/v1/chat/completions")

    def test_twice_truncated_is_not_accepted_or_retried(self):
        client, t = self.client([response("partial", "length"), response("still partial", "length")])
        with self.assertRaises(ModelError) as raised:
            client.complete(self.messages)
        self.assertEqual(raised.exception.code, "truncated_response")
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(len(t.calls), 2)

    def test_low_remaining_deadline_does_not_start_recovery(self):
        client, t = self.client([response("partial", "length")])
        with patch("llm_client.time.monotonic", return_value=100):
            with self.assertRaises(ModelError) as raised:
                client.complete(self.messages, deadline=105)
        self.assertEqual(raised.exception.code, "truncated_response")
        self.assertEqual(len(t.calls), 1)

    def test_length_with_no_visible_content_can_recover(self):
        client, t = self.client([response(None, "length"), response("Полный ответ")])
        self.assertEqual(client.complete(self.messages), "Полный ответ")
        self.assertEqual(len(t.calls), 2)

    def test_recovery_http_failure_gets_no_further_retry(self):
        client, t = self.client([response("partial", "length"), (503, {}, b"{}")])
        with self.assertRaises(ModelError) as raised:
            client.complete(self.messages)
        self.assertEqual(raised.exception.code, "api_error")
        self.assertEqual(raised.exception.status, 503)
        self.assertEqual(len(t.calls), 2)

    def test_recovery_transport_failure_gets_no_further_retry(self):
        client, t = self.client([response("partial", "length"), TimeoutError()])
        with self.assertRaises(ModelError) as raised:
            client.complete(self.messages)
        self.assertEqual(raised.exception.code, "transport_error")
        self.assertEqual(len(t.calls), 2)

    def test_normal_transport_retries_still_work_before_recovery(self):
        client, t = self.client([(503, {}, b"{}"), response("partial", "length"), response("Полный")])
        self.assertEqual(client.complete(self.messages), "Полный")
        self.assertEqual(len(t.calls), 3)

    def test_unclosed_reasoning_is_never_returned(self):
        cfg = Settings("http://localhost/v1", "key", "model", attempts=1)
        client, t = self.client([response("<think>private thought without closing tag")], cfg)
        with self.assertRaises(ModelError) as raised:
            client.complete(self.messages)
        self.assertEqual(raised.exception.code, "empty_response")
        self.assertEqual(len(t.calls), 1)
        self.assertNotIn("private thought", self.logs.getvalue())

    def test_safe_usage_metadata_has_no_text_or_credentials(self):
        usage = {"prompt_tokens": 14, "completion_tokens": 5, "total_tokens": 19,
                 "completion_tokens_details": {"reasoning_tokens": 3},
                 "secret": "do-not-log"}
        client, _ = self.client([response("<think>private reasoning</think>Ответ", usage=usage)])
        self.assertEqual(client.complete(self.messages), "Ответ")
        event = json.loads(self.logs.getvalue())
        self.assertEqual(event["reasoning_tokens"], 3)
        self.assertEqual(event["finish_reason"], "stop")
        self.assertEqual(event["completion_tokens"], 5)
        for text in ["private-key", "private reasoning", "full source", "do-not-log", "localhost"]:
            self.assertNotIn(text, self.logs.getvalue())

    def test_malformed_choice_is_typed_error(self):
        with self.assertRaises(ModelError) as raised:
            LLMClient._decode(b'{"choices":[null]}')
        self.assertEqual(raised.exception.code, "invalid_response")


if __name__ == "__main__":
    unittest.main()
