import importlib.util
import sys
import types
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
import json

pkg=types.ModuleType('_rotasi_tests');pkg.__path__=[str(Path(__file__).parent)];sys.modules['_rotasi_tests']=pkg
spec=importlib.util.spec_from_file_location('_rotasi_tests.rotasi_sektor',Path(__file__).with_name('rotasi_sektor.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class RotationTests(unittest.TestCase):
    def panel(self):
        dates=pd.bdate_range('2026-09-01',periods=26)
        close=pd.DataFrame({'AAA':100*1.01**np.arange(26),'BBB':np.full(26,100.),'CCC':100*.99**np.arange(26)},index=dates)
        vol=pd.DataFrame(1000.,index=dates,columns=close.columns)
        return close,vol,{'AAA':'A','BBB':'A','CCC':'B'}

    def test_returns_breadth_and_shares(self):
        c,v,s=self.panel();out=r.calculate(c,v,s);a=next(x for x in out['rows'] if x['sektor']=='A')
        self.assertAlmostEqual(a['r5'],((1.01**5-1)*100)/2)
        self.assertEqual(a['breadth'],50);self.assertEqual(a['tetap'],1)
        self.assertAlmostEqual(sum(x['porsi'] for x in out['rows']),100)
        self.assertAlmostEqual(sum(x['perubahan_porsi'] for x in out['rows']),0)
        expected=(c[['AAA','BBB']]*v[['AAA','BBB']]).tail(5).mean().sum()/(c[['AAA','BBB']]*v[['AAA','BBB']]).iloc[:21].tail(20).mean().sum()
        self.assertAlmostEqual(a['aktivitas'],expected)
        json.dumps(out,allow_nan=False)

    def test_missing_prices_not_forward_filled(self):
        c,v,s=self.panel();c.loc[c.index[-1],'AAA']=np.nan
        out=r.calculate(c,v,s);self.assertEqual(out['n_saham'],2)
        self.assertNotIn('AAA',[x['ticker'] for row in out['rows'] for x in row['saham']])

    def test_unmapped_and_inactive_excluded(self):
        c,v,s=self.panel();s.pop('AAA');v.loc[v.index[:3],'BBB']=0
        out=r.calculate(c,v,s);self.assertEqual(out['n_saham'],1);self.assertEqual(out['n_tanpa_sektor'],1)
        self.assertEqual(out['rows'][0]['sektor'],'B')

    def test_not_enough_history_and_empty(self):
        c,v,s=self.panel();self.assertFalse(r.calculate(c.tail(20),v,s)['available'])
        self.assertFalse(r.calculate(pd.DataFrame(),pd.DataFrame(),{})['available'])

if __name__=='__main__':unittest.main()
