import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json
import tempfile
import unittest
from unittest.mock import patch
from dream_agent.store import Store
from dream_agent.worker import configure_live, tick, load, control
from dream_agent.live import analyze, symbol


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'test.sqlite3')
        configure_live(self.store, 'ADRO', 900, 60, 'test')
        self.payload = dict(ticker='ADRO.JK', retrieved_at='2026-11-02T00:00:00+00:00',
                            price_date='2026-11-02', close=2400, price_change_pct=-2,
                            window_start='2026-08-03', statements=[], sources=[])

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_live_fetch_report_dedup(self):
        with patch('dream_agent.live.collect', return_value=self.payload):
            tick(self.store, 2000)
            tick(self.store, 3000)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM research_reports').fetchone()[0], 1)
        self.assertTrue(self.store.verify())
        report=json.loads(self.store.db.execute('SELECT body FROM research_reports').fetchone()[0])
        self.assertTrue(any('tidak tersedia' in x for x in report['risks']))

    def test_errors_are_not_synthetic_success(self):
        with patch('dream_agent.live.collect', side_effect=TimeoutError('timeout')):
            tick(self.store, 2000)
        self.assertEqual(load(self.store)['last_error'], 'timeout')
        self.assertEqual(self.store.runs(), [])

    def test_pause_during_network_does_not_publish(self):
        def fetch(_):
            control(self.store, 'pause', 'test')
            return self.payload
        with patch('dream_agent.live.collect', side_effect=fetch):
            tick(self.store, 2000)
        self.assertEqual(load(self.store)['status'], 'paused')
        self.assertIsNone(load(self.store).get('last_report'))

    def test_leases_and_validation(self):
        with self.assertRaises(ValueError):symbol('../../etc')
        with self.assertRaises(ValueError):configure_live(self.store,'ADRO',30,60,'test')
        from dream_agent.worker import save
        config=load(self.store);config['lease_until']=3000
        with self.store.transaction():save(self.store,config)
        with patch('dream_agent.live.collect') as fetch:
            tick(self.store,2000)
            fetch.assert_not_called()

    def test_risks_and_comparison(self):
        payload=dict(self.payload, statements=[dict(period='2020-01-01',revenue=100,net_income=-10)])
        report=analyze(payload,dict(self.payload,close=2300))
        self.assertIn('close',report['changed_fields'])
        self.assertTrue(any('negatif' in x for x in report['risks']))


if __name__=='__main__':unittest.main(verbosity=2)
