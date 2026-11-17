import unittest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path
import tempfile
import json
import agenda_pasar as a
import berita_global as b

class AgendaTests(unittest.TestCase):
    def test_indonesian_date(self):
        self.assertEqual(a.tanggal('Cum Dividen 12 November 2026'), '2026-11-12')
        self.assertIsNone(a.tanggal('Belum ditetapkan'))

    def test_wib_dst(self):
        self.assertEqual(datetime(2026,7,1,8,30,tzinfo=a.ET).astimezone(a.WIB).hour,19)
        self.assertEqual(datetime(2026,11,6,8,30,tzinfo=a.ET).astimezone(a.WIB).hour,20)

    def test_cached_failure_marked_old(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            now=datetime.now(a.WIB)
            e=a.event('Test',now.date().isoformat(),'Federal Reserve',a.FED)
            Path(folder,'agenda_kalender_cache.json').write_text(json.dumps({'per_sumber':{'Federal Reserve':[e]}}))
            with patch.object(a,'_runtime_file',side_effect=lambda directory,name:Path(folder)/name),patch.object(a,'fed',side_effect=RuntimeError()),patch.object(a,'bea',return_value=[]),patch.object(a,'macro',return_value=[]):
                r=a.scan('kalender',True)
            self.assertTrue(r['stale']);self.assertTrue(r['items'][0]['stale'])

    def test_summary_prefers_body_and_no_duplicates(self):
        base=dict(kategori='The Fed',terbit='2026-11-05',sumber='ANTARA',url='https://www.antaranews.com/a')
        r=b._rangkuman([dict(base,judul='The Fed menahan suku bunga - ANTARA',isi='Keputusan terbaru mempertahankan suku bunga.',metode='Petikan kalimat penting artikel'),dict(base,judul='The Fed menahan suku bunga - Sumber lain')])
        self.assertEqual(len(r),1);self.assertEqual(r[0]['ringkasan'],'Keputusan terbaru mempertahankan suku bunga.')

    def test_extract_filters_boilerplate(self):
        self.assertEqual(b._kalimat('Baca juga: berita terkait mengenai pasar keuangan dan bank sentral.'),[])

if __name__=='__main__':unittest.main()
