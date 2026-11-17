"""Authorization and configuration regressions using a fresh synthetic database."""
from datetime import date
import hashlib
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash, check_password_hash
from website import create_app, db
from website.models import User, Position, CashBalance, BestStocks, DecisionSnapshot
from website.runtime_paths import runtime_file, MARKET_DIR, RUNTIME_DIR, PROJECT_DIR, market_file


class AccountSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(test_config={
            'TESTING': True, 'SECRET_KEY': 'synthetic-fixture-session-key-only',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False, 'DREAM_AGENT_WORKER_ENABLED': False,
        })
        self.context = self.app.app_context()
        self.context.push()
        password = generate_password_hash('synthetic-account-passphrase')
        self.alice = User(email='alice@example.invalid', firstName='Alice', password=password)
        self.bob = User(email='bob@example.invalid', firstName='Bob', password=password)
        db.session.add_all([self.alice, self.bob]); db.session.flush()
        self.aid, self.bid = self.alice.id, self.bob.id
        db.session.add_all([CashBalance(amount=500000, userId=self.aid),
                            CashBalance(amount=900000, userId=self.bid),
                            CashBalance(amount=777, userId=None)])
        self.position = Position(stock='TEST', buyPrice=100, lots=1, buyDate=date(2026, 1, 2), userId=self.aid)
        self.other = Position(stock='TEST', buyPrice=200, lots=2, buyDate=date(2026, 1, 2), userId=self.bid)
        db.session.add_all([self.position, self.other]); db.session.commit()
        self.pid, self.other_id = self.position.id, self.other.id
        self.client = self.app.test_client()
        self.login_as(self.aid)

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.context.pop()

    def login_as(self, identity):
        with self.client.session_transaction() as session:
            session.clear(); session['_user_id'] = str(identity); session['_fresh'] = True

    def balance(self, owner):
        db.session.expire_all()
        return CashBalance.query.filter_by(userId=owner).one().amount

    def test_other_account_positions_cannot_be_edited_closed_or_deleted(self):
        for endpoint in ['edit', 'close', 'delete']:
            response = self.client.post('/pnl/'+endpoint, data={
                'id':self.other_id, 'stock':'TEST', 'buyPrice':10, 'lots':1, 'sellPrice':300,
            })
            self.assertEqual(response.status_code, 404, endpoint)
            self.assertEqual(self.balance(self.aid), 500000)
            self.assertEqual(self.balance(self.bid), 900000)
            self.assertEqual(db.session.get(Position, self.other_id).lots, 2)

    def test_portfolio_page_and_cash_are_scoped_to_account(self):
        def render(_name, **context):
            return {'ids':[row['id'] for row in context['rows']], 'cash':context['cashAmount']}
        with patch('website.views.render_template', side_effect=render), \
             patch('website.views.compute_cumulative_flow', return_value=None), \
             patch('website.views.flow_check', return_value={'available':False}):
            response = self.client.get('/pnl')
        self.assertEqual(response.json, {'ids':[self.pid], 'cash':500000})
        self.assertEqual(self.client.post('/pnl/cash', data={'amount':1234}).status_code, 200)
        self.assertEqual(self.balance(self.aid), 1234)
        self.assertEqual(self.balance(self.bid), 900000)
        self.assertEqual(CashBalance.query.filter_by(userId=None).one().amount, 777)

    def test_nonfinite_values_and_overflow_do_not_change_database(self):
        for value in ['nan', 'NaN', 'inf', '-inf', '1e999', '', 'invalid']:
            self.assertEqual(self.client.post('/pnl/cash', data={'amount':value}).status_code, 400)
            for field in ['buyPrice', 'lots']:
                payload={'stock':'TEST', 'buyPrice':'100', 'lots':'1', field:value}
                self.assertEqual(self.client.post('/pnl/add', data=payload).status_code,400)
            self.assertEqual(self.client.post('/pnl/close', data={'id':self.pid, 'sellPrice':value}).status_code,400)
            if value != '':  # A blank optional sellLot intentionally means the full position.
                self.assertEqual(self.client.post('/pnl/close', data={'id':self.pid, 'sellPrice':'100', 'sellLot':value}).status_code,400)
        self.assertEqual(self.client.post('/pnl/add',data={'stock':'TEST','buyPrice':'1e308','lots':'1e308'}).status_code,400)
        self.assertEqual(self.balance(self.aid),500000)
        self.assertEqual(Position.query.count(),2)
        self.assertIsNone(db.session.get(Position,self.pid).sellDate)

    def test_own_edit_and_partial_close_preserve_cash_and_owner(self):
        response=self.client.post('/pnl/edit', data={'id':self.pid,'stock':'TEST','buyPrice':120,'lots':1})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.balance(self.aid),498000)
        response=self.client.post('/pnl/close',data={'id':self.pid,'sellPrice':150,'sellLot':'.4','sellDate':'2026-02-02'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.balance(self.aid),504000)
        own=Position.query.filter_by(userId=self.aid).all()
        self.assertEqual(len(own),2)
        self.assertAlmostEqual(sum(p.lots for p in own),1)
        self.assertAlmostEqual(next(p.lots for p in own if p.sellDate),.4)
        self.assertEqual(self.balance(self.bid),900000)

    def test_account_without_cash_does_not_adopt_legacy_or_other_balance(self):
        db.session.delete(CashBalance.query.filter_by(userId=self.aid).one())
        db.session.commit()
        response=self.client.post('/pnl/cash', data={'amount':55})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.balance(self.aid),55)
        self.assertEqual(self.balance(self.bid),900000)
        self.assertEqual(CashBalance.query.filter_by(userId=None).one().amount,777)

    def test_anonymous_portfolio_changes_require_login(self):
        with self.client.session_transaction() as session:session.clear()
        self.assertEqual(self.client.post('/pnl/delete',data={'id':self.pid}).status_code,302)
        self.assertEqual(Position.query.count(),2)

    def test_personal_watchlists_cannot_be_read_or_deleted_across_accounts(self):
        db.session.add_all([BestStocks(data='AAAA',userId=self.aid), BestStocks(data='BBBB',userId=self.bid)])
        db.session.commit()
        response=self.client.get('/watchlist-tickers?type=BestStocks')
        self.assertEqual(response.json,{'tickers':['AAAA']})
        self.client.post('/admin?param=delete&type=BestStocks&stock=BBBB')
        self.assertEqual(BestStocks.query.filter_by(userId=self.bid).count(),1)
        response=self.client.post('/admin?param=delete&type=RetailSellStocks&stock=BBBB')
        self.assertEqual(response.status_code,403)

    def test_personal_decision_journal_is_scoped_to_owner(self):
        db.session.add_all([DecisionSnapshot(stock='AAAA',reason='watchlist_add',userId=self.aid),
                            DecisionSnapshot(stock='BBBB',reason='watchlist_add',userId=self.bid),
                            DecisionSnapshot(stock='CCCC',reason='watchlist_add',userId=None)])
        db.session.commit()
        from website.decision_journal import journal_entries
        from flask_login import login_user
        with self.app.test_request_context('/'):
            login_user(self.alice)
            with patch('website.decision_journal.load_summary',return_value=None):
                records=journal_entries()
        self.assertEqual([r['stock'] for r in records],['AAAA'])

    def test_empty_authentication_forms_do_not_raise_or_create_accounts(self):
        for payload in [{}, {'email':'bad','firstName':'X'}, {'email':'x@example.invalid','firstName':'X'}]:
            response=self.client.post('/sign-up', data=payload)
            self.assertEqual(response.status_code,200)
        self.assertEqual(User.query.count(),2)
        self.assertEqual(self.client.post('/login',data={}).status_code,200)

    def test_invalid_login_messages_do_not_disclose_account_existence(self):
        for email in ['alice@example.invalid','missing@example.invalid']:
            response=self.client.post('/login',data={'email':email,'password':'wrong'})
            self.assertIn(b'Invalid email or password',response.data)
            self.assertNotIn(b'Email does not exist',response.data)

    def test_legacy_password_migrates_and_unknown_digest_is_rejected(self):
        from website.auth import verify_password
        salt='fixture-salt';password='legacy-fixture-pass'
        self.alice.password='sha256$'+salt+'$'+hashlib.sha256((salt+password).encode()).hexdigest()
        db.session.commit()
        self.assertTrue(verify_password(self.alice,password))
        self.assertTrue(check_password_hash(self.alice.password,password))
        self.assertFalse(self.alice.password.startswith('sha256$'))
        self.alice.password='md5$fixture$'+hashlib.md5(b'fixturepass').hexdigest()
        self.assertFalse(verify_password(self.alice,'pass'))

    def test_logout_requires_post_and_csrf(self):
        self.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.client.get('/logout').status_code,405)
        self.assertEqual(self.client.post('/logout').status_code,400)
        page=self.client.get('/login')
        token=re.search(rb'name="csrf_token"[^>]*value="([^"]+)"',page.data).group(1).decode()
        self.assertEqual(self.client.post('/logout',data={'csrf_token':token}).status_code,302)
        with self.client.session_transaction() as session:self.assertNotIn('_user_id',session)


class ConfigurationTests(unittest.TestCase):
    def test_database_cannot_be_created_inside_source_code(self):
        path=PROJECT_DIR/'must-not-exist.sqlite'
        with self.assertRaisesRegex(ValueError,'outside'):
            create_app(test_config={'TESTING':True,'SECRET_KEY':'fixture-only',
                'SQLALCHEMY_DATABASE_URI':'sqlite:///'+path.as_posix()})
        self.assertFalse(path.exists())

    def test_normal_startup_rejects_missing_and_short_session_secret(self):
        for value in ['', 'short']:
            with patch.dict(os.environ, {'SECRET_KEY':value}):
                with self.assertRaisesRegex(ValueError,'SECRET_KEY'):
                    create_app()

    def test_artifacts_and_input_paths_are_external_and_contained(self):
        for name in ['live_scan_cache_90.pkl','best_stock_pattern_model.keras','insider_jurnal.csv','ramai_dibahas_telegram.session']:
            path=runtime_file('',name)
            self.assertTrue(path.is_relative_to(RUNTIME_DIR))
            self.assertFalse(path.is_relative_to(PROJECT_DIR))
        for name in ['../escape','/absolute','C:/private']:
            with self.assertRaises(ValueError):runtime_file('',name)
        with self.assertRaises(ValueError):market_file('../escape')

    def test_legacy_cash_schema_is_migrated_without_assigning_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.sqlite'
            with sqlite3.connect(path) as connection:
                connection.execute('CREATE TABLE cash_balance (id INTEGER PRIMARY KEY, amount FLOAT)')
                connection.execute('INSERT INTO cash_balance VALUES (1, 789)')
            connection.close()
            app=create_app(test_config={'TESTING':True,'SECRET_KEY':'fixture-only',
                'SQLALCHEMY_DATABASE_URI':'sqlite:///'+path.as_posix(),'DREAM_AGENT_WORKER_ENABLED':False})
            with app.app_context():
                old=CashBalance.query.one()
                self.assertIsNone(old.userId)
                self.assertEqual(old.amount,789)
                db.session.remove();db.engine.dispose()


if __name__=='__main__':
    unittest.main()
