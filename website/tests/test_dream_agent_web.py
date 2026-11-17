import importlib
import json
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest

from flask import Flask
from flask_login import LoginManager, UserMixin
from flask_wtf import CSRFProtect
import werkzeug
from importlib.metadata import version

# Flask 2.2 test client reads metadata removed in Werkzeug 3; test-only shim.
if not hasattr(werkzeug, '__version__'):
    werkzeug.__version__ = version('werkzeug')

ROOT = Path(__file__).resolve().parent.parent
# Load the actual blueprint without the unrelated market-analysis imports/startup jobs.
package = types.ModuleType('integration_fixture')
package.__path__ = [str(ROOT)]
sys.modules['integration_fixture'] = package
web = importlib.import_module('integration_fixture.dream_agent_web')


class User(UserMixin):
    def __init__(self, identity):
        self.id = identity
        self.firstName = 'Test'


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'))
        self.app.config.update(TESTING=True, SECRET_KEY='test-only', DREAM_AGENT_DATA_DIR=self.tmp.name)
        CSRFProtect(self.app)
        manager = LoginManager(self.app)
        manager.user_loader(lambda identity: User(identity))
        self.app.register_blueprint(web.dream_agent_web)
        self.client = self.app.test_client()
        self.login('1')
        self.case = (ROOT / 'dream_agent/examples/adro_synthetic.json').read_text(encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, identity):
        with self.client.session_transaction() as session:
            session.clear()
            session['_user_id'] = identity
            session['_fresh'] = True

    def post(self, **data):
        page = self.client.get('/dream-agent/')
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True)).group(1)
        return self.client.post('/dream-agent/', data=dict(csrf_token=token, **data), follow_redirects=True)

    def snapshot(self):
        with self.app.test_request_context():
            from flask_login import login_user
            login_user(User('1'))
            store = web.user_store()
            try:
                return store.active(), store.runs(), store.proposals(), store.verify()
            finally:
                store.close()

    def test_automatic_controls_and_status(self):
        self.post(action='start', goal='Background', dataset=self.case, interval=30, dream_interval=60)
        self.assertEqual(self.client.get('/dream-agent/status').json['status'], 'running')
        for action, expected in [('pause', 'paused'), ('resume', 'running'), ('stop', 'stopped')]:
            self.post(action=action)
            self.assertEqual(self.client.get('/dream-agent/status').json['status'], expected)
        self.login('2')
        self.assertEqual(self.client.get('/dream-agent/status').json['status'], 'stopped')

    def test_page_uses_existing_navigation(self):
        result = self.client.get('/dream-agent/')
        self.assertEqual(result.status_code, 200)
        self.assertIn(b'Dream Agent', result.data)
        self.assertIn(b'/research', result.data)

    def test_login_and_csrf_required(self):
        self.assertEqual(self.client.post('/dream-agent/', data={'action':'dream'}).status_code, 400)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get('/dream-agent/').status_code, 401)

    def test_full_workflow(self):
        self.assertEqual(self.post(action='run', goal='Riset', dataset=self.case).status_code, 200)
        self.post(action='dream')
        self.assertEqual(self.snapshot()[0][0], 1)
        self.post(action='approve', id=1, reason='Reviewed')
        self.post(action='run', goal='Riset', dataset=self.case)
        active, runs, proposals, valid = self.snapshot()
        self.assertEqual(active[0], 2)
        self.assertEqual(runs[-1]['evaluation']['score'], 1)
        self.assertTrue(valid)
        self.post(action='rollback', id=1, reason='Restore')
        self.assertEqual(self.snapshot()[0][1]['checks'], [])

    def test_invalid_inputs_and_blank_reason(self):
        for dataset in ('[]', '{}', 'null', '{broken', 'x' * 100001):
            self.assertEqual(self.post(action='run', goal='Riset', dataset=dataset).status_code, 200)
        self.assertEqual(self.snapshot()[1], [])
        self.post(action='run', goal='Riset', dataset=self.case)
        self.post(action='dream')
        self.post(action='approve', id=1, reason='')
        self.assertEqual(self.snapshot()[0][0], 1)

    def test_user_data_isolation(self):
        self.post(action='run', goal='PRIVATE_GOAL', dataset=self.case)
        self.post(action='dream')
        self.login('2')
        self.assertNotIn(b'PRIVATE_GOAL', self.client.get('/dream-agent/').data)
        self.post(action='approve', id=1, reason='Other user')
        self.assertEqual(self.snapshot()[0][0], 1)

    def test_untrusted_text_is_escaped(self):
        self.post(action='run', goal='<script>alert(1)</script>', dataset=self.case)
        page = self.client.get('/dream-agent/').get_data(as_text=True)
        self.assertNotIn('<script>alert(1)</script>', page)

    def test_reject_and_stale_proposal(self):
        self.post(action='run', goal='Riset', dataset=self.case)
        self.post(action='dream')
        self.post(action='reject', id=1, reason='No')
        self.assertEqual(self.snapshot()[2][0]['status'], 'rejected')
        self.post(action='dream')
        self.post(action='rollback', id=1, reason='Restore')
        self.post(action='approve', id=2, reason='Stale')
        self.assertEqual(self.snapshot()[0][1]['checks'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
