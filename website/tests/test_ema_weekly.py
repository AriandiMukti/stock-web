"""Run: python -m unittest discover -s tests -p test_ema_weekly.py"""
import importlib.util
import json
import re
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import werkzeug
from flask import Flask
from flask_login import LoginManager, UserMixin
from flask_wtf import CSRFProtect

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ema_weekly_fixture', ROOT / 'ema_weekly.py')
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)
if not hasattr(werkzeug, '__version__'):
    werkzeug.__version__ = version('werkzeug')


def frame(values):
    return pd.DataFrame({'Close': values}, index=pd.date_range('2026-01-05', periods=len(values), freq='W-MON'))


class SignalTests(unittest.TestCase):
    def test_true_cross_and_previous_values(self):
        d = frame([100] * 25 + [120])
        row, status = web.evaluate(d, 'TEST', pd.Timestamp('2026-07-03'))
        self.assertEqual(status, 'ok')
        self.assertEqual(row['weeks_ago'], 0)
        self.assertLessEqual(row['previous_ema10'], row['previous_ema20'])
        self.assertGreater(row['ema10'], row['ema20'])

    def test_above_without_new_cross_is_not_a_signal(self):
        row, status = web.evaluate(frame(list(range(100, 126))), 'TEST', pd.Timestamp('2026-07-03'))
        self.assertEqual(status, 'ok')
        self.assertIsNone(row)

    def test_cross_one_week_ago_included_two_weeks_ago_excluded(self):
        d = frame([100] * 23 + [120] * 3)
        self.assertIsNone(web.evaluate(d, 'TEST', pd.Timestamp('2026-07-03'))[0])
        d = frame([100] * 24 + [120] * 2)
        row, _ = web.evaluate(d, 'TEST', pd.Timestamp('2026-07-03'))
        self.assertEqual(row['weeks_ago'], 1)

    def test_partial_current_week_excluded(self):
        d = frame([100] * 25 + [120])
        self.assertIsNone(web.evaluate(d, 'TEST', pd.Timestamp('2026-06-26'))[0])

    def test_short_missing_and_stale_data(self):
        self.assertEqual(web.evaluate(frame([100] * 20), 'TEST', pd.Timestamp('2026-07-03'))[1], 'short_history')
        self.assertEqual(web.evaluate(pd.DataFrame(), 'TEST', pd.Timestamp('2026-07-03'))[1], 'unavailable')
        self.assertEqual(web.evaluate(frame([100] * 25), 'TEST', pd.Timestamp('2026-07-03'))[1], 'stale')

    def test_friday_cutoff_and_weekend(self):
        for date, expected in [('2026-07-03T17:59:00+07:00', '2026-06-26'),
                               ('2026-07-03T18:00:00+07:00', '2026-07-03'),
                               ('2026-07-05T12:00:00+07:00', '2026-07-03'),
                               ('2026-07-06T12:00:00+07:00', '2026-07-03')]:
            self.assertEqual(str(web.last_closed_week(datetime.fromisoformat(date)).date()), expected)

    def test_both_yahoo_column_layouts(self):
        d = frame([100] * 25 + [120])
        multi = pd.concat({'TEST.JK': d}, axis=1)
        pd.testing.assert_frame_equal(web.ticker_frame(multi, 'TEST.JK'), d)
        pd.testing.assert_frame_equal(web.ticker_frame(multi.swaplevel(axis=1), 'TEST.JK'), d)
        self.assertTrue(web.ticker_frame(multi, 'MISSING.JK').empty)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.cache = patch.object(web, 'CACHE_FILE', Path(self.temp.name) / 'cache.json')
        self.cache.start()
        self.cutoff = patch.object(web, 'last_closed_week', return_value=pd.Timestamp('2026-07-03'))
        self.cutoff.start()
        web._report = None
        web._state.update(running=False, processed=0, total=0, error=None)

    def tearDown(self):
        self.cutoff.stop()
        self.cache.stop()
        self.temp.cleanup()

    def test_scan_counts_partial_failure_and_persists(self):
        data = pd.concat({'TEST.JK': frame([100] * 25 + [120])}, axis=1)
        with patch.object(web, '_universe', return_value=['TEST', 'FAIL']), patch.object(web, '_download', return_value=data):
            web._scan()
        self.assertEqual(web._report['counts']['ok'], 1)
        self.assertEqual(web._report['counts']['unavailable'], 1)
        self.assertEqual(web._state['processed'], 2)
        self.assertEqual(json.loads(web.CACHE_FILE.read_text())['rows'][0]['ticker'], 'TEST')

    def test_failed_refresh_keeps_previous_report(self):
        previous = {'rows': [{'ticker': 'SAVED'}]}
        web._report = previous
        with patch.object(web, '_universe', return_value=['TEST']), patch.object(web, '_download', return_value=pd.DataFrame()):
            web._scan()
        self.assertIs(web._report, previous)
        self.assertTrue(web._state['error'])
        self.assertFalse(web._state['running'])

    def test_old_cache_never_returns_cross_older_than_two_weeks(self):
        web._report = {'updated_at': datetime.now(web.JAKARTA).isoformat(), 'week_ending': '2026-06-19',
                       'rows': [{'signal_week': '2026-06-19', 'weeks_ago': 0}], 'counts': {}}
        web._state['error'] = 'offline'
        self.assertEqual(web.snapshot()['report']['rows'], [])


class User(UserMixin):
    id = '1'
    firstName = 'Test'


class PageTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__, template_folder=str(ROOT / 'templates'), static_folder=str(ROOT / 'static'))
        app.config.update(TESTING=True, SECRET_KEY='test')
        CSRFProtect(app)
        manager = LoginManager(app)
        manager.user_loader(lambda identity: User())
        app.register_blueprint(web.ema_weekly)
        self.client = app.test_client()

    def login(self):
        with self.client.session_transaction() as session:
            session['_user_id'] = '1'
            session['_fresh'] = True

    def test_requires_login(self):
        self.assertEqual(self.client.get('/ema-weekly').status_code, 401)
        self.assertEqual(self.client.get('/ema-weekly/data').status_code, 401)

    def test_page_renders_and_data_returns_json(self):
        self.login()
        response = self.client.get('/ema-weekly')
        self.assertEqual(response.status_code, 200)
        self.assertIn('2 minggu terakhir', response.get_data(as_text=True))
        with patch.object(web, 'snapshot', return_value={'running': True, 'report': None}):
            self.assertTrue(self.client.get('/ema-weekly/data').json['running'])

    def test_refresh_requires_csrf(self):
        self.login()
        self.assertEqual(self.client.post('/ema-weekly/refresh').status_code, 400)

    def test_refresh_with_csrf(self):
        self.login()
        page = self.client.get('/ema-weekly').get_data(as_text=True)
        token = re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)
        with patch.object(web, 'snapshot', return_value={'running': True}) as snapshot:
            response = self.client.post('/ema-weekly/refresh', headers={'X-CSRFToken': token})
            self.assertEqual(response.status_code, 200)
            snapshot.assert_called_once_with(refresh=True)


if __name__ == '__main__':
    unittest.main()
