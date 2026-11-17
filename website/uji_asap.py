"""
Uji asap: tembak seluruh halaman & endpoint, pastikan tidak rusak dan tidak lambat.

KENAPA MODUL INI ADA

Dalam satu hari kerja, lima kerusakan lolos ke pemakaian -- dan tidak satu
pun ditemukan oleh sistem:

    /display-stock-list?type=<salah>   -> 500   ketemu tidak sengaja
    /display-analyze?type=<salah>      -> 500   jalur galat kembar
    /broker-summary (dua sebab beda)   -> 500   muncul di log saat lihat lain
    Ringkasan Sinyal hilang total              DILAPORKAN PENGGUNA
    Kering Screener 33 detik                   DILAPORKAN PENGGUNA

Dua yang terakhir sampai ke pengguna karena tidak ada yang memeriksa.

DUA JENIS KERUSAKAN, DUA JENIS PEMERIKSAAN

  1. Balasan galat. Status bukan 200 -- gampang dilihat, asal ada yang
     menembak rutenya.

  2. BALASAN 200 YANG TETAP RUSAK. Ini yang mahal. Kering Screener 33 detik
     dan /saham-data yang menggantung 19 detik SAMA-SAMA membalas 200;
     memeriksa status saja tidak akan pernah menangkapnya. Karena itu tiap
     entri punya `batas` waktu, dan halaman punya `penanda` -- potongan HTML
     yang WAJIB ada. Kartu Ringkasan Sinyal yang hilang tidak mengubah status
     apa pun; yang berubah cuma hilangnya elemen di halaman.

CARA MASUK TANPA LOGIN
Meniru konfigurasi bdm-flask-nologin: before_request memanggil login_user()
dengan pengguna pertama. Tanpa ini base.html merender kerangka minimal
(topbar dan sidebar tidak ikut), jadi pemeriksaan `penanda` selalu gagal --
sempat menyesatkan waktu modul ini dibuat.

Entri beropsi {'anonim': True} justru diuji SEBAGAI TAMU: klien uji terpisah
(tanpa cookie sesi) plus header X-Uji-Anonim yang membuat _masuk() tidak
login. Sejak "/" jadi landing page publik, dua hal wajib dijaga: landing-nya
terbuka tanpa login, dan halaman lain TETAP dilempar ke /login.

BATAS WAKTU DIPILIH LONGGAR
Tujuannya menangkap yang RUSAK, bukan mengejar kecepatan. Ambang default 8
detik; halaman berat yang memang lambat diberi batasnya sendiri. Kalau
sesuatu menembus 8 detik, biasanya memang ada cache yang tidak terbangun --
persis kondisi yang bikin Kering Screener 33 detik.

PEMAKAIAN
    python -m website.uji_asap              # semua
    python -m website.uji_asap --cepat      # lewati yang berat
    python -m website.uji_asap --hanya /saham /kering
"""
import sys
import json
import time
import argparse
import traceback

SAHAM = 'BBCA'
BATAS_UMUM = 8.0

# ---------------------------------------------------------------------------
# DAFTAR UJI
#   (metode, path, data_form, [penanda...], batas_detik[, status_ok[, opsi]])
#
# `penanda` adalah potongan HTML/JSON yang WAJIB ada. Inilah yang membedakan
# "halaman terbuka" dari "halaman benar" -- kartu yang hilang tidak pernah
# mengubah status HTTP.
# ---------------------------------------------------------------------------
ANONIM = {'anonim': True}

UJI = [
    # -- publik: tanpa login --
    # Landing page harus memuat angka datanya dan status bukti; halaman
    # lain harus tetap terkunci (302 ke /login), bukan ikut terbuka.
    ('GET', '/', None, ['lp-hero', 'Status bukti', 'href="/login"'], BATAS_UMUM, (200,), ANONIM),
    ('GET', '/login', None, ['auth-split', 'name="password"', 'csrf_token'], BATAS_UMUM, (200,), ANONIM),
    ('GET', '/sign-up', None, ['auth-split', 'name="password2"', 'csrf_token'], BATAS_UMUM, (200,), ANONIM),
    ('GET', '/tembus-basis', None, None, BATAS_UMUM, (302,), ANONIM),
    ('GET', '/pnl', None, None, BATAS_UMUM, (302,), ANONIM),
    ('GET', '/skor-kecondongan', None, None, BATAS_UMUM, (302,), ANONIM),
    ('GET', '/digital-twin', None, None, BATAS_UMUM, (302,), ANONIM),

    # -- halaman utama --
    # db-kpis: dashboard versi baru ikut terender.
    ('GET', '/', None, ['appPageTitle', 'db-kpis', 'app-user'], BATAS_UMUM),
    # Tombol Keluar adalah form POST; route-nya dulu cuma GET (selalu 405).
    ('POST', '/logout', None, None, BATAS_UMUM, (302,)),
    ('GET', '/watchlist-digest', None, ['appPageTitle'], 12.0),
    ('GET', '/jurnal-keputusan', None, ['appPageTitle'], BATAS_UMUM),
    # 'jejak' harus ada di payload: kalau agregatnya gagal dihitung,
    # halaman tetap 200 dan kartunya cuma bilang 'tidak tersedia'.
    ('GET', '/jurnal-keputusan-data', None, ['available', 'jejak'], 10.0),
    ('GET', '/watchlist-history', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/compare', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/weekly-report', None, ['appPageTitle'], 15.0),
    # 'Posisi Tertutup' harus ikut terender walau belum ada isinya --
    # kalau seksi itu hilang, tombol Tutup kehilangan tempat hasilnya
    # muncul dan riwayat posisi diam-diam jadi tidak terlihat.
    ('GET', '/pnl', None, ['appPageTitle', 'Posisi Tertutup'], BATAS_UMUM),
    ('GET', '/akuisisi', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/kepemilikan-saham', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/perbarui-kepemilikan', None, ['appPageTitle'], BATAS_UMUM),
    ('POST', '/perbarui-kepemilikan/status', {}, ['ksei', 'registry', 'lbrpe', 'latar'], 10.0),
    ('GET', '/scanner-lab', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/serapan-float', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/akumulasi-palsu', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/audit-screener', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/penemu-pola', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/tembus-basis', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/radar-insider', None, ['appPageTitle', 'Jurnal Maju'], BATAS_UMUM),
    ('GET', '/dicicil-insider', None, ['appPageTitle'], BATAS_UMUM),
    ('POST', '/dicicil-insider-data', {}, ['available', 'rows'], 30.0),
    # Hari tanpa sinyal itu wajar (aturannya ketat) dan dibalas 302 ke
    # halamannya -- yang diuji cuma rutenya tidak 500.
    ('GET', '/tembus-basis/chart', None, None, BATAS_UMUM, (200, 302)),

    # Chart emiten satu pola. Kuncinya orde-1 supaya tidak ikut hilang saat
    # ambang MIN_N atau MAX_ORDE digeser -- yang diuji di sini pencarian
    # kunci -> daftar emiten -> viewer, bukan pola tertentu masih lolos.
    ('GET', '/penemu-pola/saham?k=top5~beli', None,
     ['appPageTitle', 'var tickers'], 10.0),
    # Kunci ngawur harus balik ke tabelnya, bukan 500 atau viewer kosong.
    ('GET', '/penemu-pola/saham?k=ngawur~x', None, None, BATAS_UMUM, (302,)),
    ('GET', '/sidik-jari-broker', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/rontgen-portofolio', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/kepercayaan-data', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/takaran-risiko', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/emiten-hilang', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/apa-berubah', None, ['appPageTitle'], BATAS_UMUM),
    # Status Bukti dirender server-side, jadi isinya harus ADA di HTML --
    # bukan cuma judul halaman. Kalau tabelnya kosong, halaman tetap 200.
    ('GET', '/status-bukti', None, ['appPageTitle', 'Teruji luar sampel', 'risiko.py'], BATAS_UMUM),
    ('GET', '/insider-activity', None, ['appPageTitle'], BATAS_UMUM),
    # Digital Twin: halaman dirender kosong lalu diisi /digital-twin-awal.
    # Kalau bahan formulirnya gagal (mis. paket twin rusak diimpor), halaman
    # tetap 200 tapi tanpa preset -- karena itu endpoint-nya ikut diuji.
    ('GET', '/digital-twin', None, ['appPageTitle', 'dtJalankan', 'Rapor Realisme'], BATAS_UMUM),
    ('POST', '/digital-twin-awal', {}, ['!preset', '!jenis', '!kandidat', '!defaults'], 10.0),
    ('GET', '/count', None, ['appPageTitle'], BATAS_UMUM),

    # Kering Screener: pernah 33 detik karena satu berkas Summary tersentuh.
    ('GET', '/kering-screener', None, ['appPageTitle', 'Pindai Ulang'], 10.0),

    # Halaman Saham: kartu Ringkasan Sinyal pernah hilang TOTAL sementara
    # statusnya tetap 200, karena satu panggilan lambat menjatuhkan render.
    ('GET', '/saham/' + SAHAM, None, ['appPageTitle', 'hbDecisionHeadline'], 10.0),

    # -- watchlist: jenis benar DAN jenis salah --
    # Jenis salah dulu balas 500 karena jalur galatnya merender tanpa
    # db_type_name, lalu `{{ db_type_name|tojson }}` kena Undefined.
    ('GET', '/display-stock-list?type=BestStocks', None, ['appPageTitle'], 20.0),
    ('GET', '/display-stock-list?type=ngawur', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/display-stock-list', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/display-analyze?type=ngawur', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/display-stocks/', None, ['appPageTitle'], 20.0),

    # -- endpoint data: yang menyuplai kartu & tabel --
    ('POST', '/saham-data/' + SAHAM, None, ['available', 'modal_bandar', 'price'], 10.0),
    ('POST', '/filter-facts', {}, ['available', 'lapis_counts', 'facts'], BATAS_UMUM),
    ('POST', '/kering-screener-data', {}, ['available'], 10.0),
    ('POST', '/audit-screener-data', {}, ['available'], 10.0),
    ('POST', '/audit-sisi-data', {}, ['available', 'rows'], 10.0),
    # 'jurnal' harus ikut terkirim: kalau pembacaannya diam-diam gagal,
    # halaman tetap 200 dan kolom Maju cuma berisi em-dash -- tidak bisa
    # dibedakan dari "belum matang", yang memang keadaan normalnya.
    ('POST', '/penemu-pola-data', {}, ['available', 'jurnal'], 10.0),
    ('POST', '/sidik-jari-broker-data', {'mode': 'modal'}, ['available'], 15.0),
    ('POST', '/serapan-float-data', {}, ['available'], 10.0),
    # 'jurnal' harus ikut terkirim: kalau evaluasinya diam-diam gagal,
    # halaman tetap 200 dan kartu Jurnal Maju cuma bilang tidak tersedia --
    # padahal jurnal itulah satu-satunya bukti ke depan untuk menu ini.
    ('POST', '/tembus-basis-data', {}, ['available', 'baris', 'jurnal', 'bukti'], 15.0),
    # '!semua': peringkat kosong berstatus 200 = panel harga gagal dibaca.
    ('GET', '/skor-kecondongan', None, ['appPageTitle'], BATAS_UMUM),
    ('GET', '/ramai-dibahas', None, ['appPageTitle', 'rdTabelCard'], BATAS_UMUM),
    ('POST', '/ramai-dibahas-data', {}, ['available', 'tg_siap', 'tarik'], 15.0),
    # '!contoh': pustaka ada tapi pencarian tetangga diam-diam kosong.
    ('GET', '/chart-mirip-data/BBCA', None, ['available', 'tetangga', '!contoh'], 5.0),
    ('POST', '/skor-kecondongan-data', {}, ['available', '!semua', '!atas', '!bawah', 'jurnal', 'bukti'], 30.0),
    # Sama alasannya: kalau jurnal insider diam-diam gagal, radar tetap 200
    # dan kartu Jurnal Maju cuma bilang tidak tersedia.
    ('POST', '/radar-insider-data', {}, ['available', 'jurnal'], 15.0),
    ('POST', '/akumulasi-palsu-data', {}, ['available'], 10.0),
    ('POST', '/kepercayaan-data-data', {}, ['available'], 10.0),
    # 'takaran' harus ikut terkirim: kalau risiko.untuk_ticker() diam-diam
    # gagal untuk semua baris, halaman tetap 200 dan bagian Porsi Risiko
    # cuma menampilkan "belum bisa dihitung" -- tidak bisa dibedakan dari
    # portofolio yang isinya memang tidak terukur.
    ('POST', '/rontgen-portofolio-data', {}, ['available', 'takaran'], 10.0),
    ('POST', '/takaran-risiko-data', {}, ['available', 'baris', 'grid'], 10.0),
    ('POST', '/emiten-hilang-data', {}, ['available', 'zona'], 10.0),
    # Belum tentu available: butuh dua hari bursa tercatat. Yang diuji di
    # sini endpointnya tidak 500 dan selalu menjawab dengan bentuk yang
    # sama -- karena itu kunci yang dicek 'message', bukan 'available'.
    ('POST', '/apa-berubah-data', {}, None, 15.0),
    ('POST', '/watchlist-digest-data', {}, ['available'], 15.0),
    ('POST', '/crowding-data', {'stocks': SAHAM}, ['available'], BATAS_UMUM),
    ('POST', '/insider-activity-data', {}, ['available'], 10.0),
    ('GET', '/saham-watchlist-data', None, ['available'], BATAS_UMUM),
    ('GET', '/watchlist-history/latest', None, None, BATAS_UMUM),
    ('GET', '/stock-chart-data/' + SAHAM, None, None, BATAS_UMUM),
    ('GET', '/watchlist-tickers?type=BestStocks', None, None, BATAS_UMUM),

    # -- Broker Footprint & Trend di hari-hari berkas .xls IPOT --
    # 16-22 Sep 2026 sengaja: minggu pertama sesudah unduhan pindah dari
    # JSON ke .xls. Dulu kedua endpoint ini cuma kenal JSON dan membalas 200
    # dengan daftar KOSONG -- '!' mewajibkan isinya ada.
    ('POST', '/broker-footprint-data', {'stocks': 'BBCA,BBRI', 'stockType': 'All',
                                        'rangeDate': '09/16/2026 - 09/22/2026'},
     ['!buyers', '!sellers'], BATAS_UMUM),
    ('POST', '/broker-footprint-data', {'stocks': 'BBCA,BBRI', 'stockType': 'Foreign',
                                        'rangeDate': '09/16/2026 - 09/22/2026'},
     ['!buyers'], BATAS_UMUM),
    ('POST', '/broker-trend-data', {'stock': SAHAM, 'brokerCode': 'YU', 'stockType': 'All',
                                    'rangeDate': '09/16/2026 - 09/22/2026'},
     ['!series'], BATAS_UMUM),

    # -- broker summary: tiga cara gagal yang pernah terjadi --
    # (1) masukan kosong -> dulu AttributeError pada None.split()
    # (2) stockType di luar All/Foreign -> dulu UnboundLocalError
    # (3) rentang tanpa berkas -> dulu mengembalikan DataFrame dari view
    ('POST', '/broker-summary', {}, None, BATAS_UMUM, (400,)),
    ('POST', '/broker-summary', {'stockType': 'Domestic', 'stock': SAHAM,
                                 'rangeDate': '09/01/2026 - 09/05/2026'}, None, BATAS_UMUM, (400,)),
    ('POST', '/broker-summary', {'stockType': 'All', 'stock': SAHAM,
                                 'rangeDate': '01/01/2010 - 01/05/2010'}, None, BATAS_UMUM, (404,)),
    ('POST', '/broker-summary', {'stockType': 'All', 'stock': SAHAM,
                                 'rangeDate': '09/01/2026 - 09/05/2026'}, None, 15.0),
]

BERAT = {'/display-stocks/', '/weekly-report', '/watchlist-digest', '/display-stock-list?type=BestStocks'}


def _app():
    import werkzeug
    if not getattr(werkzeug, '__version__', None):
        werkzeug.__version__ = '3.0.0'
    from flask_login import login_user
    from . import create_app
    from .models import User

    app = create_app()
    app.config['WTF_CSRF_ENABLED'] = False

    # Sama seperti konfigurasi bdm-flask-nologin. Tanpa ini base.html
    # merender kerangka minimal dan semua pemeriksaan `penanda` gagal palsu.
    @app.before_request
    def _masuk():
        from flask import request
        if request.headers.get('X-Uji-Anonim'):
            return None
        try:
            u = User.query.first()
            if u is not None:
                login_user(u)
        except Exception:
            pass

    return app


def jalankan(hanya=None, cepat=False):
    app = _app()
    c = app.test_client()
    tamu = app.test_client()          # tanpa cookie sesi: untuk entri ANONIM
    hasil = []

    for entri in UJI:
        metode, path, data, penanda, batas = entri[:5]
        status_ok = entri[5] if len(entri) > 5 else (200,)
        opsi = entri[6] if len(entri) > 6 else {}
        if hanya and not any(h in path for h in hanya):
            continue
        if cepat and path in BERAT:
            hasil.append((metode, path, 'LEWAT', 0.0, '--cepat'))
            continue

        t0 = time.time()
        try:
            kl, hdr = (tamu, {'X-Uji-Anonim': '1'}) if opsi.get('anonim') else (c, {})
            r = (kl.post(path, data=data or {}, headers=hdr) if metode == 'POST'
                 else kl.get(path, headers=hdr))
            dur = time.time() - t0
            body = r.get_data(as_text=True)
        except Exception as exc:
            hasil.append((metode, path, 'ERROR', time.time() - t0,
                          '%s: %s' % (type(exc).__name__, exc)))
            continue

        catatan = []
        if r.status_code not in status_ok:
            catatan.append('status %d (harusnya %s)'
                           % (r.status_code, '/'.join(str(s) for s in status_ok)))
        if dur > batas:
            # Inilah yang menangkap Kering 33 detik dan /saham-data 19 detik:
            # keduanya membalas 200, jadi hanya waktu yang membedakannya.
            catatan.append('LAMBAT %.1fs (batas %.0fs)' % (dur, batas))

        # Balasan JSON diperiksa sebagai JSON, bukan dicocokkan sebagai teks.
        # Versi pertama modul ini mencari '"available": true' apa adanya dan
        # gagal palsu di dua endpoint -- jsonify tidak menulis spasi seperti
        # itu, dan urutan kuncinya pun tidak dijamin. Uji yang berteriak
        # karena formatnya, bukan karena isinya, akan cepat diabaikan orang.
        js = None
        if 'application/json' in (r.headers.get('Content-Type') or ''):
            try:
                js = json.loads(body)
            except ValueError:
                catatan.append('balasan JSON tidak terbaca')
        for pen in (penanda or []):
            # '!kunci' = kunci wajib ada DAN berisi. Untuk endpoint yang
            # gagalnya berupa daftar kosong berstatus 200 -- persis Broker
            # Footprint/Trend waktu pembacanya cuma kenal JSON.
            wajib_isi = pen.startswith('!')
            kunci = pen[1:] if wajib_isi else pen
            if js is not None and isinstance(js, dict):
                if kunci not in js:
                    catatan.append('kunci hilang: %s' % kunci)
                elif wajib_isi and not js.get(kunci):
                    catatan.append('kosong: %s' % kunci)
                elif kunci == 'available' and js.get('available') is not True:
                    catatan.append('available=%r (pesan: %s)'
                                   % (js.get('available'), str(js.get('message'))[:60]))
            elif kunci not in body:
                catatan.append('penanda hilang: %s' % kunci)

        label = path + (' [tamu]' if opsi.get('anonim') else '')
        hasil.append((metode, label, 'GAGAL' if catatan else 'ok', dur, '; '.join(catatan)))

    return hasil


def laporan(hanya=None, cepat=False):
    print('=' * 78)
    print('UJI ASAP  %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    print('=' * 78)
    t0 = time.time()
    hasil = jalankan(hanya=hanya, cepat=cepat)

    gagal = [h for h in hasil if h[2] in ('GAGAL', 'ERROR')]
    lambat = sorted([h for h in hasil if h[2] == 'ok'], key=lambda h: -h[3])[:5]

    print('\n%-5s %-46s %-6s %8s  %s' % ('', 'path', 'status', 'detik', 'catatan'))
    for metode, path, status, dur, catatan in hasil:
        if status == 'ok':
            continue
        print('%-5s %-46s %-6s %8.2f  %s' % (metode, path[:46], status, dur, catatan))
    if not gagal:
        print('  (tidak ada yang gagal)')

    print('\n5 TERLAMBAT yang masih lolos:')
    for metode, path, _s, dur, _c in lambat:
        print('  %-46s %6.2f dtk' % (path[:46], dur))

    n = len(hasil)
    print('\n%d diuji | %d gagal | total %.1f detik' % (n, len(gagal), time.time() - t0))
    return gagal


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Tembak semua halaman & endpoint.')
    ap.add_argument('--cepat', action='store_true', help='lewati halaman berat')
    ap.add_argument('--hanya', nargs='*', help='hanya path yang mengandung teks ini')
    a = ap.parse_args()
    try:
        gagal = laporan(hanya=a.hanya, cepat=a.cepat)
    except Exception:
        traceback.print_exc()
        sys.exit(2)
    sys.exit(1 if gagal else 0)
