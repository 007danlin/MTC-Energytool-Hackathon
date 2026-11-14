import json
import unittest
from consultation_state import build_facts, answered_topics, extract_actions
from consultant import Consultant
from contracts import ConsultationRequest, Fragment, Message
from retrieval import FixedRetriever
from settings import Settings

WAREHOUSE = ('У нас склад и офисная часть, площадь 500 м², два арендатора. '
             'Хотим понять, почему с сентября выросли счета за электроэнергию. '
             'Показания снимаем вручную раз в месяц, видим только общую сумму. Режим работы не менялся. С чего начать?')
HOUSE = ('Уточнение — объект: Частный дом\n\nУточнение — задача: Хочу уменьшить потребление\n\n'
         'Уточнение — известные сведения: Расходы сейчас 30000 рублей в год\n\nДополнение — условия: Хочу подешевле')
PLAN = ('Чтобы выявить причину роста счетов, рекомендую следующий план: '
        '1) проанализировать показания за последние три месяца; '
        '2) проверить, нет ли аномалий в работе общего счётчика; '
        '3) рассмотреть возможность подключения к облачной платформе учёта. Это поможет контролировать потребление.')


class StateTests(unittest.TestCase):
    def values(self, state, key):
        return [item['value'] for item in state[key]]

    def test_free_text_is_split_even_if_model_puts_entire_message_in_task(self):
        state = build_facts([Message('user', WAREHOUSE)], proposed={'task':[{'quote':WAREHOUSE, 'message_index':0}]})
        self.assertEqual(self.values(state, 'object'), ['У нас склад и офисная часть'])
        self.assertEqual(self.values(state, 'task'), ['Хотим понять, почему с сентября выросли счета за электроэнергию'])
        for value in ['площадь 500 м²', 'два арендатора', 'Показания снимаем вручную раз в месяц', 'видим только общую сумму', 'Режим работы не менялся']:
            self.assertIn(value, self.values(state, 'parameters'))

    def test_partial_summary_keeps_old_facts_and_ignores_assistant_claims(self):
        history=[Message('user', HOUSE), Message('assistant','У вас 900 счётчиков'), Message('user','Есть приборы учёта'),
                 Message('assistant','Как снимаете показания?'), Message('user','Показания снимаю вручную раз в месяц. Какие шаги дальше?')]
        previous=build_facts(history[:3])
        proposed={'parameters':[{'quote':'Показания снимаю вручную раз в месяц','message_index':4}],
                  'object':[{'quote':'900 счётчиков','message_index':1}]}
        state=build_facts(history, previous, proposed)
        self.assertEqual(self.values(state,'object'),['Частный дом'])
        self.assertEqual(self.values(state,'task'),['Хочу уменьшить потребление'])
        self.assertEqual(self.values(state,'constraints'),['Хочу подешевле'])
        self.assertEqual(set(self.values(state,'parameters')),{'Расходы сейчас 30000 рублей в год','Есть приборы учёта','Показания снимаю вручную раз в месяц'})

    def test_corrections_replace_the_property_not_all_facts(self):
        history=[Message('user', WAREHOUSE),Message('assistant','Уточните расходы.'),
                 Message('user','Расходы сейчас 30000 рублей в год.'),Message('assistant','Понял.'),
                 Message('user','Расходы теперь 25000 рублей в год. Показания теперь снимаем автоматически каждый день. Составь план.')]
        state=build_facts(history, build_facts(history[:3]))
        values=self.values(state,'parameters')
        self.assertIn('Расходы теперь 25000 рублей в год',values)
        self.assertNotIn('Расходы сейчас 30000 рублей в год',values)
        self.assertNotIn('Показания снимаем вручную раз в месяц',values)
        self.assertIn('площадь 500 м²',values)
        self.assertNotIn('Составь план',self.values(state,'task'))

    def test_comparative_periods_are_not_silently_treated_as_corrections(self):
        history=[Message('user','Расходы за сентябрь 30000 рублей.'),Message('assistant','Есть следующий месяц?'),
                 Message('user','Расходы за октябрь 35000 рублей.')]
        state=build_facts(history,build_facts(history[:1]))
        self.assertEqual(len(self.values(state,'parameters')),2)

    def test_long_list_keeps_all_confirmed_facts(self):
        history=[Message('user',f'Дополнение — известные сведения: Зона {i}: площадь {i+10} м²') for i in range(35)]
        state=build_facts(history,build_facts(history[:30]))
        self.assertEqual(len(self.values(state,'parameters')),35)

    def test_explicit_replace_and_append_and_newer_evidence(self):
        history=[Message('user',HOUSE),Message('assistant','Понял'),
                 Message('user','Уточнение — известные сведения: Площадь 100 м²\n\nДополнение — известные сведения: Есть приборы учёта')]
        state=build_facts(history,build_facts(history[:1]))
        self.assertEqual(self.values(state,'parameters'),['Площадь 100 м²','Есть приборы учёта'])
        self.assertEqual(self.values(state,'task'),['Хочу уменьшить потребление'])

    def test_no_questions_hypotheticals_or_foreign_evidence_as_facts(self):
        history=[Message('user','Если площадь 100 м², что меняется? Например, два арендатора. Есть ли счётчики?')]
        forged={'parameters':[{'quote':'Если площадь 100 м², что меняется?','message_index':0},
                              {'quote':'площадь 500 м²','message_index':0}, {'quote':'два арендатора','message_index':4}, {'quote':'два арендатора','message_index':0}]}
        self.assertEqual(self.values(build_facts(history,proposed=forged),'parameters'),[])

    def test_already_known_question_topics_but_unknown_count_remains(self):
        state=build_facts([Message('user',WAREHOUSE)])
        self.assertTrue(answered_topics('Какова схема сбора данных: вручную или автоматически?',state))
        self.assertTrue(answered_topics('Как часто снимаете показания?',state))
        self.assertTrue(answered_topics('Менялся ли режим работы?',state))
        self.assertFalse(answered_topics('Сколько приборов учёта на объекте?',state))
        self.assertFalse(answered_topics('Какой тип организации: собственник или управляющая компания?',state))

    def test_real_inline_infinitive_plan_and_no_fake_questions(self):
        steps=extract_actions(PLAN)
        self.assertEqual(len(steps),3)
        self.assertTrue(steps[0].startswith('проанализировать'))
        self.assertFalse(extract_actions('Есть ли счётчики? Хотите заказать расчёт?'))
        self.assertFalse(extract_actions('Уточните, есть ли у вас присоединённая мощность — это поможет подобрать решение.'))
        self.assertEqual(extract_actions('Уточните у энергетика действующий тариф.'), ['Уточните у энергетика действующий тариф.'])
        conditional='Если данные не выявят аномалий, рассмотрите возможность автоматизации учёта.'
        self.assertEqual(extract_actions(conditional),[conditional])
        self.assertEqual(len(extract_actions('1. Сравните счета.\n2. Проверьте показания.\n3. Подготовьте описание задачи.')),3)

    def test_known_facts_sent_to_model_and_repeated_question_repaired(self):
        calls=[]
        outputs=['Какова схема сбора данных?', 'Проверьте показания за сопоставимые периоды.']
        class Client:
            def complete(self,messages,deadline=None):
                calls.append(json.loads(messages[1]['content']))
                return json.dumps({'answer':outputs[len(calls)-1],'status':'clarification','summary':{},'citations':[],'contacts':[],'intent':{}})
        result=Consultant(Client(),FixedRetriever([]),Settings('http://localhost','test','test',attempts=1)).respond(ConsultationRequest('t',[Message('user',WAREHOUSE)]))
        self.assertEqual(result.debug['repairs'],1)
        self.assertIn('confirmed_facts',calls[0])
        self.assertEqual(result.summary['state_version'],2)
        self.assertEqual(result.summary['action_plan'],['Проверьте показания за сопоставимые периоды.'])
        self.assertEqual(result.summary['manager_questions'],[])

    def test_redundant_question_after_repair_does_not_hide_sourced_advice(self):
        advice='Сравните счета и показания за одинаковые периоды, чтобы оценить динамику потребления.'
        fragment=Fragment('guide.md','step',advice)
        class Client:
            def complete(self,messages,deadline=None):
                return json.dumps({'answer':advice+' Как часто снимаете показания?', 'status':'clarification',
                                   'summary':{},'contacts':[],'intent':{},
                                   'citations':[{'source_id':fragment.source_id,'quote':advice}]})
        result=Consultant(Client(),FixedRetriever([fragment]),Settings('http://unused','test','test')).respond(
            ConsultationRequest('redundant-question',[Message('user',WAREHOUSE)]))
        self.assertEqual(result.answer,advice)
        self.assertEqual(result.status,'answered')
        self.assertEqual(result.debug['repairs'],1)
        self.assertEqual(result.debug['suppressed_known_questions'],1)


if __name__=='__main__': unittest.main()
