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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
