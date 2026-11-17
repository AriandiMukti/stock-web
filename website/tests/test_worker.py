import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from dream_agent.store import Store
from dream_agent.worker import configure, control, tick, load
from dream_agent.dreaming import review


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'account.sqlite3'
        self.store = Store(self.path)
        self.case = dict(ticker='ADRO', as_of='2026-11-02', period='2020-01-01', revenue=120,
                         previous_revenue=100, source='', comparable=False, synthetic=True)
        configure(self.store, 'Riset', self.case, 30, 60, 'test')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_restart_dedup_and_procedure_update(self):
        tick(self.store, 1793577600)
        self.assertEqual(len(self.store.runs()), 1)
        self.assertEqual(self.store.active()[0], 1)
        self.store.close()
        self.store = Store(self.path)
        tick(self.store, 1793577660)
        self.assertEqual(len(self.store.runs()), 1)
        review(self.store, 1, 'reviewer', 'Checked', True)
        tick(self.store, 1793577720)
        self.assertEqual(len(self.store.runs()), 2)
        self.assertEqual(self.store.runs()[-1]['version'], 2)
        self.assertTrue(self.store.verify())

    def test_pause_stop_resume(self):
        for action in ('pause', 'stop'):
            control(self.store, action, 'test')
            tick(self.store, 1793577600)
            self.assertEqual(self.store.runs(), [])
        control(self.store, 'resume', 'test')
        tick(self.store, 1793577600)
        self.assertEqual(len(self.store.runs()), 1)

    def test_multi_worker_no_duplicates(self):
        def call(_):
            store = Store(self.path)
            try:
                tick(store, 1793577600)
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(call, range(3)))
        self.assertEqual(len(self.store.runs()), 1)
        self.assertEqual(len(self.store.proposals()), 1)

    def test_retry_does_not_stop_loop(self):
        with patch('dream_agent.worker.run', side_effect=RuntimeError('temporary')):
            tick(self.store, 1793577600)
        self.assertEqual(load(self.store)['status'], 'running')
        self.assertIn('temporary', load(self.store)['last_error'])
        tick(self.store, 1793577631)
        self.assertEqual(len(self.store.runs()), 1)
        self.assertIsNone(load(self.store)['last_error'])

    def test_changed_input_and_new_day_run(self):
        tick(self.store, 1793577600)
        case = dict(self.case, revenue=130)
        configure(self.store, 'Riset', case, 30, 60, 'test')
        tick(self.store, 1793577601)
        tick(self.store, 1793664001)
        self.assertEqual(len(self.store.runs()), 3)

    def test_atomic_crash_recovery(self):
        with patch('dream_agent.worker.dream', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                tick(self.store, 1793577600)
        self.assertEqual(self.store.runs(), [])
        tick(self.store, 1793577600)
        self.assertEqual(len(self.store.runs()), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
