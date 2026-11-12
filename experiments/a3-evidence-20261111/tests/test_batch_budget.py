import csv
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from settings import Settings
from solution import run


class Clock:
    def __init__(self, value=100.0):
        self.value = value
        self.lock = threading.Lock()

    def now(self):
        with self.lock:
            return self.value

    def consume_until(self, deadline):
        with self.lock:
            self.value = max(self.value, deadline)


def result(request):
    return SimpleNamespace(status="answered", answer="Полный ответ " + request.session_id, debug={})


class BatchBudgetTests(unittest.TestCase):
    def rows(self, count):
        return [(str(i), "Условия проекта %d?" % i) for i in range(count)]

    def execute(self, rows, service, clock, workers, deadline):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "submission.csv"
            cfg = Settings("http://localhost/v1", "test", "test", workers=workers)
            with patch("solution.time.monotonic", side_effect=clock.now):
                statuses = run(rows, service, cfg, path, deadline=deadline)
            with path.open() as stream:
                reader = csv.DictReader(stream)
                output = list(reader)
                self.assertEqual(reader.fieldnames, ["id", "answer"])
            self.assertEqual([x["id"] for x in output], [x[0] for x in rows])
            self.assertTrue(all(x["answer"].strip() for x in output))
            return statuses, output

    def test_api_latency_above_soft_share_does_not_zero_entire_batch(self):
        clock = Clock()
        calls = []

        class Service:
            supports_budget_hint = True

            def respond(self, request, *, deadline, answer_only, budget_hint):
                calls.append((request.session_id, deadline, budget_hint))
                # One deterministic worker reproduces the large-batch issue:
                # each useful API response needs20s, initial fair share is14s.
                # Hard per-row timeouts would yield no useful answers at all.
                if deadline - clock.now() < 20:
                    clock.consume_until(deadline)
                    return SimpleNamespace(status="technical_error", answer="Техническая ошибка",
                                           debug={"error_code": "deadline_exceeded"})
                clock.consume_until(clock.now() + 20)
                return result(request)

        statuses, output = self.execute(self.rows(80), Service(), clock, 1, 1220.0)
        self.assertEqual(calls[0][2], 14.0)
        self.assertEqual(statuses.count("answered"), 56)
        self.assertEqual(statuses.count("deadline_exceeded"), 24)
        self.assertEqual(sum(row["answer"].startswith("Полный ответ") for row in output), 56)
        self.assertTrue(all(deadline == 1220 for _, deadline, _ in calls))
        self.assertEqual(clock.now(), 1220.0)

    def test_concurrent_first_wave_gets_soft_share_and_global_deadline(self):
        clock = Clock()
        barrier = threading.Barrier(2)
        calls = []
        lock = threading.Lock()

        class Service:
            supports_budget_hint = True

            def respond(self, request, *, deadline, answer_only, budget_hint):
                with lock:
                    calls.append((request.session_id, deadline, budget_hint))
                if request.session_id in ("csv-0", "csv-1"):
                    barrier.wait(timeout=2)
                return result(request)

        statuses, _ = self.execute(self.rows(6), Service(), clock, 2, 220.0)
        self.assertEqual(statuses, ["answered"] * 6)
        budgets = {session: (deadline, hint) for session, deadline, hint in calls}
        self.assertEqual(budgets["csv-0"], (220.0, 40.0))
        self.assertEqual(budgets["csv-1"], (220.0, 40.0))
        self.assertTrue(all(deadline == 220 for _, deadline, _ in calls))

    def test_failed_row_releases_its_share_for_remaining_rows(self):
        clock = Clock()
        calls = []

        class Service:
            supports_budget_hint = True

            def respond(self, request, *, deadline, answer_only, budget_hint):
                calls.append((request.session_id, deadline, budget_hint))
                if request.session_id == "csv-0":
                    # Fails immediately, leaving the whole remaining budget.
                    raise ValueError("synthetic failure")
                clock.consume_until(clock.now() + 10)
                return result(request)

        statuses, _ = self.execute(self.rows(3), Service(), clock, 1, 160.0)
        self.assertEqual(statuses.count("case_error"), 1)
        self.assertEqual(statuses.count("answered"), 2)
        self.assertEqual(calls, [("csv-0", 160.0, 20.0), ("csv-1", 160.0, 30.0),
                                 ("csv-2", 160.0, 50.0)])

    def test_legacy_consultant_receives_no_unsupported_hint(self):
        clock = Clock()
        calls = []

        class Service:
            def respond(self, request, *, deadline, answer_only):
                calls.append(deadline)
                return result(request)

        statuses, _ = self.execute(self.rows(3), Service(), clock, 1, 160.0)
        self.assertEqual(statuses, ["answered"] * 3)
        self.assertEqual(calls, [160.0] * 3)

    def test_expired_global_deadline_keeps_all_ids_without_calls(self):
        clock = Clock()

        class Service:
            def respond(self, *args, **kwargs):
                raise AssertionError("Must not call model after global deadline")

        statuses, _ = self.execute(self.rows(4), Service(), clock, 2, 0.0)
        self.assertEqual(statuses, ["deadline_exceeded"] * 4)


if __name__ == "__main__":
    unittest.main()
