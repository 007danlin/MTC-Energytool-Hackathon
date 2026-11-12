"""Deterministic evidence catalog and complete, budgeted source selection.

Catalog indices always refer to the original sequence of Fragment objects. The
catalog is a selection aid, not a substitute for full evidence text. No model,
network, corpus-specific IDs, or embedded product facts are used here.
"""
import json
import re


CATALOG_CHARS = 28000
EXCERPT_CHARS = 80
MAX_SELECTIONS = 10


def _heading(fragment):
    return fragment.text.split("\n", 1)[0].strip()


def _normalized(text):
    text = text.casefold().replace("ё", "е")
    return " ".join(re.sub(r"[*_`#]", "", text).split())


def _catalog_size(catalog):
    return len(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))


def evidence_catalog(fragments):
    """Return a compact JSON-serializable catalog covering every input index.

    documents: d (document ordinal), id (document_id), title (root heading).
    sections: i (original fragment index), d, title (leaf), optional excerpt.
    A root-only introduction has title="" and inherits its document title.

    Excerpts share a deterministic maximum length of at most 80 characters.
    They are shortened before any metadata, aiming at <=28000 compact JSON
    characters. If titles alone exceed that budget, all titles are preserved;
    there is no loss of indices or truncation of titles to pretend otherwise.
    The input sequence and its Fragment objects are never modified.
    """
    fragments = tuple(fragments)
    documents, sections, excerpts, document_ordinals = [], [], [], {}
    for index, fragment in enumerate(fragments):
        headings = [part.strip() for part in _heading(fragment).split(" > ")]
        if fragment.document_id not in document_ordinals:
            ordinal = len(documents)
            document_ordinals[fragment.document_id] = ordinal
            documents.append({"d": ordinal, "id": fragment.document_id, "title": headings[0]})
        sections.append({"i": index, "d": document_ordinals[fragment.document_id],
                         "title": headings[-1] if len(headings) > 1 else ""})
        body = fragment.text.partition("\n")[2]
        excerpts.append(" ".join(body.split())[:EXCERPT_CHARS])

    def build(limit):
        return {"documents": documents, "sections": [
            dict(section, excerpt=excerpt[:limit]) if limit and excerpt else dict(section)
            for section, excerpt in zip(sections, excerpts)
        ]}

    # The encoded size is monotonic in the excerpt limit. Zero omits the field
    # altogether, allowing titles to remain available even in large catalogs.
    low, high, accepted = 0, EXCERPT_CHARS, build(0)
    while low <= high:
        middle = (low + high) // 2
        candidate = build(middle)
        if _catalog_size(candidate) <= CATALOG_CHARS:
            accepted = candidate
            low = middle + 1
        else:
            high = middle - 1
    return accepted


_INPUT_ROLE = re.compile(
    r"что нужно от клиента|какие (?:данные|сведения)|исходные данные|входные данные|"
    r"данные от клиента|required inputs|client inputs|input requirements"
)
_GUARD_ROLE = re.compile(
    r"чего утверждать нельзя|что (?:мы )?не делаем|что (?:мы )?не предоставляем|"
    r"что не входит|кому (?:не )?подходит|не подходит|для кого|"
    r"целев(?:ой клиент|ые клиенты|ая аудитория)|"
    r"область применения|границы (?:применения|продукта|решения)|"
    r"ограничени[еяй]|поддерживаемые (?:ресурсы|типы|приборы)|совместимость|"
    r"\b(?:scope|applicability|limitations|restrictions|prohibitions)\b|"
    r"\b(?:not suitable|suitable for|target audience|target customers|unsupported)\b|"
    r"\b(?:what we do not|what we don't|not included|supported resources)\b"
)


def _is_guard(fragment):
    # Inspect all heading roles: e.g. 'Кому подходит > Целевой диапазон'
    # inherits applicability even though its leaf does not say 'ограничения'.
    # Do not inherit the *document* title: an aggregate 'Product limitations'
    # reference document contains different products in its child sections.
    parts = _heading(fragment).split(" > ")
    heading = _normalized(" > ".join(parts[1:] if len(parts) > 1 else parts))
    if _INPUT_ROLE.search(heading):
        return False
    if _GUARD_ROLE.search(heading):
        return True
    # Compact product introductions often expose applicability in their first
    # body line, e.g. '**Кому:** ...', while the heading is just a product name.
    first_lines = fragment.text.partition("\n")[2].splitlines()[:3]
    return any(re.match(r"^(?:кому|для кого|целевая аудитория|целевой клиент|target audience|for whom)\s*[:—-]",
                        _normalized(line)) for line in first_lines)


def resolve_evidence(fragments, indices, context_chars=18000):
    """Resolve selected indices and complete same-document guard bundles.

    Accept at most ten unique integer indices (bool is not an index). Invalid
    selections or budgets raise ValueError; an empty selection is valid.

    Each document's selected primary sections and all applicability, scope and
    prohibition sections form one indivisible bundle. Admit bundles in order of
    the first selected primary; omit a whole bundle if it does not fit. Return
    admitted primaries in the original selection order, followed by their guards
    in document/fragment order. Full Fragment objects are returned unchanged.
    Input-request sections are never appended implicitly, nor are other docs.
    """
    fragments = tuple(fragments)
    if not isinstance(indices, (list, tuple)) or len(indices) > MAX_SELECTIONS:
        raise ValueError("evidence_indices_must_be_list_or_tuple_of_at_most_ten")
    if any(type(index) is not int or not 0 <= index < len(fragments) for index in indices):
        raise ValueError("evidence_index_out_of_range_or_not_integer")
    if len(set(indices)) != len(indices):
        raise ValueError("evidence_indices_must_be_unique")
    if type(context_chars) is not int or context_chars < 0:
        raise ValueError("evidence_context_budget_must_be_nonnegative_integer")
    if not indices:
        return []

    selected = set(indices)
    primary_by_document = {}
    for index in indices:
        primary_by_document.setdefault(fragments[index].document_id, []).append(index)
    guards_by_document = {document: [] for document in primary_by_document}
    for index, fragment in enumerate(fragments):
        if fragment.document_id in guards_by_document and index not in selected and _is_guard(fragment):
            guards_by_document[fragment.document_id].append(index)

    admitted, used_chars = set(), 0
    for document, primary_indices in primary_by_document.items():
        bundle = primary_indices + guards_by_document[document]
        cost = sum(len(fragments[index].text) for index in bundle)
        if used_chars + cost <= context_chars:
            admitted.add(document)
            used_chars += cost
    resolved = [fragments[index] for index in indices if fragments[index].document_id in admitted]
    for document, guard_indices in guards_by_document.items():
        if document in admitted:
            resolved.extend(fragments[index] for index in guard_indices)
    return resolved
