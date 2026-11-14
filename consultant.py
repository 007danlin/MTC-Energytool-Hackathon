"""Stateless consultation service used by both CSV runner and backend integration."""
from dataclasses import asdict
import json
import re
import time

from contracts import ConsultationRequest, ConsultationResult, LeadState
from dialogue import retrieval_query
from llm_client import ModelError
from prompts import ANSWER_PROMPT, SYSTEM_PROMPT
from consultation_state import build_facts, answered_topics, extract_actions, asks_for_plan, without_answered_questions

TECHNICAL_ANSWER = ("Сейчас не удалось получить ответ модели из-за технического сбоя. "
                    "Это не означает, что информации нет в базе знаний. "
                    "Попробуйте повторить вопрос позже; заявку пока не отправляли.")
FIELDS = ("full_name", "phone", "email", "company")
CONTACT_FIELDS = ("phone", "email")
FIELD_LABELS = {"full_name": "ФИО", "phone": "телефон", "company": "название компании", "contact": "телефон или email"}


def sanitize_delivery(answer):
    sent_claim = re.search(r"(?:заявк\w*\s+(?:успешно\s+)?(?:отправлен|передан)|"
                           r"(?:отправил|передал)\w*\s+(?:ваш\w*\s+)?заявк)", answer, re.I)
    if sent_claim:
        answer = re.sub(r"[^.!?\n]*" + re.escape(sent_claim.group(0)) + r"[^.!?\n]*[.!?]?",
                        "Заявку можно подготовить; отправки менеджеру пока нет.", answer, flags=re.I)
    return answer.strip()


def normalized(text):
    return " ".join(text.casefold().replace("ё", "е").split())


def repeats_previous_answer(answer, messages):
    """Reject stalled substantial replies, while allowing an explicit repeat request.

    This checks progression, not semantic correctness: short acknowledgements and
    newly worded answers still need the normal model/source checks.
    """
    if len(messages) < 3:
        return False
    latest = normalized(messages[-1].content)
    if re.search(r"\b(?:повтори(?:те|ть)?|напомни(?:те|ть)?|повтор\w*\s+(?:ответ|объяснен)|"
                 r"(?:скажи(?:те)?|объясни(?:те)?)\s+(?:это\s+)?(?:еще|ещё)\s+раз)\b", latest):
        return False
    assistant_index = next((i for i in range(len(messages) - 2, -1, -1)
                            if messages[i].role == "assistant"), None)
    if assistant_index is None:
        return False
    earlier_user = next((m.content for m in reversed(messages[:assistant_index])
                         if m.role == "user"), "")
    if latest == normalized(earlier_user):
        return False  # A deliberate resubmission of the same question may have the same answer.
    words = lambda text: re.findall(r"\w+", normalized(text))
    previous_words = words(messages[assistant_index].content)
    previous = messages[assistant_index].content
    substantial = len(previous_words) >= 12 or ("?" in previous and len(previous_words) >= 4)
    return substantial and words(answer) == previous_words


def phone_digits(value):
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits


def user_evidence(item, messages):
    index, quote = item.get("message_index"), item.get("quote")
    if type(index) is not int or not 0 <= index < len(messages):
        return False
    message = messages[index]
    return (message.role == "user" and isinstance(quote, str) and len(quote.strip()) >= 2
            and normalized(quote) in normalized(message.content))


def valid_email(value):
    """One bounded ASCII mailbox; syntax only, no claim of deliverability."""
    if not isinstance(value, str) or len(value) > 254 or value.count("@") != 1:
        return False
    local, host = value.split("@")
    if (not 1 <= len(local) <= 64 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
            or local.startswith(".") or local.endswith(".") or ".." in local):
        return False
    labels = host.split(".")
    return len(labels) >= 2 and all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels)


def contact_value(field, value, quote, message_text=None):
    if not isinstance(value, str) or not value.strip() or len(value) > (254 if field == "email" else 200):
        return None
    value = value.strip()
    if field == "phone":
        digits = phone_digits(value)
        candidates = re.findall(r"\+?\d[\d ()\-]{8,}\d", quote)
        if 10 <= len(digits) <= 15 and any(phone_digits(c) == digits for c in candidates):
            return "+" + digits if len(digits) > 10 else digits
        return None
    if field == "email":
        # Exact whole mailbox evidence prevents a substring of another address
        # from being accepted; retain the spelling supplied by the user.
        if not valid_email(value):
            return None
        pattern = r"(?<![\w.!#$%&'*+/=?^_`{|}~@-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+(?![\w.@-])"
        quoted = [c.rstrip(".") for c in re.findall(pattern, quote)
                  if c.rstrip(".").casefold() == value.casefold()]
        if not quoted:
            return None
        # A model quote may be a substring of a larger mailbox. Recheck the
        # original user message, then keep its spelling rather than model case.
        candidates = [c.rstrip(".") for c in re.findall(pattern, message_text if message_text is not None else quote)
                      if c.rstrip(".").casefold() == value.casefold()]
        return next((c for c in candidates if c in quoted), candidates[0] if candidates else None)
    if normalized(value) not in normalized(quote):
        return None
    return value


def seed_lead(request):
    lead = LeadState(request.session_id)
    old = request.lead
    if old:
        for field in FIELDS:
            evidence = old.evidence.get(field, {})
            if user_evidence(evidence, request.messages):
                value = contact_value(field, old.fields.get(field), evidence["quote"],
                                      request.messages[evidence["message_index"]].content)
                if value:
                    lead.fields[field] = value
                    lead.evidence[field] = dict(evidence)
                elif field not in old.fields and re.search(r"удал|забуд|не\s+использ|отзыва", evidence["quote"], re.I):
                    # Keep withdrawal evidence across turns so an older model extraction
                    # cannot resurrect a contact that the customer already removed.
                    lead.evidence[field] = dict(evidence)
        intent = old.evidence.get("intent", {})
        if user_evidence(intent, request.messages):
            lead.requested, lead.declined = old.requested, old.declined
            lead.evidence["intent"] = dict(intent)
    return lead


def extract_lead(payload, request):
    lead = seed_lead(request)
    for item in sorted(payload.get("contacts", []), key=lambda x: x.get("message_index", -1)
                       if type(x.get("message_index")) is int else -1):
        field = item.get("field")
        if field not in FIELDS or not user_evidence(item, request.messages):
            continue
        old_index = lead.evidence.get(field, {}).get("message_index", -1)
        if item["message_index"] < old_index:
            continue
        evidence = {"quote": item["quote"], "message_index": item["message_index"]}
        if item.get("value") is None:
            # Null is accepted only with an explicit withdrawal instruction.
            if re.search(r"удал|забуд|не\s+использ|отзыва", item["quote"], re.I):
                lead.fields.pop(field, None)
                lead.evidence[field] = evidence
            continue
        value = contact_value(field, item.get("value"), item["quote"],
                              request.messages[item["message_index"]].content)
        if value:
            lead.fields[field], lead.evidence[field] = value, evidence
    intent = payload.get("intent", {})
    if (user_evidence(intent, request.messages)
            and intent["message_index"] >= lead.evidence.get("intent", {}).get("message_index", -1)):
        if type(intent.get("requested")) is bool and type(intent.get("declined")) is bool:
            lead.requested = intent["requested"] and not intent["declined"]
            lead.declined = intent["declined"]
            lead.evidence["intent"] = {"quote": intent["quote"], "message_index": intent["message_index"]}
    return lead


def lead_is_ready(lead):
    # Organizer Q&A 14–15: one contact is enough; name/company are optional.
    return bool(lead.requested and not lead.declined and any(lead.fields.get(f) for f in CONTACT_FIELDS))


def parse_payload(raw):
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        raise ModelError("invalid_consultation_json", retryable=True) from None
    if not isinstance(obj, dict):
        raise ModelError("invalid_consultation_schema", retryable=True)
    if (not isinstance(obj.get("answer"), str) or not obj["answer"].strip()
            or len(obj["answer"]) > 10000
            or obj.get("status") not in ("answered", "clarification", "knowledge_gap", "out_of_scope")):
        raise ModelError("invalid_consultation_schema", retryable=True)
    for key in ("citations", "contacts"):
        if not isinstance(obj.get(key), list) or len(obj[key]) > 40 or not all(isinstance(x, dict) for x in obj[key]):
            raise ModelError("invalid_consultation_schema", retryable=True)
    if not isinstance(obj.get("summary"), dict) or not isinstance(obj.get("intent"), dict):
        raise ModelError("invalid_consultation_schema", retryable=True)
    return obj


def validate_sources(payload, fragments):
    by_id = {f.source_id: f for f in fragments}
    sources, seen = [], set()
    for citation in payload["citations"]:
        sid, quote = citation.get("source_id"), citation.get("quote")
        if not isinstance(sid, str) or sid not in by_id or not isinstance(quote, str):
            raise ModelError("ungrounded_citation", retryable=True)
        fragment = by_id[sid]
        if len(quote.strip()) < 12 or normalized(quote) not in normalized(fragment.text):
            raise ModelError("ungrounded_citation", retryable=True)
        if sid not in seen:
            sources.append({"document_id": fragment.document_id, "chunk_id": fragment.chunk_id,
                            "source_id": sid, "quote": quote})
            seen.add(sid)
    if payload["status"] == "answered" and not sources:
        raise ModelError("missing_evidence", retryable=True)
    return sources


def make_summary(payload, request, lead, fragments):
    raw = payload.get("summary", {})
    summary = build_facts(request.messages, request.summary_so_far, raw)
    summary["state_version"] = 2
    source_ids = {f.source_id: f for f in fragments}
    products = raw.get("products", [])
    summary["products"] = []
    if isinstance(products, list):
        for product in products[:10]:
            if not isinstance(product, dict):
                continue
            sid, name = product.get("source_id"), product.get("name")
            if isinstance(sid, str) and sid in source_ids and isinstance(name, str) and name.strip():
                if normalized(name) in normalized(source_ids[sid].text):
                    summary["products"].append({"name": name, "source_id": sid})
    questions = raw.get("manager_questions", [])
    summary["manager_questions"] = [q[:500] for q in questions[:10] if isinstance(q, str) and not answered_topics(q, summary)] if isinstance(questions, list) else []
    summary["action_plan"] = extract_actions(payload.get("answer", "")) if payload.get("status") in ('answered', 'clarification') else []
    summary["contacts"] = dict(lead.fields)
    summary["missing_fields"] = [] if any(lead.fields.get(f) for f in CONTACT_FIELDS) else ["contact"]
    summary["delivery_status"] = "prepared" if lead_is_ready(lead) else "draft"
    summary["sent"] = False
    return summary


class Consultant:
    def __init__(self, client, retriever, settings):
        self.client, self.retriever, self.settings = client, retriever, settings

    def respond(self, request: ConsultationRequest, *, deadline=None, answer_only=False):
        started = time.monotonic()
        # Request is revalidated in case a caller mutated it after construction.
        request.__post_init__()
        lead = seed_lead(request)
        fragments, used_chars, seen = [], 0, set()
        try:
            candidates = self.retriever.search(retrieval_query(request.messages), self.settings.top_k)
            for fragment in candidates:
                if fragment.source_id in seen or not fragment.text.strip():
                    continue
                if used_chars + len(fragment.text) > self.settings.context_chars:
                    continue  # Never cut a qualifier away from its section.
                fragments.append(fragment)
                seen.add(fragment.source_id)
                used_chars += len(fragment.text)
        except Exception:
            return self._failure(request, lead, started, "retrieval_error")
        context = {
            "messages": [{"index": i, **asdict(m)} for i, m in enumerate(request.messages)],
            "lead_so_far": asdict(lead),
            "sources": [{"source_id": f.source_id, "text": f.text} for f in fragments],
        }
        if answer_only:
            # CSV judges only answer text. Lead extraction and exact-quote schema
            # validation belong to the interactive backend contract, not this path.
            context.pop("lead_so_far")
            model_messages = [{"role": "system", "content": ANSWER_PROMPT},
                              {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
            try:
                answer = self.client.complete(model_messages, deadline=deadline).strip()
                # Tolerate a model wrapping an otherwise usable answer in JSON.
                # No other generated field is treated as validated evidence/state.
                candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer, flags=re.I).strip()
                if candidate.startswith("{"):
                    try:
                        wrapper = json.loads(candidate)
                        if isinstance(wrapper, dict) and isinstance(wrapper.get("answer"), str):
                            answer = wrapper["answer"].strip()
                    except (ValueError, TypeError):
                        pass
                answer = sanitize_delivery(answer)
                if not answer or len(answer) > 10000:
                    raise ModelError("invalid_answer_length")
                return ConsultationResult(
                    answer, "answered", [], round((time.monotonic() - started) * 1000),
                    lead, lead_is_ready(lead), make_summary({}, request, lead, fragments),
                    {"retrieved_sources": [f.source_id for f in fragments],
                     "context_chars": used_chars, "repairs": 0, "error_code": None,
                     "mode": "answer_only", "evidence_validation": "not_performed"})
            except ModelError as exc:
                return self._failure(request, lead, started, exc.code, fragments, http_status=exc.status)
        # Keep the current turn explicit even when it is a short answer embedded
        # in a long transcript. The global message index/evidence contract is unchanged.
        context["latest_user_message"] = {
            "index": len(request.messages) - 1, "content": request.messages[-1].content}
        confirmed_facts = build_facts(request.messages, request.summary_so_far)
        context["confirmed_facts"] = confirmed_facts
        context["requested_output"] = "action_plan" if asks_for_plan(request.messages[-1].content) else "continue_consultation"
        model_messages = [{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
        repairs = 0
        suppressed_questions = 0
        try:
            while True:
                try:
                    raw = self.client.complete(model_messages, deadline=deadline)
                    payload = parse_payload(raw)
                    sources = validate_sources(payload, fragments)
                    if repeats_previous_answer(payload["answer"], request.messages):
                        raise ModelError("repeated_answer", retryable=True)
                    questions = re.findall(r'[^.!?\n]*\?', payload['answer'])
                    # Also catch an imperative requesting facts already provided.
                    questions += [s for s in re.split(r'(?<=[.!?])\s+|\n+', payload['answer'])
                                  if re.search(r'нужно уточнить|уточните|сообщите', s, re.I)]
                    if any(answered_topics(q, confirmed_facts) for q in questions):
                        # After the bounded repair, retain useful sourced advice
                        # while omitting the redundant request. Never show a
                        # technical error solely for an already-answered question.
                        cleaned, omitted = without_answered_questions(payload['answer'], confirmed_facts)
                        if repairs and sources and len(cleaned) >= 40:
                            payload['answer'] = cleaned
                            suppressed_questions = omitted
                            if '?' not in cleaned:
                                payload['status'] = 'answered'
                        else:
                            raise ModelError('answered_question', retryable=True)
                    if (context['requested_output'] == 'action_plan' and payload['status'] in ('answered', 'clarification')
                            and not extract_actions(payload['answer'])):
                        raise ModelError('missing_action_plan', retryable=True)
                    break
                except ModelError as exc:
                    if repairs >= 1 or not exc.retryable:
                        raise
                    repairs += 1
                    # Do not echo untrusted output back as a new instruction.
                    if exc.code in ("repeated_answer", "answered_question", "missing_action_plan"):
                        repair = ("Предыдущий результат отклонён: он дословно повторяет прошлый ответ "
                                  "ассистента, хотя клиент добавил новую реплику latest_user_message. "
                                  "Продолжи разговор с учётом этой реплики. Если клиент ответил на часть "
                                  "составного вопроса, считай эту часть известной; уточни только оставшееся "
                                  "или дай следующий полезный шаг. Не возвращай прежнее объяснение целиком. "
                                  "Верни JSON прежней схемы, сохрани проверяемые источники и факты клиента.")
                        if exc.code == 'answered_question':
                            repair = ("Предыдущий ответ снова запрашивает сведения, уже имеющиеся в confirmed_facts. "
                                      "Не спрашивай повторно известную схему снятия показаний, наличие счётчиков, режим "
                                      "или оборудование. Если составной вопрос частично закрыт, спроси только неизвестную часть. "
                                      "Ответь на latest_user_message и верни JSON прежней схемы с проверяемыми citations.")
                        elif exc.code == 'missing_action_plan':
                            repair = ("Клиент явно попросил конкретные следующие действия, но ответ их не содержит. "
                                      "Дай краткий нумерованный план по sources и confirmed_facts; каждый пункт начни "
                                      "глаголом действия. Не заменяй план очередным предложением расчёта или заявки. "
                                      "Не придумывай рекомендаций при нехватке sources: тогда status=knowledge_gap. "
                                      "Верни JSON прежней схемы с проверяемыми citations.")
                    else:
                        repair = ("Предыдущий результат отклонён валидатором: " + exc.code +
                                  ". Повтори ответ в заданном JSON. Следуй формату citations из системных правил; "
                                  "выбирай идентификаторы только из sources, не придумывай их. "
                                  "Если подтверждения нет, status=knowledge_gap. Не добавляй рассуждения.")
                    model_messages.append({"role": "user", "content": repair})
            lead = extract_lead(payload, request)
            summary = make_summary(payload, request, lead, fragments)
            answer = payload["answer"].strip()
            # Delivery is not implemented: never let a generated claim imply it is.
            answer = sanitize_delivery(answer)
            ready_claim = re.search(r"заявк\w*\s+(?:уже\s+)?(?:готова|подготовлена|сформирована)", answer, re.I)
            if ready_claim and not lead_is_ready(lead):
                missing = ", ".join(FIELD_LABELS[f] for f in summary["missing_fields"])
                replacement = ("Можем продолжить консультацию без оформления заявки." if lead.declined
                               else "Заявка пока в черновике" + ("; осталось уточнить: " + missing if missing else "; нужно ваше подтверждение") + ".")
                answer = re.sub(r"[^.!?\n]*" + re.escape(ready_claim.group(0)) + r"[^.!?\n]*[.!?]?",
                                replacement, answer, flags=re.I)
            if len(answer) > 10000:
                raise ModelError("answer_too_long")
            return ConsultationResult(answer, payload["status"], sources,
                                      round((time.monotonic() - started) * 1000), lead,
                                      lead_is_ready(lead), summary,
                                      {"retrieved_sources": [f.source_id for f in fragments],
                                       "context_chars": used_chars, "repairs": repairs,
                                       "suppressed_known_questions": suppressed_questions,
                                       "error_code": None})
        except ModelError as exc:
            return self._failure(request, lead, started, exc.code, fragments, repairs, http_status=exc.status)

    @staticmethod
    def _failure(request, lead, started, code, fragments=(), repairs=0, http_status=None):
        summary = make_summary({}, request, lead, fragments)
        return ConsultationResult(TECHNICAL_ANSWER, "technical_error", [],
                                  round((time.monotonic() - started) * 1000), lead,
                                  lead_is_ready(lead), summary,
                                  {"error_code": code, "http_status": http_status, "repairs": repairs,
                                   "retrieved_sources": [f.source_id for f in fragments]})
