"""
Laporan harian StockLang untuk HP: saham yang lolos screen() tiap skrip
berjurnal hari ini, nilai jurnalnya sejauh ini (H+1/H+5/H+20), dan skrip
yang error.

Dijalankan kesehatan.py SESUDAH stocklang_jurnal (induknya), jadi yang
dilaporkan sama dengan yang baru dicatat. Hasilnya disimpan ke
stocklang_laporan.json; /stocklang/laporan-data menyajikannya, dan
ekspor_hp.py memasukkannya ke data Sinkron sebagai menu 'stocklang' --
sampai ke HP lewat tombol Sync yang sama dengan data lain.

    python -X utf8 -m website.stocklang_laporan          # susun + simpan
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import json
import os
from datetime import datetime

try:
    from . import stocklang_jurnal as jurnal
except ImportError:
    import stocklang_jurnal as jurnal

HERE = os.path.dirname(os.path.abspath(__file__))
LAPORAN_FILE = str(_runtime_file('', 'stocklang_laporan.json'))


def susun(ringkas, nilai):
    """ringkas: hasil jurnal.catat(); nilai: hasil jurnal.evaluasi(). Return dict laporan."""
    if not ringkas:
        return {'available': False, 'message': 'Belum ada skrip StockLang yang dicentang Jurnal harian.'}
    as_of = max((r['tanggal'] for r in ringkas if r.get('tanggal')), default=None) or nilai.get('data_sampai')
    per_skrip = {s['skrip']: s for s in nilai.get('skrip', []) if s['status'] == 'aktif'}
    skrip = []
    for r in ringkas:
        s = per_skrip.get(r['skrip'])
        gagal = r['status'].startswith('error') or r['status'] == 'tanpa screen()'
        skrip.append({
            'nama': r['skrip'],
            'status': 'error' if gagal else 'ok',
            'pesan': r['status'] if gagal else '',
            'versi': s['versi'] if s else None,
            'lolos': s['kode_terakhir'] if s and not gagal and s['terakhir'] == r.get('tanggal') else [],
            'horizon': s['horizon'] if s else {},
            'hari': s['hari'] if s else 0,
        })
    return {'available': True, 'as_of': as_of, 'dibuat': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'skrip': skrip}


def simpan():
    """Susun laporan hari ini dan simpan untuk Sinkron. Return ringkasan singkat."""
    lap = susun(jurnal.catat(), jurnal.evaluasi())
    tmp = LAPORAN_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(lap, f, indent=1, ensure_ascii=False)
    os.replace(tmp, LAPORAN_FILE)
    if not lap['available']:
        return lap['message']
    return 'laporan %s: %d skrip, %d saham lolos' % (
        lap['as_of'], len(lap['skrip']), sum(len(s['lolos']) for s in lap['skrip']))


def baca():
    """Laporan tersimpan terakhir, untuk /stocklang/laporan-data (dan dari situ ekspor HP)."""
    try:
        with open(LAPORAN_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'available': False, 'message': 'Laporan StockLang belum dibuat (jalan bersama pemeriksaan kesehatan harian).'}


if __name__ == '__main__':
    print(simpan())
