"""Stateless consultation service used by both CSV runner and backend integration."""
from dataclasses import asdict
import json
import re
import time

from contracts import ConsultationRequest, ConsultationResult, LeadState
from dialogue import retrieval_query
from llm_client import ModelError
from prompts import ANSWER_PROMPT, SYSTEM_PROMPT

TECHNICAL_ANSWER = ("Сейчас не удалось получить ответ модели из-за технического сбоя. "
                    "Это не означает, что информации нет в базе знаний. "
                    "Попробуйте повторить вопрос позже; заявку пока не отправляли.")
FIELDS = ("full_name", "phone", "company")
FIELD_LABELS = {"full_name": "ФИО", "phone": "телефон", "company": "название компании"}


def sanitize_delivery(answer):
    sent_claim = re.search(r"(?:заявк\w*\s+(?:успешно\s+)?(?:отправлен|передан)|"
                           r"(?:отправил|передал)\w*\s+(?:ваш\w*\s+)?заявк)", answer, re.I)
    if sent_claim:
        answer = re.sub(r"[^.!?\n]*" + re.escape(sent_claim.group(0)) + r"[^.!?\n]*[.!?]?",
                        "Заявку можно подготовить; отправки менеджеру пока нет.", answer, flags=re.I)
    return answer.strip()


def normalized(text):
    return " ".join(text.casefold().replace("ё", "е").split())


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


def contact_value(field, value, quote):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        return None
    value = value.strip()
    if field == "phone":
        digits = phone_digits(value)
        candidates = re.findall(r"\+?\d[\d ()\-]{8,}\d", quote)
        if 10 <= len(digits) <= 15 and any(phone_digits(c) == digits for c in candidates):
            return "+" + digits if len(digits) > 10 else digits
        return None
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
                value = contact_value(field, old.fields.get(field), evidence["quote"])
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
        value = contact_value(field, item.get("value"), item["quote"])
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
    return bool(lead.requested and not lead.declined and lead.fields.get("phone"))


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
            or obj.get("status") not in ("answered", "clarification", "knowledge_gap", "out_of_scope", "lead_step")):
        raise ModelError("invalid_consultation_schema", retryable=True)
    for key in ("citations", "contacts"):
        if not isinstance(obj.get(key), list) or len(obj[key]) > 40 or not all(isinstance(x, dict) for x in obj[key]):
            raise ModelError("invalid_consultation_schema", retryable=True)
    if not isinstance(obj.get("summary"), dict) or not isinstance(obj.get("intent"), dict):
        raise ModelError("invalid_consultation_schema", retryable=True)
    return obj


def validate_sources(payload, fragments):
    # A lead_step never exposes model prose: render_lead_step replaces it with
    # verified user data. Extra model citations are unused, not product evidence.
    if payload["status"] == "lead_step":
        return []
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
    summary = {}
    for field in ("task", "object", "parameters", "constraints"):
        items = raw.get(field, [])
        summary[field] = []
        if isinstance(items, list):
            for item in items[:30]:
                if isinstance(item, dict) and user_evidence(item, request.messages):
                    # Store the client's actual words, not an unchecked model paraphrase.
                    summary[field].append({"value": item["quote"], "message_index": item["message_index"]})
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
    summary["manager_questions"] = [q[:500] for q in questions[:10] if isinstance(q, str)] if isinstance(questions, list) else []
    summary["contacts"] = dict(lead.fields)
    summary["missing_fields"] = [] if lead.fields.get("phone") else ["phone"]
    summary["optional_missing_fields"] = [f for f in ("full_name", "company") if not lead.fields.get(f)]
    summary["delivery_status"] = "prepared" if lead_is_ready(lead) else "draft"
    summary["sent"] = False
    # Use verified user quotes, not an unchecked generated manager summary.
    chosen = []
    for field in ("task", "constraints", "parameters", "object"):
        for item in sorted(summary[field], key=lambda row: row["message_index"], reverse=True):
            value = item["value"]
            if value not in chosen and len(value) <= 400:
                chosen.append(value)
            if len(chosen) == 2:
                break
        if len(chosen) == 2:
            break
    summary["brief"] = " ".join("Клиент: «" + text + "»." for text in chosen)
    return summary


def render_lead_step(lead, summary):
    # Never expose arbitrary model claims under a citation-free contact status.
    if lead.declined:
        return "Продолжим консультацию без заявки и контактов."
    if not lead.requested:
        return "Хотите подготовить обращение к специалисту?"
    if not lead.fields.get("phone"):
        return "Какой телефон указать для связи? Имя и компания необязательны."
    brief = summary["brief"]
    return ("Обращение подготовлено, но не отправлено. " + (brief + " " if brief else "")
            + "Телефон: " + lead.fields["phone"] + ".")


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
        model_messages = [{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
        repairs = 0
        contact_fallback = None
        try:
            while True:
                raw = self.client.complete(model_messages, deadline=deadline)
                payload = None
                try:
                    payload = parse_payload(raw)
                    sources = validate_sources(payload, fragments)
                    break
                except ModelError as exc:
                    if (payload is not None and exc.code in ("missing_evidence", "ungrounded_citation")
                            and lead_is_ready(extract_lead(payload, request))):
                        # Product prose remains rejected. A verified, requested
                        # contact can still be prepared without exposing that prose.
                        contact_fallback = exc.code
                        payload["status"] = "lead_step"
                        payload["citations"] = []
                        sources = []
                        break
                    if repairs >= 1:
                        raise
                    repairs += 1
                    # Do not echo untrusted output back as a new instruction.
                    model_messages.append({"role": "user", "content":
                        "Предыдущий результат отклонён валидатором: " + exc.code +
                        ". Повтори ответ в заданном JSON. Используй точные source_id и дословные цитаты. "
                        "Если подтверждения нет, status=knowledge_gap. Не добавляй рассуждения."})
            lead = extract_lead(payload, request)
            summary = make_summary(payload, request, lead, fragments)
            answer = (render_lead_step(lead, summary) if payload["status"] == "lead_step"
                      else payload["answer"].strip())
            if contact_fallback:
                answer += " Дополнительные сведения о продукте не удалось подтвердить; в обращении сохранены только ваши данные."
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
                                       "error_code": contact_fallback,
                                       "product_answer_rejected": bool(contact_fallback)})
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
