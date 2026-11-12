"""Host-only regression checks for source-grounded blind review packets."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class BlindPacketTests(unittest.TestCase):
    def test_review_conditions_survive_without_private_strategy_metadata(self):
        with tempfile.TemporaryDirectory(prefix='blind-packet-test-') as folder:
            directory = Path(folder)
            question = 'Можно ли обещать окупаемость по этому ориентиру?'
            fixtures = {
                'questions': (['id', 'question'], ['case-1', question]),
                'control': (['id', 'answer'], ['case-1', 'Нужен расчёт объекта.']),
                'candidate': (['id', 'answer'], ['case-1', 'Ориентир не является гарантией.']),
            }
            for name, (header, row) in fixtures.items():
                with (directory / (name + '.csv')).open('w', encoding='utf8', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(header)
                    writer.writerow(row)
            public_criteria = {
                'required_criteria': ['Не обещать результат до расчёта.'],
                'conditional_criteria': ['Если указан срок, сохранить условия применимости.'],
                'unknown_handling': 'При нехватке исходных данных назвать пробел.',
                'family': 'conditional_project_payback',
                'source_evidence': {'product#s1': 'Оценка зависит от конкретного объекта.'},
            }
            rubric = {'cases': [{
                'id': 'case-1', 'question': question, **public_criteria,
                'strategy_label': 'PRIVATE_STRATEGY_NAME',
                'expected_winner': 'PRIVATE_WINNER_HINT',
                'candidate_score': 'PRIVATE_SCORE_HINT',
                'unrelated_field': {'note': 'PRIVATE_AUTHOR_NOTE'},
            }]}
            (directory / 'rubric.json').write_text(
                json.dumps(rubric, ensure_ascii=False), encoding='utf8')
            command = [sys.executable, str(ROOT / 'tools/build_blind_comparison.py')]
            for name in fixtures:
                command.extend(['--' + name, str(directory / (name + '.csv'))])
            command.extend(['--rubric', str(directory / 'rubric.json'),
                            '--output', str(directory / 'review'), '--seed', '42'])
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            packet_text = (directory / 'review.packet.json').read_text(encoding='utf8')
            packet = json.loads(packet_text)
            criteria = packet['cases'][0]['criteria']
            for field, expected in public_criteria.items():
                with self.subTest(field=field):
                    self.assertIn(field, criteria)
                    self.assertEqual(criteria[field], expected)
            for field in ('strategy_label', 'expected_winner', 'candidate_score', 'unrelated_field'):
                self.assertNotIn(field, criteria)
            self.assertNotIn('PRIVATE_', packet_text)


if __name__ == '__main__':
    unittest.main()
