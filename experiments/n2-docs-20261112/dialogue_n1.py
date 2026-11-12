"""Transcript decoding for the N1 modes: the A2 parser plus a wider set of speaker labels."""
import re

from contracts import Message
from dialogue import parse_question

CLIENT = ("пользователь", "клиент", "user", "human", "покупатель", "заказчик", "посетитель", "вопрос")
LABEL = re.compile(r"^\s*(?:\*\*)?(Пользователь|Клиент|Покупатель|Заказчик|Посетитель|Вопрос|User|Human|"
                   r"Ассистент|Бот|Консультант|Менеджер|Оператор|Помощник|Ответ|Assistant|AI|Bot)"
                   r"(?:\*\*)?\s*:\s*(?:\*\*)?", re.I | re.M)


def parse_dialogue(question):
    base = parse_question(question)
    matches = list(LABEL.finditer(question))
    if len(matches) < 2 or question[:matches[0].start()].strip():
        return base
    decoded = []
    for i, match in enumerate(matches):
        role = "user" if match[1].lower() in CLIENT else "assistant"
        end = matches[i + 1].start() if i + 1 < len(matches) else len(question)
        content = question[match.end():end].strip()
        if not content:
            continue
        if decoded and decoded[-1].role == role:     # two labels of one speaker in a row
            decoded[-1] = Message(role, decoded[-1].content + "\n" + content)
        else:
            decoded.append(Message(role, content))
    # Prefer the wider label set only when it really separates more turns.
    if decoded and decoded[-1].role == "user" and len(decoded) > len(base):
        return decoded
    return base
