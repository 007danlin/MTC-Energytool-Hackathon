"""Focused guards for failure patterns observed in the live browser audit."""
import json
import unittest

from consultant import (Consultant, initial_cost_discovery, meter_reuse_question,
                        confused_wholesale_threshold, bill_diagnosis_focus,
                        loss_product_fragment)
from consultation_state import build_facts, answered_topics
from contracts import ConsultationRequest, Fragment, Message
from retrieval import FixedRetriever
from settings import Settings

CFG=Settings('http://unused','fixture','fixture',attempts=1)
TARIFF=Fragment('10-energy/11-price-categories.md','s005',
                'Потребители с максимальной мощностью от 670 кВт рассчитываются по категориям с третьей по шестую.')
STEPS=Fragment('10-energy/14-tariffs.md','s001',
               'При скачке счёта сравните два периода отдельно по объёму, средней цене и плате за мощность.')
BAD_THRESHOLD='Если мощность превышает 670 кВт, переход на оптовый рынок может снизить надбавку.'
LOSS=Fragment('20-products/24-losses.md','s009',
              'Поиск коммерческих потерь электроэнергии > Что нужно от клиента\nТребуется суточная выгрузка день/ночь и архив не менее одного года.')
LOSS_REFERENCE=Fragment('00-reference/03-calculation-and-requests.md','s007',
                        'Расчёт по объекту > Для поиска коммерческих потерь\nМинимально достаточно суточных данных с разбивкой на день и ночь.')
CAFE='Это небольшое кафе. Счета выросли после установки второй холодильной витрины, показания снимаем вручную. Какие первые действия помогут разобраться?'


def payload(answer,status='clarification',source=None,**extra):
    value=dict(answer=answer,status=status,citations=[] if source is None else [
        {'source_id':source.source_id,'quote':source.text}],contacts=[],intent={},summary={})
    value.update(extra)
    return value


class Client:
    def __init__(self,*answers):self.answers=answers;self.calls=[]
    def complete(self,messages,deadline=None):
        self.calls.append(messages[:])
        return json.dumps(self.answers[min(len(self.calls)-1,len(self.answers)-1)],ensure_ascii=False)


class WebTurnBoundaryTests(unittest.TestCase):
    def request(self,*texts):
        return ConsultationRequest('turn-focus',[Message('user' if i%2==0 else 'assistant',text) for i,text in enumerate(texts)])

    def test_vague_first_cost_question_gets_focus_and_safe_fallback(self):
        request=self.request('Хочу снизить расходы на электроэнергию, но не понимаю, с чего начать.')
        client=Client(payload('Если мощность от 750 кВт, подойдёт оптовый рынок, а ниже — солнечная станция.',
                              summary={'products':[{'name':'Солнечная станция','source_id':STEPS.source_id}],
                                       'action_plan':['Установите солнечную станцию.'],
                                       'manager_questions':['Какова мощность для солнечной станции?']}))
        result=Consultant(client,FixedRetriever([STEPS]),CFG).respond(request)
        self.assertEqual(result.status,'clarification')
        self.assertEqual(result.debug['routing'],'initial_object_clarification')
        self.assertIn('объекте',result.answer)
        self.assertNotIn('кВт',result.answer)
        self.assertEqual(len(client.calls),1)
        self.assertIn('Не подбирай продукты',client.calls[0][-1]['content'])
        self.assertEqual(result.summary['task'][0]['message_index'],0)
        self.assertEqual(result.summary['products'],[])
        self.assertNotIn('солнеч',json.dumps(result.summary,ensure_ascii=False))

    def test_explicit_questions_and_known_objects_keep_normal_consultation(self):
        for text in ['Как снизить расходы кафе, с чего начать?',
                     'Хочу снизить расходы. Как выбрать тариф?',
                     'Хочу снизить расходы: подойдёт солнечная станция?',
                     'Хочу снизить расходы: возможен ли выход на оптовый рынок при 750 кВт?',
                     'Хочу снизить расходы: сравни платформу учёта и солнечные станции.',
                     'Счёт 30000 рублей. С чего начать снижение расходов?']:
            with self.subTest(text=text):
                request=self.request(text)
                self.assertFalse(initial_cost_discovery(request,build_facts(request.messages)))
        request=self.request('Хочу снизить расходы.','О каком объекте речь?','Не понимаю, с чего начать.')
        self.assertFalse(initial_cost_discovery(request,build_facts(request.messages)))

    def test_cafe_is_known_without_conflating_owner_role(self):
        request=self.request('Это небольшое кафе. Счета выросли после установки второй холодильной витрины, показания снимаем вручную.')
        facts=build_facts(request.messages)
        self.assertEqual(facts['object'],[{'value':'Это небольшое кафе','message_index':0}])
        self.assertIn('object_type',answered_topics('Что ещё нужно уточнить: присоединённая мощность и тип организации?',facts))
        self.assertFalse(answered_topics('Какой тип организации: собственник или управляющая компания?',facts))

    def test_meter_reuse_cannot_be_promised_for_unknown_models(self):
        request=self.request('У каждого арендатора уже есть отдельный электросчётчик. Можно начать автоматизацию с этих счётчиков?')
        client=Client(payload('Да, можно подключить существующие счётчики.',source=STEPS))
        result=Consultant(client,FixedRetriever([STEPS]),CFG).respond(request)
        self.assertEqual(result.status,'clarification')
        self.assertEqual(result.debug['routing'],'unconfirmed_existing_meter')
        self.assertFalse(result.answer.startswith('Да'))
        self.assertIn('тип или модель',result.answer)
        self.assertNotIn('прилож',result.answer)
        self.assertEqual(result.sources,[])
        self.assertEqual(len(client.calls),1)

    def test_supported_model_and_non_compatibility_question_are_not_overridden(self):
        source=Fragment('meters.md','s1','Поддерживается подключение счётчика Меркурий 230.')
        request=self.request('У нас существующий счётчик Меркурий 230. Можно его подключить?')
        self.assertIsNone(meter_reuse_question(request,[source]))
        self.assertIsNone(meter_reuse_question(self.request('Существующие счётчики показывают расход. Как сравнить два месяца?'),[source]))
        client=Client(payload('В источнике подтверждено подключение Меркурий 230.',status='answered',source=source))
        result=Consultant(client,FixedRetriever([source]),CFG).respond(request)
        self.assertEqual(result.status,'answered')
        self.assertNotIn('routing',result.debug)

    def test_known_but_unconfirmed_model_is_not_requested_again(self):
        source=Fragment('meters.md','s1','Платформа поддерживает более 300 типов приборов.')
        request=self.request('У нас существующий счётчик Quasar9000. Можно его подключить?')
        result=Consultant(Client(payload('Да, подключим.')),FixedRetriever([source]),CFG).respond(request)
        self.assertEqual(result.status,'knowledge_gap')
        self.assertNotIn('Какой',result.answer)
        self.assertIn('модель счётчика учтена',result.answer)
        self.assertEqual(result.summary['manager_questions'],[])

    def test_explicitly_unknown_model_is_not_requested_again(self):
        request=self.request('Тип и модель счётчиков пока неизвестны. Подтвердите: можно ли подключить эти существующие счётчики без замены?')
        result=Consultant(Client(payload('Да, можно.')),FixedRetriever([STEPS]),CFG).respond(request)
        self.assertEqual(result.status,'knowledge_gap')
        self.assertEqual(result.debug['routing'],'unconfirmed_existing_meter')
        self.assertNotIn('?',result.answer)
        self.assertIn('можно указать позже',result.answer)
        self.assertEqual(result.summary['manager_questions'],[])
        self.assertIn('неизвестны',result.summary['parameters'][0]['value'])

    def test_one_supported_meter_does_not_confirm_the_whole_mixed_set(self):
        source=Fragment('meters.md','s1','Поддерживается подключение счётчика Меркурий 230.')
        request=self.request('Существующие счётчики Меркурий 230 и Quasar9000. Можно их подключить без замены?')
        check=meter_reuse_question(request,[source])
        self.assertIsNotNone(check)
        self.assertEqual(set(check['models']),{'Меркурий 230','Quasar9000'})

    def test_threshold_confusion_is_repaired_once_without_inventing_another_threshold(self):
        good=payload('1. Сравните объём потребления за два периода.\n2. Проверьте среднюю цену и плату за мощность.',status='answered',source=STEPS)
        client=Client(payload(BAD_THRESHOLD,source=TARIFF),good)
        result=Consultant(client,FixedRetriever([TARIFF,STEPS]),CFG).respond(self.request('Это небольшое кафе. Какие первые действия помогут разобраться в росте счёта?'))
        self.assertEqual(result.answer,good['answer'])
        self.assertEqual(result.debug['repairs'],1)
        self.assertIn('Не подставляй',client.calls[1][-1]['content'].replace('не подставляй','Не подставляй'))
        self.assertEqual(json.loads(client.calls[0][1]['content'])['requested_output'],'action_plan')
        self.assertIn('Тип объекта уже указан',client.calls[0][-1]['content'])

    def test_threshold_guard_allows_negation_and_separate_correct_comparison(self):
        self.assertTrue(confused_wholesale_threshold(BAD_THRESHOLD,[TARIFF]))
        self.assertFalse(confused_wholesale_threshold(BAD_THRESHOLD,[]))
        for text in ['670 кВт недостаточно для выхода на оптовый рынок.',
                     '670 кВт не является порогом выхода на оптовый рынок.',
                     'При 670 кВт перейти на оптовый рынок нельзя.',
                     '670 кВт относятся к ценовым категориям, а для выхода на оптовый рынок порог 750 кВт.',
                     'От 670 кВт действуют ценовые категории 3–6. Выход на оптовый рынок обсуждают от 750 кВт.']:
            with self.subTest(text=text):self.assertFalse(confused_wholesale_threshold(text,[TARIFF]))

    def test_bad_threshold_after_repair_stays_a_visible_error(self):
        client=Client(payload(BAD_THRESHOLD,source=TARIFF))
        result=Consultant(client,FixedRetriever([TARIFF]),CFG).respond(self.request('Нужен расчёт для кафе.'))
        self.assertEqual(result.status,'technical_error')
        self.assertEqual(result.debug['error_code'],'misapplied_wholesale_threshold')
        self.assertEqual(len(client.calls),2)

    def test_bill_diagnosis_context_excludes_only_product_owned_sources(self):
        general=Fragment('00-reference/02-product-scope-and-limits.md','s001',
                         'Общие границы\nСведения для коммерческих потерь относятся к отдельному проекту; для других задач состав уточняется.')
        good=payload('Сравните два периода отдельно по объёму, средней цене и плате за мощность.',status='answered',source=STEPS)
        client=Client(good)
        result=Consultant(client,FixedRetriever([LOSS,LOSS_REFERENCE,general,STEPS]),CFG).respond(self.request(CAFE))
        context=json.loads(client.calls[0][1]['content'])
        ids=[source['source_id'] for source in context['sources']]
        self.assertEqual(ids,[general.source_id,STEPS.source_id])
        self.assertEqual(result.debug['source_scope'],'bill_diagnosis')
        self.assertEqual(result.debug['excluded_sources'],[LOSS.source_id,LOSS_REFERENCE.source_id])
        self.assertEqual(result.answer,good['answer'],'the sourced model answer is not replaced by a template')
        self.assertEqual(result.debug['repairs'],0)
        self.assertEqual(len(client.calls),1)
        self.assertEqual(result.debug['context_chars'],len(general.text)+len(STEPS.text))
        self.assertFalse(loss_product_fragment(general),'body mentions alone must not discard a general source')

    def test_legitimate_loss_projects_keep_their_requirements(self):
        for question in [CAFE+' Нужно найти коммерческие потери.',
                         'Это кафе. Счета выросли. Какие первые действия для поиска хищений?',
                         'Это кафе. Потребление выросло. Какие первые действия по поиску аномалий?']:
            with self.subTest(question=question):
                request=self.request(question)
                self.assertFalse(bill_diagnosis_focus(request,build_facts(request.messages)))
                client=Client(payload('Подготовьте годовую выгрузку для проекта поиска коммерческих потерь.',status='answered',source=LOSS))
                result=Consultant(client,FixedRetriever([LOSS,LOSS_REFERENCE,STEPS]),CFG).respond(request)
                ids=[source['source_id'] for source in json.loads(client.calls[0][1]['content'])['sources']]
                self.assertIn(LOSS.source_id,ids)
                self.assertIn(LOSS_REFERENCE.source_id,ids)
                self.assertNotIn('source_scope',result.debug)
                self.assertEqual(result.status,'answered')
                self.assertEqual([source['source_id'] for source in result.sources],[LOSS.source_id])

    def test_loss_interest_from_customer_history_is_retained_not_invented_by_assistant(self):
        request=self.request('У нас кафе. Хотим найти коммерческие потери.',
                             'Уточните проблему.',CAFE)
        self.assertFalse(bill_diagnosis_focus(request,build_facts(request.messages)))
        request=self.request('Хочу снизить расходы на электроэнергию.',
                             'Рассмотрите поиск коммерческих потерь.',CAFE)
        self.assertTrue(bill_diagnosis_focus(request,build_facts(request.messages)))
        self.assertFalse(bill_diagnosis_focus(self.request('Счета выросли. Какие первые действия?'),{'object':[]}))

    def test_excluded_product_cannot_be_cited_even_after_existing_single_repair(self):
        bad=payload('Для точного расчёта требуется годовая выгрузка день/ночь.',status='answered',source=LOSS)
        good=payload('Сравните объём, цену и плату за мощность до и после изменений.',status='answered',source=STEPS)
        client=Client(bad,good)
        result=Consultant(client,FixedRetriever([LOSS,STEPS]),CFG).respond(self.request(CAFE))
        self.assertEqual(result.answer,good['answer'])
        self.assertEqual(result.debug['repairs'],1)
        self.assertEqual(len(client.calls),2)
        self.assertEqual([source['source_id'] for source in result.sources],[STEPS.source_id])
        client=Client(bad)
        failed=Consultant(client,FixedRetriever([LOSS,STEPS]),CFG).respond(self.request(CAFE))
        self.assertEqual(failed.status,'technical_error')
        self.assertEqual(len(client.calls),2,'the product scope does not add any extra repair budget')

    def test_answer_only_context_is_unchanged_for_bill_diagnosis(self):
        class RawClient:
            def complete(self,messages,deadline=None):
                self.context=json.loads(messages[1]['content'])
                return 'Проверочный текст.'
        client=RawClient()
        Consultant(client,FixedRetriever([LOSS,LOSS_REFERENCE,STEPS]),CFG).respond(self.request(CAFE),answer_only=True)
        self.assertEqual([source['source_id'] for source in client.context['sources']],
                         [LOSS.source_id,LOSS_REFERENCE.source_id,STEPS.source_id])


if __name__=='__main__':unittest.main()
