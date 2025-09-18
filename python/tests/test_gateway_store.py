from __future__ import annotations

import os
import tempfile
import unittest

from services.gateway.app.store import RunStore


class RunStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(delete=False)
        self._tmp.close()
        self.store = RunStore(self._tmp.name)

    def tearDown(self) -> None:
        try:
            os.remove(self._tmp.name)
        except FileNotFoundError:
            pass

    def test_create_and_fetch(self) -> None:
        record = self.store.create_run({"targetSpl": 118.0})
        fetched = self.store.get_run(record.id)
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched.status, "queued")
        self.assertAlmostEqual(fetched.params["targetSpl"], 118.0)

    def test_complete_run_updates_status(self) -> None:
        record = self.store.create_run({"targetSpl": 110.0})
        self.store.mark_running(record.id)
        result = {"summary": {"fc_hz": 45.0}}
        self.store.complete_run(record.id, result)
        fetched = self.store.get_run(record.id)
        assert fetched is not None
        self.assertEqual(fetched.status, "succeeded")
        self.assertEqual(fetched.result, result)

    def test_mark_failed_sets_error(self) -> None:
        record = self.store.create_run({})
        self.store.mark_failed(record.id, "boom")
        fetched = self.store.get_run(record.id)
        assert fetched is not None
        self.assertEqual(fetched.status, "failed")
        self.assertEqual(fetched.error, "boom")

    def test_list_runs_returns_newest_first(self) -> None:
        first = self.store.create_run({"targetSpl": 100.0})
        second = self.store.create_run({"targetSpl": 105.0})
        runs = self.store.list_runs()
        self.assertGreaterEqual(len(runs), 2)
        self.assertEqual(runs[0].id, second.id)
        self.assertEqual(runs[1].id, first.id)

    def test_list_runs_with_status_filter(self) -> None:
        queued = self.store.create_run({})
        running = self.store.create_run({})
        self.store.mark_running(running.id)
        completed = self.store.create_run({})
        self.store.mark_running(completed.id)
        self.store.complete_run(completed.id, {"ok": True})

        queued_runs = self.store.list_runs(status="queued")
        self.assertTrue(any(run.id == queued.id for run in queued_runs))
        self.assertFalse(any(run.id == running.id for run in queued_runs))

        running_runs = self.store.list_runs(status="running")
        self.assertTrue(any(run.id == running.id for run in running_runs))

        succeeded_runs = self.store.list_runs(status="succeeded")
        self.assertTrue(any(run.id == completed.id for run in succeeded_runs))

        with self.assertRaises(ValueError):
            self.store.list_runs(status="bogus")

    def test_status_counts_includes_all_statuses(self) -> None:
        self.store.create_run({})
        running = self.store.create_run({})
        failed = self.store.create_run({})
        self.store.mark_running(running.id)
        self.store.mark_running(failed.id)
        self.store.mark_failed(failed.id, "boom")

        counts = self.store.status_counts()
        self.assertEqual(counts["queued"], 1)
        self.assertEqual(counts["running"], 1)
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(counts["succeeded"], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
