"""The preview database and every displayed quote are generated synthetically."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from website.demo import SYMBOLS, synthetic_summary


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temporary.name)/'demo'
        cls.code=Path(__file__).resolve().parents[2]
        cls.env=dict(os.environ,PYTHONPATH=str(cls.code),PYTHONDONTWRITEBYTECODE='1')
        result=subprocess.run([sys.executable,'-B','-m','website.demo','seed','--out',str(cls.root)],
                              cwd=cls.code,env=cls.env,capture_output=True,text=True,timeout=45)
        if result.returncode:raise RuntimeError(result.stderr)

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def test_prices_are_deterministic_and_ohlcv_valid(self):
        for symbol in SYMBOLS:
            frame=synthetic_summary(symbol)
            self.assertEqual(len(frame),80)
            self.assertTrue(frame.equals(synthetic_summary(symbol)))
            self.assertTrue(frame.Synthetic.all())
            self.assertTrue((frame.High>=frame[['Open','Close']].max(axis=1)).all())
            self.assertTrue((frame.Low<=frame[['Open','Close']].min(axis=1)).all())

    def test_database_has_three_owned_positions_and_never_overwrites(self):
        path=self.root/'var/databases/demo.sqlite'
        with sqlite3.connect(path) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM position').fetchone()[0],3)
            self.assertEqual(connection.execute('SELECT count(*) FROM "PortfolioStocks"').fetchone()[0],3)
            self.assertEqual(connection.execute('SELECT count(*) FROM user').fetchone()[0],1)
        connection.close()
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        result=subprocess.run([sys.executable,'-B','-m','website.demo','seed','--out',str(self.root)],
                              cwd=self.code,env=self.env,capture_output=True,text=True,timeout=15)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

    def test_seeded_login_portfolio_and_chart_are_visible_and_marked_synthetic(self):
        program=r'''
import json,re,sys
from pathlib import Path
from website.demo import _configure
root=Path(sys.argv[1]);config=json.loads((root/'demo-config.json').read_text())
login=(root/'demo-login.txt').read_text().splitlines()
password=next(x.removeprefix('Password: ') for x in login if x.startswith('Password: '))
_configure(root,config['secret_key'])
from website import create_app,db
app=create_app();app.config['TESTING']=True
assert app.config['DEMO_MODE'] is True
with app.test_client() as client:
 page=client.get('/login')
 token=re.search(rb'name="csrf_token"[^>]*value="([^"]+)"',page.data).group(1).decode()
 response=client.post('/login',data={'email':config['email'],'password':password,'csrf_token':token})
 assert response.status_code==302
 for path in ['/','/pnl','/display-stock-list?type=PortfolioStocks']:
  response=client.get(path)
  assert response.status_code==200,(path,response.status_code)
  assert b'DEMO SINTETIS' in response.data
  assert response.headers['X-Data-Provenance']=='synthetic-demo'
 for symbol in ['ADRO','BBRI','TLKM']:
  response=client.get('/stock-chart-data/'+symbol)
  assert response.status_code==200 and response.json['found'] is True,(symbol,response.status_code)
  assert response.headers['X-Data-Provenance']=='synthetic-demo'
with app.app_context():db.session.remove();db.engine.dispose()
print('Synthetic login, portfolio, watchlist and three stock chart APIs verified')
'''
        result=subprocess.run([sys.executable,'-B','-c',program,str(self.root)],cwd=self.code,
                              env=self.env,capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
