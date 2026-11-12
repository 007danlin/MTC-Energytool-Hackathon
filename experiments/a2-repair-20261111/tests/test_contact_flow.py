import unittest
from contracts import Message
from contact_flow import contact_reply


def conversation(*items):
    return [Message(role, text) for role, text in items]


class ContactFlowTests(unittest.TestCase):
    def test_bare_phone_after_user_requested_handoff(self):
        messages = conversation(('user', 'Нужно собрать показания трёх площадок. Нужен менеджер.'),
                                ('assistant', 'Ваш телефон?'), ('user', '+7 900 123-45-67'))
        result = contact_reply(messages)
        self.assertIn('+79001234567', result)
        self.assertIn('трёх площадок', result)
        self.assertIn('ничего не отправлено', result)
        self.assertNotIn('ФИО', result)

    def test_collective_handoff_intent_accepts_later_bare_contact(self):
        for intent in ['Давайте передадим задачу специалисту.',
                       'Направим обращение менеджеру.']:
            with self.subTest(intent=intent):
                messages = conversation(
                    ('user', 'Нужно обсудить подключение двух объектов.'),
                    ('user', intent),
                    ('assistant', 'Как с вами связаться?'),
                    ('user', '+7 900 654-32-10'))
                result = contact_reply(messages)
                self.assertIsNotNone(result)
                self.assertIn('+79006543210', result)
                self.assertIn('подключение двух объектов', result)
                self.assertIn('ничего не отправлено', result)

    def test_negated_or_quoted_collective_handoff_is_not_consent(self):
        for intent in ['Давайте не передадим задачу специалисту.',
                       'Не будем направлять обращение менеджеру.',
                       'Не направим задачу специалисту.',
                       'В примере написано: «Давайте передадим задачу специалисту».',
                       '> Направим обращение менеджеру.']:
            with self.subTest(intent=intent):
                self.assertIsNone(contact_reply(conversation(
                    ('user', 'Нужно обсудить подключение двух объектов.'),
                    ('user', intent), ('assistant', 'Ваш контакт?'),
                    ('user', '+7 900 654-32-10'))))
        self.assertIsNone(contact_reply(conversation(
            ('user', 'Нужно обсудить подключение двух объектов.'),
            ('assistant', 'Давайте передадим задачу специалисту.'),
            ('user', '+7 900 654-32-10'))))

    def test_collective_handoff_can_be_withdrawn_before_bare_contact(self):
        for refusal in ['Не будем направлять обращение менеджеру.',
                        'Не хотим передавать задачу специалисту.']:
            with self.subTest(refusal=refusal):
                self.assertIsNone(contact_reply(conversation(
                    ('user', 'Давайте передадим задачу специалисту.'),
                    ('user', refusal), ('user', '+7 900 654-32-10'))))

    def test_email_is_sufficient(self):
        result = contact_reply(conversation(('user', 'Подготовьте заявку. Моя почта user@example.org.')))
        self.assertIn('user@example.org', result)
        self.assertNotIn('Какой контакт', result)
        self.assertNotIn('телефон', result)

    def test_latest_phone_replaces_previous(self):
        messages = conversation(('user', 'Нужен менеджер. Мой телефон +7 900 111-11-11.'),
                                ('user', 'Подготовьте заявку. Новый номер +7 900 222-22-22.'))
        result = contact_reply(messages)
        self.assertIn('+79002222222', result)
        self.assertNotIn('+79001111111', result)

    def test_explicit_replacement_in_same_turn(self):
        for text in ['Подготовьте заявку. Вместо +7 900 111-11-11 используйте +7 900 222-22-22.',
                     'Подготовьте заявку. Не +7 900 111-11-11, а +7 900 222-22-22.',
                     'Подготовьте заявку. Используйте +7 900 222-22-22 вместо +7 900 111-11-11.']:
            with self.subTest(text=text):
                result = contact_reply(conversation(('user', text)))
                self.assertIn('+79002222222', result)
                self.assertNotIn('+79001111111', result)

    def test_withdrawal_does_not_resurrect_contact_or_ask_again(self):
        messages = conversation(('user', 'Нужен менеджер. Телефон +7 900 111-11-11.'),
                                ('user', 'Не используйте мой номер. Телефон больше не дам.'),
                                ('user', 'Подготовьте заявку.'))
        self.assertIsNone(contact_reply(messages))

    def test_two_alternative_numbers_are_ambiguous(self):
        self.assertIsNone(contact_reply(conversation(('user',
            'Подготовьте заявку. +7 900 111-11-11 или +7 900 222-22-22.'))))

    def test_quoted_example_and_assistant_contacts_are_not_evidence(self):
        for text in ['Подготовьте заявку. Например, +7 900 111-11-11.',
                     'Подготовьте заявку. В инструкции написано «телефон +7 900 111-11-11».',
                     'Подготовьте заявку.\n> мой телефон +7 900 111-11-11']:
            with self.subTest(text=text):
                result = contact_reply(conversation(('assistant', 'Номер +7 900 333-33-33.'), ('user', text)))
                self.assertNotIn('7900', result)
                self.assertIn('одного контакта', result)

    def test_mixed_product_question_is_not_bypassed(self):
        for text in ['Подготовьте заявку, телефон +7 900 111-11-11. Какая точность распознавания?',
                     'Мой телефон +7 900 111-11-11. Объясните отличие вариантов и позвоните.']:
            self.assertIsNone(contact_reply(conversation(('user', text))))

    def test_contact_sufficiency_question_can_prepare_draft(self):
        messages = conversation(('user', 'Нужен менеджер, вопрос по проверке совместимости наших счётчиков.'),
                                ('assistant', 'Дайте имя, компанию и телефон.'),
                                ('user', 'Сейчас могу дать только телефон +7 900 456-78-90. Этого достаточно?'))
        result = contact_reply(messages)
        self.assertIn('+79004567890', result)
        self.assertIn('проверке совместимости', result)
        self.assertNotIn('имя', result)

    def test_superseded_topic_and_assistant_facts_are_excluded(self):
        messages = conversation(('user', 'Нужен менеджер по старому проекту.'),
                                ('assistant', 'Вам гарантирована экономия 90 процентов.'),
                                ('user', 'Старый проект не подходит, возвращаемся к учёту электричества. Нужно собрать показания трёх площадок.'),
                                ('user', 'Подготовьте заявку. Телефон +7 900 345-67-89.'))
        result = contact_reply(messages)
        self.assertIn('трёх площадок', result)
        self.assertNotIn('Старый проект', result)
        self.assertNotIn('экономия', result)

    def test_missing_contact_requires_only_one_channel(self):
        result = contact_reply(conversation(('user', 'Подготовьте заявку.')))
        self.assertIn('одного контакта', result)
        self.assertNotIn('ФИО', result)
        self.assertNotIn('компани', result)

    def test_refusal_and_general_questions_use_normal_consultation(self):
        for text in ['Телефон не дам, хочу разобраться без заявки.', 'Как работают приборы?',
                     'Контакты не оставлю. Объясните отличие вариантов.']:
            self.assertIsNone(contact_reply(conversation(('user', text))))

    def test_device_or_contract_number_is_not_a_phone(self):
        for text in ['Подготовьте заявку. Серийный номер 12345678901.',
                     'Подготовьте заявку. Номер договора 12345678901.']:
            result = contact_reply(conversation(('user', text)))
            self.assertNotIn('12345678901', result)
            self.assertIn('одного контакта', result)

    def test_tax_identifier_is_not_a_contact(self):
        for identifier in ['ИНН 7700000000', 'ОГРН 1234567890123', 'СНИЛС 123-456-789 00']:
            with self.subTest(identifier=identifier):
                result = contact_reply(conversation(('user', 'Нужен менеджер. ' + identifier)))
                self.assertNotIn('Контакт:', result)
                self.assertIn('одного контакта', result)

    def test_product_request_without_question_mark_is_not_bypassed(self):
        for text in [
                'Позвоните на +7 900 111-11-11. Хочу узнать, поддерживает ли ваша платформа учёт воды.',
                'Подготовьте заявку. Телефон +7 900 111-11-11. Нужно понять, как работает система.',
                'Мой телефон +7 900 111-11-11. Позвоните и уточните, можно ли начать с одного прибора.']:
            with self.subTest(text=text):
                self.assertIsNone(contact_reply(conversation(('user', text))))

    def test_inline_contact_does_not_erase_task(self):
        for text, task in [
                ('Нужен менеджер по солнечным панелям, телефон +7 900 111-11-11.', 'солнечным панелям'),
                ('Нужен менеджер по проверке приборов, почта user@example.org.', 'проверке приборов')]:
            with self.subTest(text=text):
                result = contact_reply(conversation(('user', text)))
                self.assertIn(task, result)
                self.assertNotIn('Запрос: связаться со специалистом.', result)

    def test_negated_topic_does_not_resurrect_earlier_task(self):
        messages = conversation(
            ('user', 'Хотим обсудить оптовый рынок с менеджером.'),
            ('user', 'Оптовый рынок не интересует, нужны солнечные панели для склада.'),
            ('user', 'Подготовьте заявку. Телефон +7 900 111-11-11.'))
        result = contact_reply(messages)
        self.assertIn('солнечные панели для склада', result)
        self.assertNotIn('оптовый рынок', result.casefold())
        unresolved = conversation(
            ('user', 'Хотим обсудить оптовый рынок с менеджером.'),
            ('user', 'Этот проект больше не интересует.'),
            ('user', 'Подготовьте заявку. Телефон +7 900 111-11-11.'))
        self.assertIsNone(contact_reply(unresolved))

    def test_sessions_do_not_share_contacts_or_intent(self):
        contact_reply(conversation(('user', 'Подготовьте заявку. Телефон +7 900 111-11-11.')))
        result = contact_reply(conversation(('user', 'Подготовьте заявку.')))
        self.assertNotIn('+7900', result)
        self.assertIsNone(contact_reply(conversation(('user', '+7 900 222-22-22'))))

    def test_handoff_does_not_claim_external_delivery(self):
        result = contact_reply(conversation(('user', 'Передайте менеджеру. Телефон +7 900 111-11-11.')))
        self.assertIn('Черновик', result)
        self.assertIn('ничего не отправлено', result)
        for claim in ['передам', 'направлю', 'позвонит', 'перезвонит', 'отправлена', 'получил']:
            self.assertNotIn(claim, result.casefold())


if __name__ == '__main__':
    unittest.main()
