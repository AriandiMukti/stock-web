"""Run local fixture tests with private-data access and network connections blocked."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
_test_directory = tempfile.TemporaryDirectory(prefix='flask-fixtures-')
os.environ['FLASK_RUNTIME_DIR'] = str(Path(_test_directory.name) / 'runtime')
os.environ['BDM_BASE_PATH'] = str(Path(_test_directory.name) / 'market')
os.environ['DREAM_AGENT_WORKER_ENABLED'] = '0'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))


def guard(event, args):
    if event == 'socket.connect':
        raise PermissionError('Network connections are disabled in fixture tests')
    if event in {'open', 'sqlite3.connect'} and args and isinstance(args[0], (str, bytes)):
        raw = os.fsdecode(args[0]).replace('\\', '/').lower()
        private = str(ROOT.parent / 'private-data').replace('\\', '/').lower()
        if '/program/flask/' in raw or raw.startswith(private + '/'):
            raise PermissionError('Private/original project files are disabled in fixture tests')


sys.addaudithook(guard)
loader = unittest.TestLoader()
suite = loader.discover(str(ROOT/'website/tests'), pattern='test_*.py')
sys.path.insert(0, str(ROOT/'website'))
for module in ['test_market_agenda', 'test_rotasi_sektor']:
    suite.addTests(loader.loadTestsFromName(module))
result = unittest.TextTestRunner(verbosity=2).run(suite)
_test_directory.cleanup()
raise SystemExit(0 if result.wasSuccessful() else 1)
