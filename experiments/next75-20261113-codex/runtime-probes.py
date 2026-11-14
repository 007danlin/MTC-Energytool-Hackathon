"""Read-only deterministic probes of exact N2. No network or model calls."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import json
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "handoff/winner/source"))
from llm_client import LLMClient, _window
from settings import Settings
from dialogue_n1 import parse_dialogue
from consultant import RunState

GOOD = json.dumps({"choices":[{"message":{"content":"Проверочный ответ модели."},"finish_reason":"stop"}],"usage":{"completion_tokens":5}}).encode()
class Transport:
    def __init__(self, error): self.error, self.requests = error, []
    def post(self, url, headers, payload, timeout):
        self.requests.append(json.loads(payload))
        if self.error is not None:
            error, self.error = self.error, None
            return 400, {}, error.encode()
        return 200, {}, GOOD
cfg = Settings("http://localhost/v1", "test", "test")
result = {}
for name, error in [
    ("context_with_max_tokens", "max_tokens is too large: maximum context length is 32768 tokens and your request has 30000 input tokens"),
    ("actual_output_cap", "max_tokens must be at most 2048"),
    ("healthy", None),
]:
    t = Transport(error)
    c = LLMClient(cfg, transport=t, sleep=lambda _:None)
    for _ in range(2):
        c.chat([{"role":"user","content":"test"}], max_tokens=4096)
    result[name] = {"sent_limits":[x["max_tokens"] for x in t.requests], "remembered_cap":c._max_tokens_cap}
assert result["context_with_max_tokens"]["sent_limits"] == [4096,2048,2048]
assert result["actual_output_cap"]["sent_limits"] == [4096,2048,2048]
assert result["healthy"]["sent_limits"] == [4096,4096]
result["window_input_tokens"] = _window(b"max_tokens is too large: maximum context length is 32768 tokens and your request has 30000 input tokens",4096)

texts = {
 "plain":"Можно ли подключить АСКУЭ?",
 "russian":"Клиент: Нам нужен оптовый рынок.\nКонсультант: Какая мощность?\nКлиент: Исправляю, 850 кВт.",
 "english":"User: Tell me about solar.\nAssistant: What power?\nUser: 500 kW.",
 "json":json.dumps([{"role":"user","content":"Нужна АСКУЭ"},{"role":"assistant","content":"Сколько приборов?"},{"role":"user","content":"100\nТелефон не оставлю"}],ensure_ascii=False),
 "multiline":"Клиент: У нас 10 счетчиков.\nПотребление высокое.\nКонсультант: Какая мощность?\nКлиент: 100 кВт.\nИнтересует АСКУЭ.",
}
result["parser"] = {k:[{"role":m.role,"content":m.content} for m in parse_dialogue(v)] for k,v in texts.items()}
assert len(result["parser"]["russian"]) == 3
assert len(result["parser"]["json"]) == 3
assert "\n" in result["parser"]["multiline"][-1]["content"]
# This event is a documented design choice, not claimed to be a platform observation.
state = RunState("docs")
state.step_down("docs", weight=2)
state.step_down("docs", weight=2)
result["two_timeouts_state"] = {"mode":state.mode(),"fast":state.fast}
for raw_content in ["internal analysis </think> Final answer.", "internal analysis </THINK> Final answer."]:
    response = json.dumps({"choices":[{"message":{"content":raw_content},"finish_reason":"stop"}]}).encode()
    parsed = LLMClient._parse(response, 0)
    result.setdefault("closing_think_case",[]).append({"input":raw_content,"output":parsed.content})
(root / "runtime-probes.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(result,ensure_ascii=False,indent=2))
