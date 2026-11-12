"""30 reproducible scenarios. Offline is infrastructure only; live needs real API.

Full prompts, reference answers and source excerpts stay in reports/private/.
Semantic quality is reviewed using the rubric; never equate a mock/substring check
with passing consultation quality or the organizer's LLM judge.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from consultant import Consultant, normalized
from contracts import ConsultationRequest, Message
from dialogue import parse_question, retrieval_query
from llm_client import LLMClient, ModelError
from retrieval import LexicalRetriever
from scenarios import CUSTOM_SCENARIOS, DEMO_RUBRICS
from settings import Settings
from solution import read_questions


class OfflineClient:
    """Protocol fixture, deliberately does not answer product questions."""
    def complete(self, messages, deadline=None):
        data = json.loads(messages[1]["content"])
        if "lead_so_far" not in data:
            return "[MOCK] Проверка CSV-протокола выполнена. Качество ответа не проверено."
        contacts, intent = [], {}
        for i, message in enumerate(data["messages"]):
            if message["role"] != "user":
                continue
            text = message["content"]
            for field, pattern in (("full_name", r"ФИО:\s*([^.!?\n]+)"),
                                   ("company", r"Компания:\s*([^.!?\n]+)"),
                                   ("phone", r"(?:Телефон|телефон):\s*(\+?[\d ()-]{10,})")):
                match = re.search(pattern, text)
                if match:
                    contacts.append({"field": field, "value": match[1].strip(), "quote": match[0], "message_index": i})
            if "Подготовьте заявку" in text:
                intent = {"requested": True, "declined": False, "quote": "Подготовьте заявку", "message_index": i}
            if "Телефон оставлять не хочу" in text:
                intent = {"requested": False, "declined": True, "quote": "Телефон оставлять не хочу", "message_index": i}
        return json.dumps({"answer": "[MOCK] Проверка протокола выполнена. Содержательный ответ модели не получен.",
                           "status": "clarification", "citations": [], "contacts": contacts,
                           "intent": intent, "summary": {}}, ensure_ascii=False)


class FailureClient:
    def complete(self, messages, deadline=None):
        raise ModelError("transport_error", retryable=True)


class EmptyTransport:
    def __init__(self):
        self.calls = 0

    def post(self, url, headers, payload, timeout):
        self.calls += 1
        return 200, {}, b'{"choices":[{"message":{"content":""}}]}'


def evaluate(data_dir, mode, output):
    cfg = Settings.from_env() if mode == "live" else Settings("http://localhost/v1", "mock", "MOCK")
    client = LLMClient(cfg) if mode == "live" else OfflineClient()
    retrieval = LexicalRetriever.from_zip(data_dir / "knowledge-base.zip")
    service = Consultant(client, retrieval, cfg)
    rows = read_questions(data_dir / "questions.csv")
    if len(rows) != 18 or {qid for qid, _ in rows} != set(DEMO_RUBRICS):
        raise ValueError("Evaluation requires the provided 18 demo questions with IDs 1..18")
    cases = [{"id": qid, "name": "Демонстрационный сценарий " + qid,
              "messages": parse_question(question), "expected": DEMO_RUBRICS[qid][0],
              "evidence_groups": DEMO_RUBRICS[qid][1]} for qid, question in rows] + CUSTOM_SCENARIOS
    records = []
    for case in cases:
        messages, lead, outputs = [], None, []
        if case.get("new_session"):
            service.respond(ConsultationRequest("discarded-session", [Message("user", "Компания ООО Старая сессия, телефон +79990000009.")]))
        steps = [case["messages"]] if "messages" in case else case["turns"]
        local_service = Consultant(FailureClient(), retrieval, cfg) if case.get("failure") else service
        for step in steps:
            if isinstance(step, list):
                messages = list(step)
            else:
                messages.append(Message("user", step))
            result = local_service.respond(ConsultationRequest("eval-" + case["id"], messages[:], lead),
                                           deadline=time.monotonic() + 180,
                                           answer_only=case["id"] in DEMO_RUBRICS)
            outputs.append(result.to_dict())
            lead = result.lead
            messages.append(Message("assistant", result.answer))
        retrieved_ids = set(outputs[-1]["debug"]["retrieved_sources"])
        context = normalized("\n".join(f.text for f in retrieval.fragments if f.source_id in retrieved_ids))
        groups = case.get("evidence_groups", [])
        coverage = all(any(normalized(term) in context for term in group) for group in groups) if groups else None
        assertions = {"nonempty_answer": all(0 < len(o["answer"]) <= 10000 for o in outputs),
                      "never_sent": all(o["summary"]["sent"] is False for o in outputs)}
        if not case.get("failure"):
            assertions["model_response_succeeded"] = all(o["status"] != "technical_error" for o in outputs)
        if case.get("new_session"):
            assertions["new_session_empty_contacts"] = not outputs[-1]["lead"]["fields"]
        if case["id"] == "27":
            assertions["no_phone_without_user_input"] = not outputs[-1]["lead"]["fields"].get("phone")
        if case["id"] == "28":
            assertions["readiness_sequence"] = [o["lead_ready"] for o in outputs] == [False, False, True]
        if case["id"] == "29":
            assertions["corrected_phone"] = outputs[-1]["lead"]["fields"].get("phone") == "+79990000002"
        if case.get("failure"):
            assertions["technical_status"] = outputs[-1]["status"] == "technical_error"
            empty = EmptyTransport()
            empty_result = Consultant(LLMClient(cfg, empty, lambda _: None), retrieval, cfg).respond(
                ConsultationRequest("empty-response", [Message("user", "Тест пустого ответа")]))
            assertions["empty_response_bounded"] = empty.calls == cfg.attempts and empty_result.status == "technical_error"
            outputs.append(empty_result.to_dict())
        records.append({"id": case["id"], "name": case["name"], "expected": case["expected"],
                        "input": [m.__dict__ for m in messages if m.role == "user"],
                        "mode": mode, "outputs": outputs, "retrieval_coverage": coverage,
                        "checks": assertions, "protocol_result": "pass" if all(assertions.values()) else "fail",
                        "quality_result": "not_evaluated_mock" if mode == "offline" else "requires_human_review"})
    output.mkdir(parents=True, exist_ok=True)
    summary = {"created_utc": datetime.now(timezone.utc).isoformat(), "mode": mode,
               "model": cfg.model, "scenario_count": len(records),
               "protocol_pass": sum(r["protocol_result"] == "pass" for r in records),
               "retrieval_coverage_pass": sum(r["retrieval_coverage"] is True for r in records[:18]),
               "retrieval_coverage_total": 18,
               "semantic_quality_verified": False, "platform_score": None,
               "notes": "Coverage checks presence of annotated evidence, not answer quality or ranking optimality."}
    (output / (mode + "-results.json")).write_text(json.dumps({"summary": summary, "scenarios": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Проверка 30 сценариев", "", f"Режим: **{mode}**. Качество консультаций не подтверждено этим отчётом.", "",
             "| ID | Сценарий | Протокол | Наличие ожидаемых сведений | Качество |",
             "|---|---|---|---|---|"]
    for record in records:
        lines.append(f"| {record['id']} | {record['name']} | {record['protocol_result']} | {record['retrieval_coverage']} | {record['quality_result']} |")
    for record in records:
        lines.extend(["", "## " + record["id"] + " " + record["name"], "", record["expected"], ""])
        for turn in record["outputs"]:
            lines.extend([f"Ответ ({turn['elapsed_ms']} мс): {turn['answer']}", "",
                          "Использованные источники: " + json.dumps(turn["sources"], ensure_ascii=False), "",
                          "Найденные фрагменты: " + ", ".join(turn["debug"]["retrieved_sources"]), ""])
    (output / (mode + "-results.md")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offline", "live"), required=True)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/private")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.data_dir, args.mode, args.output), ensure_ascii=False, indent=2))
