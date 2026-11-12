"""Backend adapter. The backend owns sessions, persistence and authentication."""
from __future__ import annotations

from pathlib import Path

from consultant import Consultant
from contracts import ConsultationRequest, LeadState, Message
from llm_client import LLMClient
from retrieval import LexicalRetriever
from settings import Settings


def create_consultant(knowledge_zip: str | Path, *, retriever=None, settings=None):
    settings = settings or Settings.from_env()
    return Consultant(LLMClient(settings), retriever if retriever is not None else
                      LexicalRetriever.from_zip(knowledge_zip), settings)


def respond_json(service: Consultant, payload: dict, *, deadline=None) -> dict:
    """Use in a thread pool from an async endpoint. Pass full active-session history."""
    if not isinstance(payload, dict):
        raise ValueError("Request must be an object")
    raw = payload.get("messages")
    if not isinstance(raw, list) or not all(isinstance(m, dict) for m in raw):
        raise ValueError("messages must be an array of objects")
    messages = [Message(m.get("role"), m.get("content")) for m in raw]
    old = payload.get("lead")
    if old is not None:
        if not isinstance(old, dict) or not isinstance(old.get("fields", {}), dict) or not isinstance(old.get("evidence", {}), dict):
            raise ValueError("Invalid lead object")
        if not all(isinstance(value, dict) for value in old.get("evidence", {}).values()):
            raise ValueError("Invalid lead evidence")
        if type(old.get("requested", False)) is not bool or type(old.get("declined", False)) is not bool:
            raise ValueError("Lead intent flags must be boolean")
        old = LeadState(old.get("session_id"), old.get("fields", {}), old.get("evidence", {}),
                        old.get("requested", False), old.get("declined", False))
    request = ConsultationRequest(payload.get("session_id"), messages, old)
    return service.respond(request, deadline=deadline).to_dict()


def save_prepared_lead(result, directory):
    """Explicit local export for a prepared lead; no network delivery is performed."""
    import os
    import uuid
    from contracts import ConsultationResult
    if not isinstance(result, ConsultationResult) or not result.lead_ready or result.lead.declined:
        raise ValueError("Only a validated, requested lead with a contact can be saved")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / ("lead-" + uuid.uuid4().hex + ".txt")
    lines = ["Обращение подготовлено. Внешней отправки не было.", result.summary.get("brief", "")]
    lines.extend(label + ": " + result.lead.fields[field]
                 for field, label in (("phone", "Телефон"), ("full_name", "Имя"), ("company", "Компания"))
                 if result.lead.fields.get(field))
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write("\n".join(line for line in lines if line) + "\n")
    return destination
