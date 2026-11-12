"""Narrow, stateless contact handoff; ambiguous/product questions stay with the LLM.

Only literal user-provided contact data is used. This module formats a local draft,
never sends it or schedules a call. No product facts or synthetic identity fields.
"""
import re
from typing import Optional

PHONE = re.compile(r'(?<![\w])\+?\d(?:[ ()\t.-]*\d){9,14}(?![\w])')
EMAIL = re.compile(r'(?<![\w@])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w@])')
INTENT = re.compile(
    r'(?:подготов|оформ|сформир|состав|созда)\w*\s+(?:мне\s+)?(?:заявк|обращен|черновик)|'
    r'(?:нужен|нужна|нужно|хочу|хотим)\s+(?:связаться\s+с\s+)?(?:менеджер|специалист)|'
    r'(?:хочу|хотим|давайте|прошу)\b[^.!?\n]{0,120}(?:с\s+менеджер|со\s+специалист)|'
    r'\b(?:позвоните|звоните|перезвоните|свяжитесь|свяжи|соедините)\b|'
    r'(?:передайте|передадим|направьте|направим)\b[^.!?\n]{0,80}(?:менеджер|специалист|заявк|обращен)', re.I)
REFUSAL = re.compile(
    r'\bне\s+(?:надо\s+|нужно\s+|хочу\s+|хотим\s+|буду\s+|будем\s+)?(?:звон|перезвон|пиш|писать|связыв|'
    r'оставл|оставить|да[мв]|давать|сообщ|переда|направ|отправ|использ|запис|сохраня|оформ|готов|подготавли)|'
    r'(?:телефон|контакт|почт\w*|номер)\b[^.!?\n]{0,25}\bне\s+(?:даю|дам|сообщ|остав)|'
    r'\b(?:удали|удалите|забудь|забудьте|отзываю)\b|без\s+(?:телефона|контактов|заявки)', re.I)
EXAMPLE = re.compile(r'\b(?:например|пример\w*|образец|чуж\w*|вымышлен\w*|фиктивн\w*|тестов\w*)\b', re.I)
ANSWER_REQUEST = re.compile(
    r'\b(?:объясни\w*|расскаж\w*|подскаж\w*|сравни\w*|посовет\w*|рассчита\w*|'
    r'уточните|ответь|ответьте)\b|\b(?:хочу|хотим|нужно|надо|хотелось\s+бы)\s+'
    r'(?:узнать|понять|уточнить|выяснить)\b|\b\w+\s+ли\b', re.I)
IDENTIFIER_LABEL = re.compile(
    r'\b(?:инн|огрн|огрнип|кпп|снилс|бик|артикул|паспорт|идентификатор)\b[^0-9+]{0,60}$', re.I)
REJECTED_TASK = re.compile(r'\bне\s+(?:подходит|нужен|нужна|нужно|нужны|интересует|интересуют|рассматриваем|хочу|хотим)\b', re.I)
META_QUESTION = re.compile(
    r'^(?:этого\s+достаточно|достаточно\s+ли\s+(?:этого|телефона|почты|номера)|'
    r'можно\s+(?:без\s+(?:имени|фио|компании)|только\s+(?:телефон|почту)))[\s?!.]*$', re.I)
CONTACT_WORD = re.compile(r'телефон|контакт|почт|номер|email|e-mail', re.I)


def _clean(text):
    text = re.sub(r'```.*?```|`[^`]*`|«[^»]*»|"[^"\n]*"|“[^”]*”|‘[^’]*’', ' ', text, flags=re.S)
    return '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('>'))


def _clauses(text):
    return [c.strip() for c in re.split(r'(?<=[.!?;])\s+|\n+', text) if c.strip()]


def _canonical_phone(raw):
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    return ('+' if len(digits) > 10 or raw.startswith('+') else '') + digits


def _correction(text):
    # Only explicit replacement syntax may discard an old contact in the same turn.
    if re.search(r'\bне\b.*?,\s*а\s+', text, re.I) and (PHONE.search(text) or EMAIL.search(text)):
        return re.split(r',\s*а\s+', text, maxsplit=1, flags=re.I)[1]
    if re.search(r'\bстар\w*\b', text, re.I) and re.search(r'\bнов\w*\b', text, re.I):
        return re.split(r'\bнов\w*\b', text, maxsplit=1, flags=re.I)[1]
    if re.search(r'\bвместо\b', text, re.I):
        before, after = re.split(r'\bвместо\b', text, maxsplit=1, flags=re.I)
        if PHONE.search(before) or EMAIL.search(before):
            return before
        match = re.search(r'\b(?:используйте|укажите|запишите|звоните)\b', after, re.I)
        if match:
            return after[match.start():]
    return text


def _contacts(text):
    result = {'phone': [], 'email': []}
    for clause in _clauses(_correction(_clean(text))):
        if EXAMPLE.search(clause) or REFUSAL.search(clause) or re.search(r'\bне\s+мой\b', clause, re.I):
            continue
        for kind, pattern in [('email', EMAIL), ('phone', PHONE)]:
            for match in pattern.finditer(clause):
                if kind == 'phone' and re.search(
                        r'(?:серийн\w*\s+номер|номер\s+(?:прибор|договор|сч[её]т|заказ|лицев))',
                        clause, re.I):
                    continue
                if kind == 'phone' and IDENTIFIER_LABEL.search(clause[:match.start()]):
                    continue
                value = match.group() if kind == 'email' else _canonical_phone(match.group())
                if value not in result[kind]:
                    result[kind].append(value)
    return result


def _intent(text):
    return any(INTENT.search(c) and not REFUSAL.search(c) and not EXAMPLE.search(c)
               for c in _clauses(_clean(text)))


def _strip_contacts(text):
    return PHONE.sub(' ', EMAIL.sub(' ', text))


def _needs_answer(text):
    # Even with a contact, a substantive current question must reach generation.
    for clause in _clauses(_clean(text)):
        if META_QUESTION.fullmatch(clause):
            continue
        if '?' in clause or ANSWER_REQUEST.search(clause):
            return True
    return False


def _contact_only(text):
    text = _strip_contacts(_clean(text))
    for clause in _clauses(text):
        if META_QUESTION.fullmatch(clause):
            text = text.replace(clause, ' ')
    words = re.findall(r'[^\W\d_]+', text.casefold(), re.U)
    allowed = {'мой','моя','мне','на','для','связи','телефон','телефона','номер','номера',
               'почта','почту','email','e','mail','вот','да','только','сейчас','могу','дать',
               'это','контакт','контакты','звоните','позвоните','пишите','используйте',
               'укажите','запишите','новый','актуальный','вместо','старого','пожалуйста'}
    return all(w in allowed for w in words)


def _task_summary(user_texts):
    """Return (literal summary, uncertain); rejected topics form a history barrier."""
    for original in reversed(user_texts):
        text = _clean(original)
        switch = re.search(r'(?:возвращаемся\s+к|теперь\s+(?:про|о)|вместо\s+этого|'
                           r'речь\s+о|лучше\s+обсудим)\b', text, re.I)
        if switch:
            text = text[switch.start():]
        parts = []
        rejected = False
        # Contact fields and a new task commonly share a sentence. Split at
        # explicit clause boundaries, never discard the entire sentence merely
        # because its second clause contains a phone or a rejected old topic.
        clauses = [part.strip() for sentence in _clauses(text)
                   for part in re.split(r'\s*[,;]\s*|\s+(?:но|зато)\s+', sentence) if part.strip()]
        for clause in clauses:
            if REJECTED_TASK.search(clause):
                rejected = True
                continue
            if (PHONE.search(clause) or EMAIL.search(clause) or EXAMPLE.search(clause)
                    or REFUSAL.search(clause) or CONTACT_WORD.search(clause)):
                continue
            if META_QUESTION.fullmatch(clause) or _contact_only(clause):
                continue
            clause = re.sub(r'^(?:нужен\s+(?:менеджер|специалист)|подготовьте\s+(?:заявку|обращение))\s*[,.:—-]?\s*', '', clause, flags=re.I)
            if not clause or len(re.findall(r'[^\W\d_]+', clause, re.U)) < 3:
                continue
            if INTENT.search(clause) and not re.search(r'обсуд|вопрос\s+по|чтобы|для\s+', clause, re.I):
                continue
            parts.append(clause)
        if parts:
            summary = ' '.join(parts[:2]).strip()
            if len(summary) > 320:
                summary = summary[:317].rsplit(' ', 1)[0].rstrip('.,;:') + '…'
            return summary, False
        if rejected or switch:
            # A later correction with no confidently extracted replacement must
            # reach the normal model path, not resurrect an earlier topic.
            return None, True
    return None, False


def contact_reply(messages) -> Optional[str]:
    """Return a local contact draft only for a clear handoff, otherwise None."""
    if not messages or len(messages) > 200 or messages[-1].role != 'user':
        return None
    if sum(len(m.content) for m in messages) > 100000:
        return None
    user_texts = [m.content for m in messages if m.role == 'user']
    current = user_texts[-1]
    if _needs_answer(current):
        return None
    contacts = {}
    intent = False
    declined = False
    ambiguous = False
    for text in user_texts:
        cleaned = _clean(text)
        refusal = bool(REFUSAL.search(cleaned))
        new = _contacts(text)
        if refusal:
            # Conservative withdrawal: old contacts cannot silently reappear later.
            contacts.clear()
            intent = False
            declined = True
        if _intent(text):
            intent = True
        if any(len(values) > 1 for values in new.values()):
            ambiguous = True
            contacts.clear()
        elif any(new.values()):
            for kind, values in new.items():
                if values:
                    contacts[kind] = values[0]
            ambiguous = False
            declined = False
    current_intent = _intent(current)
    if not current_intent and not (_contact_only(current) and any(_contacts(current).values()) and intent):
        return None
    if ambiguous:
        return None
    if not contacts:
        if declined:
            return None
        return ('Для обращения достаточно одного контакта — телефона или электронной почты. '
                'Какой контакт указать?')
    summary, uncertain = _task_summary(user_texts)
    if uncertain:
        return None
    task = ('Запрос: «' + summary + '». ') if summary else 'Запрос: связаться со специалистом. '
    contact = '; '.join(contacts[k] for k in ('phone', 'email') if k in contacts)
    return ('Черновик обращения для менеджера. ' + task + 'Контакт: ' + contact
            + '. Обращение подготовлено здесь; менеджеру ничего не отправлено.')
