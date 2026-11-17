import importlib
import ast
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import pandas as pd
from flask import Blueprint, Flask, render_template, request
from flask_login import LoginManager, login_required
import werkzeug
from importlib.metadata import version

if not hasattr(werkzeug, '__version__'):
    werkzeug.__version__ = version('werkzeug')

ROOT = Path(__file__).resolve().parent.parent
package = types.ModuleType('_kb_tests')
package.__path__ = [str(ROOT)]
sys.modules['_kb_tests'] = package
core = importlib.import_module('_kb_tests.broker_consistency')
bt = importlib.import_module('_kb_tests.broker_consistency_backtest')


class ConsistencyTests(unittest.TestCase):
    def test_ranking_counts_then_latest_streak_then_signed_total(self):
        days = list('abcde')
        daily = {d: {'AA': 1, 'BB': 100, 'CC': -10, 'DD': 10000} for d in days}
        daily['a']['BB'] = -1000
        daily['d']['DD'] = -100
        r = core.rank_days(days, daily)
        self.assertEqual([x['broker'] for x in r['buy']], ['AA', 'BB', 'DD'])
        self.assertEqual(r['buy'][1]['days'], 4)
        self.assertLess(r['buy'][1]['net_lot'], 0)  # majority days != net position
        self.assertEqual(r['sell'][0]['broker'], 'CC')

    def test_missing_is_not_zero_or_a_continuing_streak(self):
        r = core.rank_days(['a', 'b', 'c'], {'a': {'AA': 2}, 'b': None, 'c': {}})
        self.assertEqual(r['buy'][0]['values'], [2, None, None])
        self.assertEqual(r['buy'][0]['streak'], 0)

    def test_recent_sessions_do_not_backfill_missing_stock(self):
        with tempfile.TemporaryDirectory() as directory:
            for day in pd.bdate_range('2026-01-05', periods=6):
                folder = Path(directory, str(day.date()))
                folder.mkdir()
                if day.day == 8:
                    continue
                row = {'netbs_broker_code': 'AA', 'blot': '10'}
                data = {'data': {'broker_summary': {'brokers_buy': [row], 'brokers_sell': [
                    {'netbs_broker_code': 'AA', 'slot': '-4'}]}}}
                Path(folder, 'ADRO_ALL_%s.json' % day.date()).write_text(json.dumps(data))
                Path(folder, 'ADRO.xls').write_text('duplicate should not be read')
            r = core.build('adro', directory)
            self.assertEqual(r['dates'][0], '2026-01-06')
            self.assertEqual(r['missing'], ['2026-01-08'])
            self.assertEqual(r['buy'][0]['values'], [6, 6, None, 6, 6])
            self.assertEqual(r['buy'][0]['net_lot'], 24)

    def test_invalid_stock(self):
        for stock in ('../x', 'ADRO/../../', 'ABCDE', ''):
            with self.assertRaises(ValueError):
                core.build(stock)

    def test_source_date_mismatch_is_not_used(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory, '2026-01-05')
            folder.mkdir()
            path = folder / 'ADRO_ALL_2026-01-05.json'
            path.write_text(json.dumps({'data': {'broker_summary': {'brokers_buy': [
                {'netbs_broker_code': 'AA', 'netbs_date': '20260102', 'blot': 100}]}}}))
            r = core.build('ADRO', directory)
            self.assertEqual(r['available_days'], 0)
            self.assertEqual(r['buy'], [])

    def test_backtest_next_open_and_purged_boundary(self):
        dates = pd.bdate_range('2026-01-01', periods=40)
        daily = {str(d.date()): {'AA': 10} for d in dates}
        prices = pd.DataFrame({'Open': 100., 'Close': 120.}, index=dates)
        r = bt.calculate(dates, daily, prices)
        row = next(x for x in r['rows'] if x['period'] == 'Awal 70%' and x['horizon'] == 5)
        self.assertEqual(row['signal'], 'buy')
        self.assertEqual(row['n'], 19)  # t=4..22; exit t+5 must be before split=28
        self.assertAlmostEqual(row['mean'], 20.)  # close(T) entry would incorrectly yield 0
        daily.pop(str(dates[10].date()))
        r = bt.calculate(dates, daily, prices)
        row = next(x for x in r['rows'] if x['period'] == 'Awal 70%' and x['horizon'] == 5)
        self.assertEqual(row['n'], 14)

    def test_backtest_future_brokers_do_not_change_early_signals(self):
        dates = pd.bdate_range('2026-01-01', periods=40)
        daily = {str(d.date()): {'AA': 10} for d in dates}
        prices = pd.DataFrame({'Open': 100., 'Close': 120.}, index=dates)
        before = bt.calculate(dates, daily, prices)
        for d in dates[28:]:
            daily[str(d.date())] = {'AA': -10, 'BB': -20}
        after = bt.calculate(dates, daily, prices)
        self.assertEqual([x for x in before['rows'] if x['period'] == 'Awal 70%'],
                         [x for x in after['rows'] if x['period'] == 'Awal 70%'])

    def test_page_renders_actual_base_and_backtest(self):
        app = Flask(__name__, template_folder=str(ROOT / 'templates'), static_folder=str(ROOT / 'static'))
        app.config['SECRET_KEY'] = 'test'
        app.jinja_env.globals['csrf_token'] = lambda: 'test'
        app.add_url_rule('/logout', endpoint='auth.logout', view_func=lambda: '')
        app.add_url_rule('/login', endpoint='auth.login', view_func=lambda: '')
        app.add_url_rule('/signup', endpoint='auth.sign_up', view_func=lambda: '')
        report = dict(stock='ADRO', dates=['2026-11-13'], missing=[], available_days=1,
                      **core.rank_days(['2026-11-13'], {'2026-11-13': {'AA': 10}}))
        with app.test_request_context('/'):
            html = render_template('konsistensi_broker.html', stock='ADRO', report=report,
                                   error=None, user=types.SimpleNamespace(is_authenticated=True, firstName='Test'),
                                   all_stocks=['ADRO'], backtest={'error': 'Test empty history'})
        self.assertIn('Top 5 konsisten net beli', html)
        self.assertIn('+10', html)
        self.assertIn('Test empty history', html)

    def test_actual_route_login_validation_and_backtest(self):
        # Compile the actual route independently of unrelated heavy view imports.
        tree = ast.parse((ROOT / 'views.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'konsistensiBroker')
        blueprint = Blueprint('views', __name__)
        scope = dict(__package__='_kb_tests', views=blueprint, login_required=login_required,
                     request=request, render_template=lambda name, **ctx: {'stock': ctx['stock'],
                     'error': ctx.get('error'), 'backtest': ctx.get('backtest')}, current_user=None)
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'views.py', 'exec'), scope)
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY='test')
        manager = LoginManager(app)
        manager.user_loader(lambda identity: None)
        app.register_blueprint(blueprint)
        with app.test_client() as client:
            self.assertEqual(client.get('/konsistensi-broker').status_code, 401)
            app.config['LOGIN_DISABLED'] = True
            self.assertEqual(client.get('/konsistensi-broker?stock=../x').status_code, 400)
            with patch.object(core, 'build', return_value={'stock': 'ADRO'}), patch.object(bt, 'build', return_value={'rows': []}):
                response = client.get('/konsistensi-broker?stock=adro&backtest=1')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['stock'], 'ADRO')
            self.assertEqual(response.json['backtest'], {'rows': []})

    def test_bootstrap_and_zero_volume_exclusion(self):
        self.assertIsNone(bt.comparison([1, 2, 3], [True]*3, [False]*3, 5))
        c = bt.comparison([1, -1]*20, [True, False]*20, [False, True]*20, 5)
        self.assertAlmostEqual(c['spread'], 2.)
        self.assertAlmostEqual(c['low'], 2.)
        dates = pd.bdate_range('2026-01-01', periods=40)
        daily = {str(d.date()): {'AA': 10} for d in dates}
        prices = pd.DataFrame({'Open': 100., 'Close': 120., 'Volume': 0.}, index=dates)
        self.assertEqual(bt.calculate(dates, daily, prices)['rows'], [])


if __name__ == '__main__':
    unittest.main()
