"""Daily StockLang report for the phone (stocklang_laporan): composed, saved, read back for Sync."""
import os
import tempfile
import unittest

import stocklang_laporan as lap

RINGKAS = [
    {'skrip': 'akumulasi', 'status': 'dicatat', 'tanggal': '2026-10-26', 'jumlah': 2},
    {'skrip': 'kosong', 'status': 'dicatat', 'tanggal': '2026-10-26', 'jumlah': 0},
    {'skrip': 'rusak', 'status': "error: unknown name 'clsoe'"},
]
NILAI = {'data_sampai': '2026-10-26', 'skrip': [
    {'skrip': 'akumulasi', 'versi': 'ab12cd34', 'status': 'aktif', 'terakhir': '2026-10-26', 'hari': 12,
     'kode_terakhir': ['PTRO', 'RANS'],
     'horizon': {'1': {'matang': 40, 'rata': -0.31, 'win': 45.0, 'lebih': 0.2}, '5': {'matang': 0}, '20': {'matang': 0}}},
    {'skrip': 'kosong', 'versi': 'ffff0000', 'status': 'aktif', 'terakhir': '2026-10-26', 'hari': 3,
     'kode_terakhir': [], 'horizon': {'1': {'matang': 0}, '5': {'matang': 0}, '20': {'matang': 0}}},
]}


class TestLaporan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved = (lap.LAPORAN_FILE, lap.jurnal.catat, lap.jurnal.evaluasi)
        lap.LAPORAN_FILE = os.path.join(self.tmp, 'laporan.json')
        lap.jurnal.catat = lambda: RINGKAS
        lap.jurnal.evaluasi = lambda: NILAI

    def tearDown(self):
        lap.LAPORAN_FILE, lap.jurnal.catat, lap.jurnal.evaluasi = self._saved

    def test_report_contents(self):
        r = lap.susun(RINGKAS, NILAI)
        self.assertEqual(r['as_of'], '2026-10-26')
        s = {x['nama']: x for x in r['skrip']}
        self.assertEqual(s['akumulasi']['lolos'], ['PTRO', 'RANS'])
        self.assertEqual(s['akumulasi']['horizon']['1']['matang'], 40)
        self.assertEqual(s['kosong']['lolos'], [])
        self.assertEqual((s['rusak']['status'], s['rusak']['pesan']), ('error', "error: unknown name 'clsoe'"))

    def test_saved_then_read_back_for_sync(self):
        self.assertEqual(lap.baca()['available'], False)          # nothing saved yet
        self.assertIn('2 saham lolos', lap.simpan())
        back = lap.baca()
        self.assertTrue(back['available'])
        self.assertEqual(back['skrip'][0]['lolos'], ['PTRO', 'RANS'])

    def test_no_journal_scripts(self):
        lap.jurnal.catat = lambda: []
        self.assertIn('Belum ada skrip', lap.simpan())
        self.assertFalse(lap.baca()['available'])
