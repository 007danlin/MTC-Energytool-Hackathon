"""Append same-product scope guards after the unchanged A2 candidates.

The existing Consultant packs whole sections in order: accepted A2 sources stay
an exact prefix even under tight budgets. Guards use only remaining space; this
additive policy cannot guarantee every applicable guard will fit. No reranking,
new product discovery, network calls or embedded knowledge-base facts.
"""
from pathlib import PurePosixPath
import re
from retrieval import LexicalRetriever

_INPUT_ROLE = re.compile(
    r"что нужно от клиента|какие (?:данные|сведения)|исходные данные|входные данные|"
    r"данные от клиента|required inputs|client inputs|input requirements")
_GUARD_ROLE = re.compile(
    r"чего утверждать нельзя|что (?:мы )?не делаем|что (?:мы )?не предоставляем|"
    r"что не входит|кому (?:не )?подходит|не подходит|для кого|"
    r"целев(?:ой клиент|ые клиенты|ая аудитория)|"
    r"область применения|границы (?:применения|продукта|решения)|"
    r"ограничени[еяй]|поддерживаемые (?:ресурсы|типы|приборы)|совместимость|"
    r"\b(?:scope|applicability|limitations|restrictions|prohibitions)\b|"
    r"\b(?:not suitable|suitable for|target audience|target customers|unsupported)\b|"
    r"\b(?:what we do not|what we don't|not included|supported resources)\b")


def _normalized(text):
    return " ".join(re.sub(r"[*_`#]", "", text.casefold().replace("ё", "е")).split())


def _is_guard(fragment):
    heading, _, body = fragment.text.partition("\n")
    parts = heading.split(" > ")
    # Applicability ancestors govern leaves. Ignore an aggregate document title.
    role = _normalized(" > ".join(parts[1:] if len(parts) > 1 else parts))
    if _INPUT_ROLE.search(role):
        return False
    if _GUARD_ROLE.search(role):
        return True
    return any(re.match(
        r"^(?:кому|для кого|целевая аудитория|целевой клиент|target audience|for whom)\s*[:—-]",
        _normalized(line)) for line in body.splitlines()[:3])


def _is_product_document(document_id):
    path = PurePosixPath(document_id)
    return (any(re.fullmatch(r"(?:\d+-)?products", part) for part in path.parts[:-1])
            and not re.fullmatch(r"(?:\d+-)?(?:portfolio|general)", path.stem))


class GuardedRetriever(LexicalRetriever):
    """A2-compatible retriever; add scope guards for at most two products."""
    def __init__(self, fragments):
        super().__init__(fragments)
        self._guards_by_document = {}
        for fragment in self.fragments:
            if _is_product_document(fragment.document_id) and _is_guard(fragment):
                self._guards_by_document.setdefault(fragment.document_id, []).append(fragment)

    def search(self, query, top_k=12):
        original = super().search(query, top_k)
        # A2 positive-score primary hits precede zero-score companions. Do not
        # derive product scope from previously appended support/guard sections.
        documents = []
        for fragment in original[:max(0, top_k)]:
            if (fragment.score > 0 and _is_product_document(fragment.document_id)
                    and fragment.document_id not in documents):
                documents.append(fragment.document_id)
                if len(documents) == 2:
                    break
        result = list(original)
        seen = {fragment.source_id for fragment in original}
        for document in documents:
            for fragment in self._guards_by_document.get(document, ()):
                if fragment.source_id not in seen:
                    result.append(fragment)
                    seen.add(fragment.source_id)
        return result
