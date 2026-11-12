import unittest
from contracts import Message
from contact_flow import contact_reply


def messages(*texts):
    return [Message('user', text) for text in texts]


class ContactChannelTests(unittest.TestCase):
    def test_optional_identity_refusal_keeps_phone_task_and_power(self):
        result = contact_reply(messages(
            'У нас склад в Туле, хотим солнечную станцию на крыше, примерно 50 кВт. Нужен менеджер.',
            'Мой телефон +7 900 123-45-67. Имя и компанию пока не хочу сообщать. Подготовьте заявку.'))
        for fact in ['Туле', 'на крыше', '50 кВт', '+79001234567', 'ничего не отправлено']:
            self.assertIn(fact, result)
        for claim in ['свяжется', 'позвонит', 'принята', 'Уточните имя']:
            self.assertNotIn(claim, result)

    def test_phone_refusal_preserves_user_email(self):
        for separator in [', ', ' — ', '; ', ' но ']:
            with self.subTest(separator=separator):
                result = contact_reply(messages(
                    'Нужна консультация по учёту воды для управляющей компании. Связаться можно по email manager@example.org.',
                    'Телефон не дам' + separator + 'пишите на указанный email. Составьте краткую заявку.'))
                self.assertIn('учёту воды', result)
                self.assertIn('manager@example.org', result)
                self.assertIn('Черновик', result)
                self.assertNotIn('Какой контакт', result)

    def test_email_withdrawal_preserves_phone(self):
        result = contact_reply(messages(
            'Нужен менеджер по проверке совместимости приборов. Телефон +7 900 123-45-67. Почта user@example.org.',
            'Не используйте мою почту. Подготовьте итоговую заявку.'))
        self.assertIn('+79001234567', result)
        self.assertNotIn('user@example.org', result)
        self.assertIn('совместимости приборов', result)

    def test_all_contacts_withdrawal_does_not_prepare_draft(self):
        self.assertIsNone(contact_reply(messages(
            'Нужен менеджер. Телефон +7 900 123-45-67. Почта user@example.org.',
            'Отзываю все контакты. Подготовьте заявку.')))

    def test_negative_manager_request_is_not_consent(self):
        for text in ['Мне не нужен менеджер.', 'Не хочу менеджера.', 'Не надо специалиста.', 'Мне не нужна заявка.']:
            self.assertIsNone(contact_reply(messages(text + ' Телефон +7 900 123-45-67.')))

    def test_examples_are_not_promoted_to_contacts_or_tasks(self):
        result = contact_reply(messages('Подготовьте заявку. Например, телефон +7 900 123-45-67.'))
        self.assertNotIn('+79001234567', result)
        self.assertIn('одного контакта', result)

    def test_product_question_with_a_contact_is_not_intercepted(self):
        self.assertIsNone(contact_reply(messages(
            'Нужен менеджер. Почта client@example.org. А с какой точностью распознаются показания?')))

    def test_declined_topic_is_not_restored(self):
        result = contact_reply(messages(
            'Хотим обсудить солнечную станцию с менеджером.',
            'Солнечная станция не интересует, нужны показания водомеров по фото.',
            'Составьте краткую заявку. Почта water@example.org.'))
        self.assertIn('показания водомеров', result)
        self.assertNotIn('солнечную', result.casefold())

    def test_budget_or_metered_value_is_not_a_phone(self):
        for value in ['Бюджет 10000000000 рублей.', 'Расход 89001234567 кВтч.', 'В проекте 1234567890 единиц.']:
            result = contact_reply(messages('Подготовьте заявку. ' + value))
            self.assertIn('одного контакта', result)
            self.assertNotIn('Контакт:', result)

    def test_labelled_international_number_is_a_contact(self):
        result = contact_reply(messages('Подготовьте заявку. Телефон 12025550123.'))
        self.assertIn('+12025550123', result)

    def test_withdrawal_synonyms_preserve_other_channel(self):
        for refusal in ['Не присылайте сообщения на мою почту.', 'Не храните мой email.', 'Не высылайте ничего на email.']:
            result = contact_reply(messages(
                'Нужен менеджер по проверке приборов. Телефон +7 900 123-45-67. Почта user@example.org.',
                refusal + ' Составьте заявку.'))
            self.assertIn('+79001234567', result)
            self.assertNotIn('user@example.org', result)


if __name__ == '__main__':
    unittest.main()
