r"""
Ekspor data olahan ke satu file untuk aplikasi Android "BDM Saku".

HP tidak menghitung apa pun -- semua hitungan berat (cache .pkl, model,
Summary harian) tetap di laptop. Yang dikirim cuma hasil akhirnya: JSON
yang SAMA PERSIS dengan yang dipakai halaman web, diambil lewat endpoint
*-data yang sudah ada (pakai test client Flask), supaya angka di HP tidak
pernah beda tafsir dengan angka di web.

Hasil: website/hp/data/bdm_hp.json.gz (biasanya 1-3 MB). Dikirim ke HP
lewat WiFi oleh kirim_hp.py.

    python -X utf8 -m website.ekspor_hp      (dijalankan dari <project>/)
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import gzip
import json
import logging
import os
import sys
import time
from datetime import datetime

logger = logging.getLogger(__name__)

FOLDER_HP = str(_runtime_file('', 'hp', 'data'))
FILE_DATA = str(_runtime_file('hp/data', 'bdm_hp.json.gz'))
VERSI_FORMAT = 1

# Chart di HP cukup ~6 bulan terakhir: layar kecil, dan file tetap ringan.
BAR_CHART = 130

# (kunci di file, metode, endpoint) -- urutannya juga urutan tampil di log.
MENU = [
    ('perubahan_kepemilikan', 'POST', '/perubahan-kepemilikan-data'),
    ('musiman_saham', 'POST', '/musiman-saham-data'),
    ('rotasi_sektor', 'POST', '/rotasi-sektor-data'),
    ('kalender', 'POST', '/kalender-pasar-data'),
    ('agenda_emiten', 'POST', '/agenda-emiten-data'),
    ('kabar', 'POST', '/kabar-semalam-data'),
    ('tembus', 'POST', '/tembus-basis-data'),
    ('kecondongan', 'POST', '/skor-kecondongan-data'),
    ('rapat', 'POST', '/rapat-agen-data'),
    ('radar', 'POST', '/radar-insider-data'),
    ('ramai', 'POST', '/ramai-dibahas-data'),
    ('watchlist', 'GET', '/saham-watchlist-data'),
    ('digest', 'POST', '/watchlist-digest-data'),
    ('stocklang', 'GET', '/stocklang/laporan-data'),
]

# Bagian JSON yang cuma dipakai halaman "bukti"/pengaturan di web -- tidak
# ditampilkan di HP, jadi dibuang supaya file tidak membengkak.
BUANG = ('bukti', 'config', 'catat')

# Ramai Dibahas: cuma yang teratas yang dibuka detailnya; sisanya tetap ada
# di daftar menunya.
N_RAMAI_DETAIL = 30


def _app():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import werkzeug
    # Flask test client membaca werkzeug.__version__, yang sudah dihapus di
    # werkzeug versi terpasang -- sama seperti konfigurasi bdm-flask-nologin.
    werkzeug.__version__ = getattr(werkzeug, '__version__', '2.3.0')
    from flask_login import login_user
    from website import create_app
    from website.models import User

    app = create_app()
    app.config['WTF_CSRF_ENABLED'] = False
    app.before_request(lambda: login_user(User.query.first()) and None)
    return app


def _ambil(client, metode, url):
    r = client.open(url, method=metode)
    if r.status_code != 200:
        return {'available': False, 'message': 'HTTP %s' % r.status_code}
    try:
        return json.loads(r.get_data())
    except ValueError:
        return {'available': False, 'message': 'Bukan JSON'}


def _rampingkan_chart(c):
    """Potong chart ke BAR_CHART bar terakhir; garis kumulatif dihitung ulang
    dari hari pertama yang tampil, sama seperti aturan di stockChartData."""
    if not c or not c.get('found'):
        return None
    n = len(c.get('dates') or [])
    a = max(0, n - BAR_CHART)

    def potong(k):
        return (c.get(k) or [])[a:]

    def kumulatif(seri):
        total, hasil = 0, []
        for v in seri:
            total += v or 0
            hasil.append(total)
        return hasil

    return {
        'dates': potong('dates'), 'open': potong('open'), 'high': potong('high'),
        'low': potong('low'), 'close': potong('close'), 'volume': potong('volume'),
        'top5': kumulatif(potong('netTop5Lot')),
        'ritel': kumulatif(potong('retail')),
        'levels': c.get('levels') or [],
        'change': c.get('change'), 'lastClose': c.get('lastClose'), 'value': c.get('value'),
    }


def _ticker_menu(menu):
    """Semua emiten yang muncul di menu mana pun -- yang ini dibuatkan
    halaman detail (hub + chart). Urutan tidak penting."""
    t = set()
    for g in (menu['watchlist'].get('groups') or []):
        t.update(g.get('tickers') or [])
    t.update(b.get('stock') for b in (menu['tembus'].get('baris') or []))
    t.update(b.get('stock') for b in (menu['kecondongan'].get('atas') or []))
    t.update(b.get('stock') for b in (menu['kecondongan'].get('bawah') or []))
    t.update(b.get('stock') for b in (menu['rapat'].get('rows') or []))
    t.update(b.get('ticker') for b in (menu['radar'].get('beli') or []))
    t.update(b.get('ticker') for b in (menu['radar'].get('jual_peringatan') or []))
    t.update(b.get('stock') for b in (menu['kabar'].get('kena') or []))
    t.update(b.get('stock') for b in (menu['ramai'].get('baris') or [])[:N_RAMAI_DETAIL])
    for s in menu['stocklang'].get('skrip') or []:
        t.update(s.get('lolos') or [])
    return sorted(x for x in t if x)


def ekspor(cetak=print):
    mulai = time.time()
    app = _app()
    client = app.test_client()

    menu = {}
    for kunci, metode, url in MENU:
        t = time.time()
        d = _ambil(client, metode, url)
        d.pop('per_sumber', None)
        for b in BUANG:
            d.pop(b, None)
        # daily_diff = salinan isi baris itu sendiri untuk hari ini & kemarin
        # (dipakai web buat menandai yang berubah) -- separuh ukuran digest.
        for r in (d.get('rows') or []) if kunci == 'digest' else []:
            r.pop('daily_diff', None)
        if kunci == 'kabar':
            d.get('berita_global', {}).pop('raw_items', None)
        menu[kunci] = d
        cetak('  %-12s %s (%.1f dtk)' % (kunci, 'ok' if d.get('available') else
                                          'TIDAK ADA: %s' % d.get('message'), time.time() - t))

    tickers = _ticker_menu(menu)
    cetak('  detail %d emiten...' % len(tickers))
    saham = {}
    for tk in tickers:
        hub = _ambil(client, 'POST', '/saham-data/%s' % tk)
        chart = _rampingkan_chart(_ambil(client, 'GET', '/stock-chart-data/%s' % tk))
        if hub.get('available') or chart:
            saham[tk] = {'hub': hub if hub.get('available') else None, 'chart': chart}

    as_of = max((menu[k].get('as_of') or '' for k in menu), default='')
    paket = {
        'versi': VERSI_FORMAT,
        'dibuat': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'as_of': as_of,
        'menu': menu,
        'saham': saham,
    }

    os.makedirs(FOLDER_HP, exist_ok=True)
    mentah = json.dumps(paket, ensure_ascii=False, separators=(',', ':'), default=str).encode('utf-8')
    # Tulis ke file sementara lalu ganti nama: kalau HP sedang mengunduh
    # saat ekspor berjalan, ia tetap dapat file lama yang utuh.
    sementara = FILE_DATA + '.tmp'
    with gzip.open(sementara, 'wb', compresslevel=9) as f:
        f.write(mentah)
    os.replace(sementara, FILE_DATA)

    cetak('Selesai: %d emiten, %.1f MB -> %.1f MB terkompres, %.0f dtk' % (
        len(saham), len(mentah) / 1e6, os.path.getsize(FILE_DATA) / 1e6, time.time() - mulai))
    return FILE_DATA


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    ekspor()
