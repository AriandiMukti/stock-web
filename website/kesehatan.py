"""
Pemeriksa kesehatan harian: verifikasi data, lalu bangun ulang semua cache
menurut urutan ketergantungannya.

KENAPA MODUL INI ADA

Dalam satu hari kerja, tiga bug dari keluarga yang sama muncul -- dan
ketiganya ditemukan secara kebetulan, bukan karena ada yang memberi tahu:

  1. Kering Screener memakan 33 detik pada SETIAP permintaan karena satu
     dari 881 berkas Summary tersentuh.
  2. Modal bandar membangun ulang FIFO dari 3,5 juta baris (~2 menit) di
     dalam permintaan halaman saham, sehingga seluruh kartu Ringkasan
     Sinyal tidak pernah muncul.
  3. Satu baris dengan Close kosong lolos masuk ke Summary secara permanen.

Akarnya satu: CACHE MAHAL TANPA PEMILIK. Tidak ada yang membangunnya
terjadwal, jadi ia dibangun malas di dalam permintaan pengguna -- dan
kalau gagal, gagal diam-diam.

URUTAN KETERGANTUNGAN ADALAH INTINYA

Saat modul ini ditulis, keadaannya begini:

    modal_bandar_cache.pkl    umur  0,9 jam   <- terlihat segar
    broker_ledger.pkl         umur 41,4 jam   <- basi

Modal bandar dibangun ulang sejam sebelumnya, TAPI DARI buku besar broker
berumur hampir dua hari. Angkanya terlihat baru, isinya data lusa, dan
tidak ada apa pun di layar yang memberi tahu.

Membangun anak tanpa induknya menghasilkan cache yang terlihat segar tapi
isinya basi -- kegagalan yang paling sulit dilihat karena semua indikator
tampak hijau. Karena itu URUTAN di TUGAS di bawah bukan sekadar rapi-rapi;
ia menentukan benar atau tidaknya hasilnya.

PEMAKAIAN
    python -m website.kesehatan              # periksa + bangun semua
    python -m website.kesehatan --periksa     # periksa saja, tanpa bangun
    python -m website.kesehatan --cepat       # lewati broker_ledger (~2 menit)
    python -m website.kesehatan --hanya modal_bandar kering
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import sys
import glob
import time
import pickle
import argparse
import traceback
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
ALL_DIR = os.path.join(DAILY_PATH, 'All')
HERE = os.path.dirname(__file__)

BASI_JAM = 24          # cache lebih tua dari ini dianggap perlu dibangun
BERKAS_KECIL = 2000    # byte; di bawah ini berkas broker dianggap kosong


# ---------------------------------------------------------------------------
# TUGAS PEMBANGUNAN -- URUTANNYA PENTING, JANGAN DIACAK.
#
# `induk` menyatakan cache ini diturunkan dari cache lain. Kalau induknya
# dibangun ulang, anaknya WAJIB ikut dibangun -- kalau tidak, anaknya jadi
# "segar tapi isinya basi", kegagalan yang paling sulit terlihat.
# ---------------------------------------------------------------------------
TUGAS = [
    # build() TANPA force: mode bertambah, cuma membaca folder tanggal yang
    # baru atau yang mtime-nya berubah. Dulu force=True di sini mengurai
    # ulang ~152 ribu berkas JSON tiap pagi untuk menambahkan satu hari --
    # 142 detik, sepertiga dari seluruh rebuild, dan satu-satunya tugas
    # yang menahan modal_bandar dan sidik_jari di belakangnya.
    #
    # Pembacaan penuh tetap ada sebagai jaring pengaman untuk dijalankan
    # berkala (arsip disalin ulang, jam sistem mundur, cache dicurigai):
    #     python -m website.broker_ledger
    dict(nama='broker_ledger', cache='broker_ledger.pkl', induk=None,
         perkiraan='~5 detik (bertambah)',
         jalan=lambda: __import__('website.broker_ledger', fromlist=['x']).build()),

    dict(nama='modal_bandar', cache='modal_bandar_cache.pkl', induk='broker_ledger',
         perkiraan='~30 detik',
         jalan=lambda: __import__('website.broker_fingerprint', fromlist=['x'])._modal_terakhir(force=True)),

    # cache=None dulu di sini, padahal build() memang menulis
    # broker_fingerprint_cache.pkl. Akibatnya sidik_jari jadi SATU-SATUNYA
    # tugas yang umurnya tidak pernah muncul di tabel [CACHE], tidak pernah
    # ikut pemeriksaan "segar tapi isinya basi" (periksa_cache melewati
    # tugas tanpa cache), dan tidak ikut kartu cache di Beranda yang memakai
    # _berkas() yang sama. Terbukti 11 September: seluruh cache lain
    # dibangun ulang pukul 18.10, berkas ini tertinggal di 19.55 hari
    # sebelumnya -- laporan tetap mencetak "[MASALAH] 0". Persis kegagalan
    # diam-diam yang jadi alasan modul ini ada.
    dict(nama='sidik_jari', cache='broker_fingerprint_cache.pkl',
         induk='broker_ledger',
         perkiraan='~10 detik',
         jalan=lambda: __import__('website.broker_fingerprint', fromlist=['x']).build(force=True)),

    dict(nama='stock_filter', cache='stock_filter_cache.pkl', induk=None,
         perkiraan='~3 detik',
         jalan=lambda: __import__('website.stock_filter', fromlist=['x']).facts(force=True)),

    dict(nama='kering', cache='kering_screener_cache.pkl', induk=None,
         perkiraan='~35 detik',
         jalan=lambda: __import__('website.kering_screener', fromlist=['x']).refresh(force=True)),

    dict(nama='data_confidence', cache='data_confidence_cache.pkl', induk=None,
         perkiraan='~20 detik',
         jalan=lambda: __import__('website.data_confidence', fromlist=['x']).scan(force=True)),

    dict(nama='screener_side', cache='screener_side_cache.pkl', induk=None,
         perkiraan='~7 detik',
         jalan=lambda: __import__('website.screener_side', fromlist=['x']).audit(force=True)),

    dict(nama='pattern_miner', cache='pattern_miner_cache.pkl', induk=None,
         perkiraan='~1 menit',
         jalan=lambda: __import__('website.pattern_miner', fromlist=['x']).mine(force=True)),

    dict(nama='signal_recall', cache='signal_recall_cache.pkl', induk=None,
         perkiraan='~30 detik',
         jalan=lambda: __import__('website.signal_recall', fromlist=['x']).audit(force=True)),

    dict(nama='float_squeeze', cache='float_squeeze_cache.pkl', induk=None,
         perkiraan='~20 detik',
         jalan=lambda: __import__('website.float_squeeze', fromlist=['x']).scan(force=True)),

    dict(nama='screen_eval', cache='screen_eval_cache.pkl', induk=None,
         perkiraan='~15 detik',
         jalan=lambda: __import__('website.screen_eval', fromlist=['x']).build_report(force=True)),

    # TIGA days_back dari SATU lintasan. live_scan menyimpan satu berkas
    # cache per days_back (lihat live_scan._cache_file) dan menganggapnya
    # basi begitu ada Summary yang lebih baru -- artinya unduhan harian
    # membasikan ketiganya sekaligus. Dulu di sini cuma cached_scan(
    # force=True), yang memakai default 60, jadi yang 14 dan 90 tidak
    # pernah dihangatkan dan dibangun ulang di dalam permintaan:
    # /watchlist-digest-data 59 detik dan /saham-data 57 detik, tiap hari
    # bursa, dilaporkan uji asap sebagai GAGAL. Uji yang selalu merah
    # untuk hal normal akan berhenti dibaca.
    #
    # warm() memindai sekali lalu menyaring, bukan tiga kali: 140 detik
    # jadi 47, hasilnya terbukti identik baris per baris.
    #
    #   14 = Ringkasan Watchlist   60 = Scanner Lab   90 = Halaman Saham
    dict(nama='live_scan', induk=None,
         cache=('live_scan_cache_14.pkl', 'live_scan_cache_60.pkl',
                'live_scan_cache_90.pkl'),
         perkiraan='~50 detik',
         jalan=lambda: __import__('website.live_scan', fromlist=['x']).warm((14, 60, 90))),

    dict(nama='baseline', cache='baseline_cache.pkl', induk=None,
         perkiraan='~8 detik',
         jalan=lambda: __import__('website.baseline', fromlist=['x']).hitung(force=True)),

    dict(nama='market_regime', cache='market_regime_cache.pkl', induk=None,
         perkiraan='~5 detik',
         jalan=lambda: __import__('website.market_regime', fromlist=['x']).get_regime(force=True)),

    dict(nama='risiko', cache='risiko_cache.pkl', induk=None,
         perkiraan='~5 detik',
         jalan=lambda: __import__('website.risiko', fromlist=['x']).scan(force=True)),

    dict(nama='survivorship', cache='survivorship_cache.pkl', induk=None,
         perkiraan='~5 detik',
         jalan=lambda: __import__('website.survivorship', fromlist=['x']).scan(force=True)),

    # Membangun ulang sekaligus MENCATAT jurnal maju hari ini (lihat
    # tembus_basis.catat). Jurnal itu yang bolongnya tidak bisa dikejar,
    # jadi tugas ini wajib jalan tiap hari bursa -- periksa_jurnal_tembus()
    # yang memastikan.
    dict(nama='tembus_basis', cache='tembus_basis_cache.pkl', induk=None,
         perkiraan='~10 detik',
         jalan=lambda: __import__('website.tembus_basis', fromlist=['x']).scan(force=True)),

    # Pustaka Chart Termirip (chart_mirip.py). Cuma bergantung pada pickle
    # harga Yahoo di research_cache: kalau pickle itu tidak berubah, bangun()
    # cuma menyentuh cache (detik), tidak menghitung ulang (~35 detik).
    dict(nama='chart_mirip', cache='chart_mirip_cache.pkl', induk=None,
         perkiraan='~1 detik (35 detik kalau harga riset berubah)',
         jalan=lambda: __import__('website.chart_mirip', fromlist=['x']).bangun()),

    # Peringkat harian + jurnal maju Skor Kecondongan (kecondongan.py).
    # Sama seperti tembus_basis: jurnalnya yang bolong tidak bisa dikejar,
    # periksa_jurnal_kecondongan() yang menjaga.
    dict(nama='kecondongan', cache='kecondongan_cache.pkl', induk=None,
         perkiraan='~20 detik',
         jalan=lambda: __import__('website.kecondongan', fromlist=['x']).scan(force=True)),

    # Mencatat transaksi insider yang BARU pertama kali terlihat (tanggal
    # terlihat, bukan tanggal transaksi) lalu menilai yang sudah matang.
    # Lihat insider_jurnal.py. Bolongnya juga tidak bisa dikejar --
    # periksa_jurnal_insider() yang menjaga.
    dict(nama='insider_jurnal', cache='insider_jurnal_cache.pkl', induk=None,
         perkiraan='~6 detik',
         jalan=lambda: __import__('website.insider_jurnal', fromlist=['x']).jalankan()),

    # Rapat Agen (rapat_agen.py): menimbang kandidat dekat support + dicicil
    # insider memakai cache tembus_basis/kecondongan/risiko di atas, lalu
    # mencatat keputusannya ke rapat_agen_jurnal.csv. Harus SETELAH ketiganya.
    dict(nama='rapat_agen', cache='rapat_agen_cache.pkl', induk=None,
         perkiraan='~30 detik',
         jalan=lambda: __import__('website.rapat_agen', fromlist=['x']).scan(force=True)),

    # Jurnal maju skrip StockLang yang dicentang "jurnal harian" di /stocklang
    # (stocklang_jurnal.py). Tiap skrip jalan di proses sendiri dengan batas
    # 60 detik. Sama seperti jurnal lain: hari yang terlewat tidak bisa dikejar.
    dict(nama='stocklang_jurnal', cache=None, induk=None,
         perkiraan='~2 detik per skrip berjurnal',
         jalan=lambda: __import__('website.stocklang_jurnal', fromlist=['x']).catat()),

    # Laporan StockLang untuk HP (stocklang_laporan.py): yang lolos hari ini +
    # nilai jurnalnya, disimpan lalu ikut ekspor Sinkron (menu 'stocklang').
    # Induknya stocklang_jurnal supaya di mode paralel tidak mencatat berbarengan.
    dict(nama='stocklang_laporan', cache='stocklang_laporan.json', induk='stocklang_jurnal',
         perkiraan='~2 detik per skrip berjurnal',
         jalan=lambda: __import__('website.stocklang_laporan', fromlist=['x']).simpan()),

    # Jurnal maju dua temuan uji 18 Okt 2026 (msci_jurnal.py, pk_jurnal.py).
    # MSCI: di bulan review (Feb/Mei/Agu/Nov) mencoba mengunduh PDF review
    # berikutnya dari app2.msci.com, mencatat emiten-review baru, lalu
    # mengisi hasil D1 -> E -> E+20 yang jendelanya sudah lewat. Pemantauan
    # Khusus: datanya masuk lewat impor skrip browser di
    # /perbarui-kepemilikan; tugas ini cuma menilai H+5/H+20. Panel harga
    # (~15 detik) hanya dimuat kalau ada kejadian yang perlu dinilai.
    # Tebakan "dihapus dari MSCI Standard" (msci_tebakan.py, uji 28 Okt 2026)
    # dicatat SEBELUM pengumuman -- jadi harus jalan sebelum msci_jurnal yang
    # mengunduh PDF review. Mengunduh sendiri arsip KSEI bulan sebelum review.
    dict(nama='msci_tebakan', cache=None, induk=None,
         perkiraan='~5 detik (~15 detik kalau ada yang dinilai)',
         jalan=lambda: __import__('website.msci_tebakan', fromlist=['x']).jalankan()),
    dict(nama='msci_jurnal', cache=None, induk=None,
         perkiraan='~1 detik (~15 detik kalau ada yang dinilai)',
         jalan=lambda: __import__('website.msci_jurnal', fromlist=['x']).jalankan()),
    dict(nama='pk_jurnal', cache=None, induk=None,
         perkiraan='~1 detik (~15 detik kalau ada yang dinilai)',
         jalan=lambda: __import__('website.pk_jurnal', fromlist=['x']).jalankan()),

    # Tarik obrolan Stockbit + Telegram untuk /ramai-dibahas (ramai_dibahas.py)
    # dan catat bacaan 24 jamnya ke ramai_dibahas_harian.csv. Stockbit cuma
    # memberi 30 post terakhir per emiten, jadi hari yang tidak ditarik
    # bolong di sentimen Senin-Jumat -- terbukti 17-24 Okt 2026, minggu itu
    # cuma terwakili tarikan hari Minggunya. Butuh internet; grup Telegram
    # yang gagal tidak menggagalkan tugas (statusnya tercatat per grup).
    dict(nama='ramai_dibahas', cache='ramai_dibahas_sebutan.pkl', induk=None,
         perkiraan='~1 menit',
         jalan=lambda: __import__('website.ramai_dibahas', fromlist=['x']).kumpulkan()),

    # PALING BELAKANG, DAN ITU WAJIB. perubahan.rekam() memotret keanggotaan
    # layar-layar di atas; kalau dia jalan lebih dulu, yang terpotret
    # keanggotaan KEMARIN (dari cache yang belum dibangun ulang) tapi
    # tersimpan dengan tanggal HARI INI. Selisih besok lalu membandingkan
    # dua potret yang isinya sama dan melaporkan "tidak ada perubahan" --
    # persis kegagalan diam-diam yang jadi alasan modul kesehatan ini ada.
    #
    # Tidak punya `cache`: keluarannya jurnal CSV yang BERTAMBAH, bukan
    # berkas yang ditimpa, jadi umurnya tidak bisa dibandingkan dengan
    # mtime sumber seperti cache lain.
    dict(nama='perubahan', cache=None, induk='risiko',
         perkiraan='~5 detik',
         jalan=lambda: __import__('website.perubahan', fromlist=['x']).rekam()),
]


def _tanpa_baris_broker(paths):
    """
    Berapa berkas yang TIDAK menghasilkan satu pun baris broker.

    Bukan ukuran byte. BERKAS_KECIL = 2000 byte dulu dipakai untuk ini dan
    ternyata menyesatkan: berkas lengkap milik saham tipis memang di bawah
    2 KB. APII 9 September cuma 1.974 byte, tapi isinya 5 baris broker yang
    sah -- dia cuma disentuh 5 broker hari itu, sementara BBCA 76. Ambang
    byte menyatukan "unduhan gagal" dengan "saham sepi"; hitungan baris
    memisahkannya.

    Ongkosnya ~0,14 detik untuk 962 berkas.
    """
    from .broker_ledger import _parse_file
    n = 0
    for p in paths:
        try:
            if not (_parse_file(p) or []):
                n += 1
        except Exception:
            n += 1
    return n


def _umur_jam(path):
    p = str(_runtime_file('', path))
    if not os.path.exists(p):
        return None
    return (time.time() - os.path.getmtime(p)) / 3600.0


def _berkas(t):
    """`cache` boleh satu nama atau beberapa -- live_scan menulis tiga."""
    c = t['cache']
    if not c:
        return ()
    return (c,) if isinstance(c, str) else tuple(c)


def _umur_terburuk(t):
    """Umur berkas PALING TUA milik satu tugas; None kalau ada yang hilang.

    Sengaja yang paling tua, bukan rata-rata: satu berkas basi sudah cukup
    membuat satu halaman membangun ulang di dalam permintaan pengguna.
    """
    umur = [_umur_jam(f) for f in _berkas(t)]
    if not umur or any(u is None for u in umur):
        return None
    return max(umur)


# ---------------------------------------------------------------------------
# PEMERIKSAAN DATA
# ---------------------------------------------------------------------------
def periksa_data():
    """Periksa kelengkapan & kewarasan data mentah. Tidak mengubah apa pun."""
    masalah = []
    info = {}

    # -- berkas broker hari terakhir --
    # JSON Stockbit ATAU .xls IPOT per emiten (broker_ledger.berkas_tanggal).
    # Dulu cuma menghitung JSON, jadi sejak unduhan pindah ke .xls (16 Sep
    # 2026) baris ini melaporkan "0 berkas" tiap hari.
    from .broker_ledger import berkas_tanggal
    if os.path.isdir(ALL_DIR):
        hari = sorted(d for d in os.listdir(ALL_DIR)
                      if os.path.isdir(os.path.join(ALL_DIR, d)) and d[:2] == '20')
        info['hari_terakhir'] = hari[-1] if hari else None
        if hari:
            f = berkas_tanggal(os.path.join(ALL_DIR, hari[-1]))
            info['n_berkas'] = len(f)
            info['n_tanpa_broker'] = _tanpa_baris_broker(f)
            if len(hari) > 1:
                sebelum = berkas_tanggal(os.path.join(ALL_DIR, hari[-2]))
                info['n_berkas_sebelum'] = len(sebelum)
                # Turun tajam dibanding hari sebelumnya = unduhan terpotong.
                # Ini yang membedakan "pasar sepi" dari "unduhan gagal".
                if sebelum and len(f) < len(sebelum) * 0.8:
                    masalah.append('Berkas broker %s cuma %d, kemarin %d (turun %.0f%%) '
                                   '-- unduhan kemungkinan terpotong.'
                                   % (hari[-1], len(f), len(sebelum),
                                      (1 - len(f) / len(sebelum)) * 100))

                # Mode gagal yang TIDAK tertangkap pemeriksaan di atas:
                # sumbernya membalas sukses tapi isinya kerangka kosong
                # (706 byte, nol baris broker). Jumlah berkasnya utuh, jadi
                # "turun 20%" tidak pernah menyala -- padahal buku besar
                # broker hari itu bolong untuk tiap emiten yang kena.
                #
                # Angka normalnya stabil di ~130 dari 962: saham suspend dan
                # saham yang memang tidak diperdagangkan. Lonjakan besar
                # berarti sesuatu yang lain.
                nb_sebelum = _tanpa_baris_broker(sebelum)
                info['n_tanpa_broker_sebelum'] = nb_sebelum
                naik = info['n_tanpa_broker'] - nb_sebelum
                if nb_sebelum and naik >= 25 and info['n_tanpa_broker'] > nb_sebelum * 1.5:
                    masalah.append(
                        '%d berkas broker %s tidak berisi satu pun baris broker, '
                        'kemarin cuma %d (+%d). Jumlah berkasnya utuh, jadi ini bukan '
                        'unduhan terpotong -- sumbernya membalas sukses dengan isi '
                        'kosong. Buku besar broker hari ini bolong untuk emiten-emiten '
                        'itu.' % (info['n_tanpa_broker'], hari[-1], nb_sebelum, naik))
    else:
        masalah.append('Folder broker tidak ditemukan: %s' % ALL_DIR)

    # -- baris Summary dengan OHLC kosong --
    # Satu baris seperti ini merusak SEMUA hitungan 20/60 hari emiten itu,
    # dan karena ditulis dengan mode append ia permanen sampai dihapus tangan.
    kosong = []
    tertinggal = []
    terbaru = None
    per_emiten = {}
    for path in glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')):
        kode = os.path.basename(path)[:4]
        try:
            d = pd.read_csv(path, usecols=['Date', 'Close'])
            d['Date'] = pd.to_datetime(d['Date'], format='%d-%b-%y', errors='coerce')
        except Exception as exc:
            masalah.append('%s_Summary.csv tidak terbaca: %s' % (kode, exc))
            continue
        n_kosong = int(pd.to_numeric(d['Close'], errors='coerce').isna().sum())
        if n_kosong:
            kosong.append((kode, n_kosong))
        tgl = d['Date'].max()
        if pd.notna(tgl):
            per_emiten[kode] = tgl
            if terbaru is None or tgl > terbaru:
                terbaru = tgl

    if terbaru is not None:
        for kode, tgl in per_emiten.items():
            hari_tertinggal = (terbaru - tgl).days
            if hari_tertinggal > 30:
                tertinggal.append((kode, hari_tertinggal))

    info['n_emiten_summary'] = len(per_emiten)
    info['tanggal_terbaru'] = str(terbaru.date()) if terbaru is not None else None
    info['baris_ohlc_kosong'] = sorted(kosong, key=lambda t: -t[1])
    info['tertinggal'] = sorted(tertinggal, key=lambda t: -t[1])

    if kosong:
        masalah.append('%d emiten punya baris dengan Close kosong (%d baris total). '
                       'Satu baris seperti ini merusak semua hitungan 20/60 hari emiten itu: %s'
                       % (len(kosong), sum(n for _, n in kosong),
                          ', '.join('%s(%d)' % k for k in sorted(kosong, key=lambda t: -t[1])[:8])))

    return info, masalah


def periksa_kepemilikan(contoh=6):
    """
    Pastikan kedua jalur kepemilikan masih merujuk variabel yang SAMA.

    KENAPA ADA
    Ada dua definisi "ritel" di app ini dan pernah tertukar diam-diam:

      build_month_metrics() -> pct_retail   = bucket "Individu" KSEI MENTAH
      build_ownership()     -> pct_retail   = setelah split_retail(),
                                              perorangan bernama >1% dibuang

    KSEI cuma memilah per tipe investor, jadi pengendali yang memegang
    sahamnya atas nama pribadi ikut masuk bucket Individu. PSAB 92,96%
    "individu" ternyata 90% satu nama; ritel sesungguhnya 0,46%. Scanner
    Lab dulu menampilkan yang mentah dengan label "% Ritel" dan memberi
    bonus skor "basis ritel tebal" -- 6 emiten dinilai keliru karenanya.

    Sekarang scanner.py memakai nama own_pct_individu dan Halaman Saham
    disambungkan ke pct_retail_raw, jadi keduanya bicara variabel yang
    sama. Pemeriksaan ini menjaga supaya tetap begitu: kalau kelak ada
    yang "memperbaiki" salah satu sisi -- menerapkan carve-out di panel,
    atau mengarahkan kartu keputusan kembali ke angka yang sudah
    disaring -- laporan harian yang memberi tahu, bukan pengguna.

    Sampel sengaja diambil dari emiten yang carve-out-nya MENGGIGIT
    (mentah != carve-out). Pada emiten yang keduanya sama, tertukar pun
    tidak akan kelihatan, jadi memeriksanya tidak membuktikan apa-apa.
    """
    masalah = []
    try:
        from .ownership import build_ownership, available_tickers, load_idx_registries
        from .scanner import ownership_panel
    except Exception as exc:
        return ['Modul kepemilikan tidak bisa dimuat: %s' % exc]

    try:
        punya = [t for t in available_tickers() if load_idx_registries(t)]
    except Exception as exc:
        return ['Daftar registri IDX tidak terbaca: %s' % exc]
    if not punya:
        return []

    menggigit = []
    for t in punya:
        try:
            o = build_ownership(t)
        except Exception:
            continue
        mentah, carve = o.get('pct_retail_raw'), o.get('pct_retail')
        if mentah is None or carve is None:
            continue
        if abs(mentah - carve) >= 1.0:
            menggigit.append((t, mentah, carve))
        if len(menggigit) >= contoh:
            break

    if not menggigit:
        # Bukan kegagalan: bisa saja memang tidak ada lagi emiten yang
        # carve-out-nya menggigit. Tapi berarti penjaga ini sedang buta.
        return ['Tidak ada emiten dengan carve-out aktif -- pemeriksaan '
                'kepemilikan tidak bisa membuktikan apa pun kali ini.']

    try:
        panel = ownership_panel()
    except Exception as exc:
        return ['ownership_panel() gagal: %s' % exc]

    if 'own_pct_individu' not in panel.columns:
        return ['scanner.ownership_panel() tidak lagi punya kolom '
                'own_pct_individu -- kolom ini dipakai halaman Scanner Lab '
                'dan penilaian sinyal.']

    akhir = panel.sort_values('as_of').groupby('stock').tail(1).set_index('stock')
    for t, mentah, carve in menggigit:
        if t not in akhir.index:
            continue
        panel_nilai = akhir.loc[t, 'own_pct_individu']
        if panel_nilai is None:
            continue
        if abs(float(panel_nilai) - mentah) > 0.02:
            masalah.append(
                '%s: scanner memberi %.2f%% tapi bucket individu mentah '
                '%.2f%% (carve-out %.2f%%). Kedua jalur kepemilikan tidak '
                'lagi merujuk variabel yang sama.'
                % (t, float(panel_nilai), mentah, carve))

    return masalah


def _harga_cocok(df, tanggal, berkas, _kode_sel, longgar=0.1):
    """Median harga rata-rata broker emiten `berkas` di `tanggal` jatuh di
    rentang Low-High Summary hari itu (+-10%). Tanpa data pembanding -> False."""
    from .tembus_basis import _baca_summary
    kode = os.path.splitext(berkas)[0].upper()
    s = _baca_summary(os.path.join(DAILY_PATH, 'Summary', '%s_Summary.csv' % kode))
    t = pd.Timestamp(tanggal)
    if s is None or t not in s.index:
        return False
    harga = df.loc[(df['date'] == t) & (df['stock'] == kode), 'avg_price'].dropna()
    if harga.empty:
        return False
    return s.at[t, 'Low'] * (1 - longgar) <= harga.median() <= s.at[t, 'High'] * (1 + longgar)


def periksa_ledger():
    """
    Invarian buku besar broker: satu (tanggal, saham, broker, sisi) muncul
    TEPAT sekali.

    KENAPA ADA
    Di Daily\\All ada folder bernama `backup` berisi 831 berkas yang
    semuanya bertanggal 20260907. broker_ledger dulu menyapu seluruh
    subfolder tanpa memeriksa namanya, jadi 7 September masuk dua kali dan
    SETIAP angka broker untuk hari itu terhitung ganda -- net lot, nilai,
    harga rata-rata modal bandar, semuanya. Tidak ada yang menangkapnya
    selama berbulan-bulan karena tidak ada yang rusak dan tidak ada yang
    lambat; angkanya cuma salah.

    Uji asap memeriksa halaman yang RUSAK atau LAMBAT. Pemeriksaan ini
    memeriksa angka yang DIAM-DIAM SALAH -- kelas kegagalan yang sama sekali
    berbeda, dan yang paling mahal.
    """
    masalah = []
    try:
        from .broker_ledger import load
    except Exception as exc:
        return ['broker_ledger tidak bisa dimuat: %s' % exc]

    try:
        df, meta = load()
    except Exception as exc:
        return ['broker_ledger.pkl tidak terbaca: %s' % exc]
    if df is None or not len(df):
        return []

    kunci = ['date', 'stock', 'broker', 'side']
    try:
        n_kembar = int(df.duplicated(subset=kunci, keep=False).sum())
    except Exception as exc:
        return ['Buku besar broker tidak bisa diperiksa: %s' % exc]

    if n_kembar:
        contoh = df[df.duplicated(subset=kunci, keep=False)]
        hari = sorted(set(str(d)[:10] for d in contoh['date'].unique()))[:5]
        masalah.append(
            'Buku besar broker punya %d baris kembar pada kunci '
            '(tanggal, saham, broker, sisi) -- satu hari terbaca lebih dari '
            'sekali, jadi angkanya terhitung ganda. Tanggal: %s. '
            'Bangun ulang penuh: python -m website.broker_ledger'
            % (n_kembar, ', '.join(hari)))

    # Ekspor IPOT yang sel Code-nya bukan emiten di nama berkasnya (IFII.xls
    # 28 Sep 2026 bertuliskan EAST). Buku besar memakai nama berkas, tapi
    # berkas salah label bisa juga berisi emiten yang salah -- itu cuma bisa
    # dipastikan dari harganya. Yang harganya cocok dengan Summary emiten di
    # nama berkas tidak dilaporkan: peringatan yang menyala selamanya untuk
    # berkas yang sudah terbukti benar akan berhenti dibaca.
    tidak_cocok = [b for b in (meta or {}).get('kode_beda') or [] if not _harga_cocok(df, *b)]
    if tidak_cocok:
        masalah.append(
            '%d berkas broker .xls sel Code-nya beda dari nama berkas DAN harganya tidak cocok dengan Summary '
            'emiten di nama berkas -- isinya mungkin emiten lain: %s. Unduh ulang berkasnya.'
            % (len(tidak_cocok), ', '.join('%s %s (Code %s)' % tuple(b) for b in tidak_cocok[-5:])))

    # Buku besar yang BERHENTI bertambah padahal folder broker terus terisi.
    # Persis kejadian 16-22 Sep 2026: unduhan pindah dari JSON ke .xls, modul
    # itu cuma membaca JSON, dan mode bertambahnya menyimpulkan "tidak ada
    # yang berubah" -- seminggu Sidik Jari & Modal Bandar membeku tanpa satu
    # pun galat. Tertinggal SATU hari wajar: pemeriksaan ini jalan sebelum
    # pembangunan ulang malam ini.
    sampai = (meta or {}).get('sampai')
    if sampai:
        try:
            from .broker_ledger import ALL_DIR as _ALL, RE_FOLDER_TANGGAL, berkas_tanggal
            baru = [d for d in sorted(os.listdir(_ALL))
                    if RE_FOLDER_TANGGAL.match(d) and d > sampai
                    and berkas_tanggal(os.path.join(_ALL, d))]
        except Exception:
            baru = []
        if len(baru) > 1:
            masalah.append(
                'Buku besar broker berhenti di %s padahal folder broker sudah sampai %s '
                '(%d hari berisi berkas) -- berkas barunya tidak terbaca? Sidik Jari Broker '
                'dan Modal Bandar ikut membeku.' % (sampai, baru[-1], len(baru)))

    return masalah


def periksa_live_scan():
    """
    Invarian cache live_scan: hasil 14 hari harus BAGIAN dari 60, dan 60
    bagian dari 90.

    warm() memindai sekali di rentang terluas lalu menyaring turunannya.
    Kalau suatu saat ada yang membangun salah satunya sendiri-sendiri --
    atau menyaring dengan jangkar yang berbeda -- ketiganya bisa saling
    bertentangan tanpa satu pun terlihat rusak.
    """
    masalah = []
    try:
        import pickle
        from .live_scan import _cache_file
    except Exception as exc:
        return ['live_scan tidak bisa dimuat: %s' % exc]

    isi = {}
    for d in (14, 60, 90):
        try:
            with open(_cache_file(d), 'rb') as fh:
                isi[d] = pickle.load(fh)['df']
        except Exception:
            return []          # cache belum ada -- bukan tugas fungsi ini

    def kunci(df):
        if df is None or not len(df):
            return set()
        return set(zip(df['stock'].astype(str), df['scanner'].astype(str),
                       df['signal_date'].astype(str)))

    k14, k60, k90 = kunci(isi[14]), kunci(isi[60]), kunci(isi[90])
    if not k14 <= k60:
        masalah.append('live_scan: %d sinyal ada di cache 14 hari tapi tidak di 60 hari '
                       '-- ketiga cache tidak lagi berasal dari satu pindaian.'
                       % len(k14 - k60))
    if not k60 <= k90:
        masalah.append('live_scan: %d sinyal ada di cache 60 hari tapi tidak di 90 hari '
                       '-- ketiga cache tidak lagi berasal dari satu pindaian.'
                       % len(k60 - k90))
    return masalah


def periksa_baseline():
    """
    Konstanta baseline yang dibekukan di kode vs hasil ukur ulang hari ini.

    Yang dijaga bukan kesalahan hitung, tapi PERGESERAN: -1,33 dihitung
    sekali lalu ditanam ke scanner.py dan screen_eval.py, dan setiap
    kolom "vs baseline" di app berdiri di atasnya. Kalau pasarnya
    bergeser, seluruh penilaian ikut bergeser tanpa satu pun halaman
    terlihat rusak. Lihat baseline.py.
    """
    try:
        from .baseline import periksa
    except Exception as exc:
        return ['baseline tidak bisa dimuat: %s' % exc]
    return periksa()


def periksa_jurnal_pola():
    """
    Jurnal maju Penemu Pola harus ikut bertambah tiap hari bursa.

    Beda dari cache lain: yang ini TIDAK bisa dibangun ulang. Cache yang
    bolong sehari cuma perlu dijalankan lagi; jurnal yang bolong sehari
    kehilangan hari itu selamanya, karena isinya potret sebelum hasilnya
    ada. Jadi kegagalannya harus terlihat pada hari yang sama, bukan dua
    bulan kemudian saat angkanya dipakai.
    """
    try:
        from .pola_jurnal import _muat, JURNAL_FILE
    except Exception as exc:
        return ['pola_jurnal tidak bisa dimuat: %s' % exc]

    if not os.path.exists(JURNAL_FILE):
        return []              # belum pernah dijalankan -- bukan kerusakan

    j = _muat()
    if j.empty:
        return ['Jurnal Penemu Pola ada tapi kosong.']

    hari_jurnal = str(j['tanggal'].astype(str).max())
    hari_data = None
    try:
        import glob as _g
        from .pattern_miner import SUMMARY_DIR
        berkas = _g.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv'))
        if berkas:
            import pandas as _pd
            df = _pd.read_csv(max(berkas, key=os.path.getsize), usecols=['Date'])
            d = _pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce').dropna()
            if len(d):
                hari_data = str(d.max().date())
    except Exception:
        return []

    if hari_data and hari_jurnal < hari_data:
        return ['Jurnal Penemu Pola berhenti di %s padahal data sudah sampai %s '
                '-- hari yang terlewat tidak bisa dikejar, isinya potret '
                'sebelum hasilnya ada.' % (hari_jurnal, hari_data)]
    return []


def periksa_jurnal_tembus():
    """
    Jurnal maju Tembus Basis harus ikut bertambah tiap hari bursa -- alasan
    yang sama dengan periksa_jurnal_pola().

    Yang diperiksa tembus_basis_hari.csv, BUKAN jurnal sinyalnya: hari tanpa
    satu pun sinyal itu wajar (aturannya ketat), dan dari berkas sinyal saja
    tidak bisa dibedakan dari hari jurnalnya tidak jalan.

    Dipanggil SEBELUM pembangunan ulang malam ini, jadi di hari bursa baru
    wajar kalau jurnalnya masih tertinggal satu hari -- itu yang akan
    dikejar tugas tembus_basis. Yang dilaporkan cuma ketertinggalan yang
    lebih dari itu: hari yang sudah pasti hilang.
    """
    try:
        from .tembus_basis import HARI_FILE, _muat_jurnal
    except Exception as exc:
        return ['tembus_basis tidak bisa dimuat: %s' % exc]
    return _jurnal_harian_tertinggal('Tembus Basis', HARI_FILE, _muat_jurnal)


def periksa_jurnal_kecondongan():
    """Sama dengan periksa_jurnal_tembus(), untuk jurnal Skor Kecondongan
    (kecondongan_hari.csv)."""
    try:
        from .kecondongan import HARI_FILE, _muat_jurnal
    except Exception as exc:
        return ['kecondongan tidak bisa dimuat: %s' % exc]
    return _jurnal_harian_tertinggal('Skor Kecondongan', HARI_FILE, _muat_jurnal)


def _jurnal_harian_tertinggal(label, hari_file, muat_jurnal):
    """Hari bursa yang sudah pasti hilang dari jurnal harian ber-berkas
    `*_hari.csv`. Tertinggal satu hari wajar (dikejar malam ini)."""
    if not os.path.exists(hari_file):
        return []              # belum pernah dijalankan -- bukan kerusakan
    try:
        _, h = muat_jurnal()
    except Exception as exc:
        return ['Jurnal %s tidak terbaca: %s' % (label, exc)]
    if h.empty:
        return ['Jurnal %s ada tapi kosong.' % label]

    hari_jurnal = str(h['tanggal'].astype(str).max())
    try:
        berkas = glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv'))
        df = pd.read_csv(max(berkas, key=os.path.getsize), usecols=['Date'])
        hari = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce').dropna()
        hari = sorted({str(d.date()) for d in hari})
    except Exception:
        return []
    lewat = [d for d in hari if d > hari_jurnal]
    if len(lewat) > 1:
        return ['Jurnal %s berhenti di %s padahal data sudah sampai %s -- %d hari '
                'bursa (%s) tidak tercatat dan tidak bisa dikejar.'
                % (label, hari_jurnal, lewat[-1], len(lewat) - 1, ', '.join(lewat[:-1][-5:]))]
    return []


def periksa_jurnal_kejadian():
    """
    Jurnal maju MSCI & Pemantauan Khusus (uji 18 Okt 2026). Beda dengan
    jurnal harian di atas, kejadiannya jarang -- yang bisa bolong adalah
    SUMBERNYA: PDF review MSCI yang gagal terunduh, nama MSCI baru yang
    belum dipetakan, atau pengumuman IDX yang lama tidak diimpor (cuma bisa
    lewat browser). Detailnya di periksa() masing-masing modul.
    """
    masalah = []
    for modul in ('msci_jurnal', 'msci_tebakan', 'pk_jurnal'):
        try:
            m = __import__('website.%s' % modul, fromlist=['x'])
            masalah += m.periksa()
        except Exception as exc:
            masalah.append('%s tidak bisa diperiksa: %s' % (modul, exc))
    return masalah


def periksa_jurnal_insider():
    """
    Dua hal, dua-duanya soal jurnal maju insider:

    1. Jurnalnya sendiri harus jalan tiap hari bursa (logika sama dengan
       periksa_jurnal_tembus: tertinggal satu hari wajar sebelum dibangun
       ulang malam ini, lebih dari itu berarti hari yang hilang).
    2. DATA insider-nya harus ditarik. Jurnal mencatat tanggal transaksi
       pertama kali TERLIHAT -- kalau scraper-nya tidak jalan, tidak ada
       yang terlihat, dan jurnal yang rajin jalan pun kosong. Ambangnya
       sengaja longgar (C['INSIDER_BASI'] = 35 hari): kebiasaan sekarang
       menarik sebulan sekali, dan pemeriksaan yang merah tiap hari untuk
       kebiasaan normal akan berhenti dibaca. Yang ditangkap cuma tarikan
       bulanan yang TERLEWAT.
    """
    try:
        from .insider_jurnal import HARI_FILE, C as CI, _muat, _tarik_terakhir
    except Exception as exc:
        return ['insider_jurnal tidak bisa dimuat: %s' % exc]
    masalah = []
    tarik = _tarik_terakhir()
    if tarik is not None:
        umur = (pd.Timestamp.now().normalize() - tarik).days
        if umur > CI['INSIDER_BASI']:
            masalah.append('Data insider terakhir ditarik %s (%d hari lalu) -- jurnal maju insider tidak '
                           'akan melihat transaksi baru sampai RUN_INSIDER_ACTIVITY_ALL dijalankan.'
                           % (tarik.strftime('%Y-%m-%d'), umur))
    if not os.path.exists(HARI_FILE):
        return masalah
    try:
        _, h = _muat()
    except Exception as exc:
        return masalah + ['Jurnal insider tidak terbaca: %s' % exc]
    if h.empty:
        return masalah + ['Jurnal insider ada tapi kosong.']
    hari_jurnal = str(h['tanggal'].astype(str).max())
    try:
        berkas = glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv'))
        df = pd.read_csv(max(berkas, key=os.path.getsize), usecols=['Date'])
        hari = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce').dropna()
        hari = sorted({str(d.date()) for d in hari})
    except Exception:
        return masalah
    lewat = [d for d in hari if d > hari_jurnal]
    if len(lewat) > 1:
        masalah.append('Jurnal insider berhenti di %s padahal data sudah sampai %s -- transaksi yang '
                       'terlihat di %d hari bursa itu tercatat dengan tanggal terlambat.'
                       % (hari_jurnal, lewat[-1], len(lewat) - 1))
    return masalah


def periksa_cache():
    """Umur tiap cache + deteksi 'segar tapi isinya basi'."""
    baris = []
    masalah = []
    umur = {}
    for t in TUGAS:
        for f in _berkas(t):
            baris.append((t['nama'], f, _umur_jam(f)))
        if _berkas(t):
            umur[t['nama']] = _umur_terburuk(t)

    for t in TUGAS:
        if not t['induk'] or not t['cache']:
            continue
        anak = umur.get(t['nama'])
        induk = umur.get(t['induk'])
        if anak is None or induk is None:
            continue
        # Anak lebih MUDA dari induk berarti anak dibangun dari induk yang
        # sudah basi -- semua indikator tampak hijau padahal isinya lusa.
        if induk > BASI_JAM and anak < induk:
            masalah.append('%s terlihat segar (%.1f jam) tapi dibangun dari %s yang '
                           'sudah %.1f jam -- angkanya lama, tampilannya baru.'
                           % (t['nama'], anak, t['induk'], induk))
    return baris, masalah


# ---------------------------------------------------------------------------
# PEMBANGUNAN
# ---------------------------------------------------------------------------
def _jalankan_satu(nama):
    """
    Jalankan SATU tugas. Dipanggil di proses anak, jadi harus fungsi
    tingkat-modul (bisa di-pickle) dan tidak boleh bergantung pada apa pun
    yang hidup di proses induk -- termasuk app context Flask. Aman: tidak
    satu pun tugas di TUGAS menyentuh basis data, semuanya membaca berkas
    dan menulis pickle.
    """
    for t in TUGAS:
        if t['nama'] != nama:
            continue
        t0 = time.time()
        try:
            t['jalan']()
            return (nama, 'ok', '', time.time() - t0)
        except Exception as exc:
            return (nama, 'GAGAL', '%s: %s' % (type(exc).__name__, exc), time.time() - t0)
    return (nama, 'GAGAL', 'tugas tidak dikenal', 0.0)


def _rencana(hanya=None, cepat=False, lewati_segar=False):
    """
    Tentukan tugas mana yang jalan, mana yang dilewati, dan siapa menunggu
    siapa. Dipakai jalur seri maupun paralel supaya keputusannya identik.
    """
    jalan, lewat = [], []
    for t in TUGAS:
        if hanya and t['nama'] not in hanya:
            continue
        if cepat and t['nama'] == 'broker_ledger':
            lewat.append((t['nama'], 'dilewati', '--cepat', 0.0))
            continue
        jalan.append(t)

    nama_jalan = {t['nama'] for t in jalan}
    if lewati_segar:
        tetap = []
        for t in jalan:
            # Induk ikut dibangun -> anak WAJIB ikut, walau umurnya masih muda.
            wajib = t['induk'] in nama_jalan
            u = _umur_terburuk(t) if t['cache'] else None
            if not wajib and u is not None and u < BASI_JAM:
                lewat.append((t['nama'], 'dilewati', 'masih segar (%.1f jam)' % u, 0.0))
                continue
            tetap.append(t)
        jalan = tetap
        nama_jalan = {t['nama'] for t in jalan}

    return jalan, lewat, nama_jalan


def bangun_paralel(hanya=None, cepat=False, lewati_segar=False, pekerja=4):
    """
    Sama dengan bangun(), tapi tugas yang tidak saling bergantung jalan
    berbarengan di proses terpisah.

    KENAPA BOLEH PARALEL
    Dari 15 tugas hanya 2 yang punya induk: modal_bandar dan sidik_jari,
    keduanya menunggu broker_ledger. Sisanya membaca berkas Summary atau
    cache-nya sendiri dan tidak saling menyentuh -- sudah diperiksa: tidak
    ada dua tugas yang menulis berkas cache yang sama, dan satu-satunya
    impor silang (signal_recall -> kering_screener) cuma meminjam konstanta,
    bukan cache-nya.

    KENAPA PROSES, BUKAN THREAD
    Semuanya pekerjaan pandas yang terikat CPU. Thread cuma akan berebut
    GIL dan tidak menghemat apa pun.

    URUTAN LAPORAN tetap mengikuti urutan TUGAS, bukan urutan selesai --
    laporan harian yang barisnya berpindah-pindah tiap hari sulit dibaca
    sekilas.
    """
    from concurrent.futures import ProcessPoolExecutor

    jalan, hasil, nama_jalan = _rencana(hanya, cepat, lewati_segar)
    if not jalan:
        return hasil

    menunggu = {t['nama']: t['induk'] for t in jalan
                if t['induk'] and t['induk'] in nama_jalan}
    siap = [t['nama'] for t in jalan if t['nama'] not in menunggu]

    from concurrent.futures.process import BrokenProcessPool

    try:
        with ProcessPoolExecutor(max_workers=max(1, pekerja)) as pool:
            berjalan = {pool.submit(_jalankan_satu, n): n for n in siap}
            while berjalan:
                selesai = next(f for f in list(berjalan) if f.done()) if any(
                    f.done() for f in berjalan) else None
                if selesai is None:
                    # Tidak ada yang selesai: tunggu yang mana pun.
                    from concurrent.futures import wait, FIRST_COMPLETED
                    wait(list(berjalan), return_when=FIRST_COMPLETED)
                    continue
                nama = berjalan.pop(selesai)
                hasil.append(selesai.result())
                sukses = hasil[-1][1] == 'ok'
                for anak, induk in list(menunggu.items()):
                    if induk != nama:
                        continue
                    menunggu.pop(anak)
                    if sukses:
                        berjalan[pool.submit(_jalankan_satu, anak)] = anak
                    else:
                        hasil.append((anak, 'GAGAL',
                                      'induk %s gagal -- tidak dijalankan' % induk, 0.0))
    except BrokenProcessPool:
        # Proses anak mati mendadak -- di Windows biasanya karena memori
        # virtual habis ("paging file is too small") saat anak mengimpor
        # numpy. Satu anak mati merusak seluruh pool, jadi tugas yang belum
        # tercatat dilanjut seri di proses ini: lebih lambat, tapi cuma satu
        # salinan pandas di memori dan laporan tetap keluar.
        sudah = {r[0] for r in hasil}
        sisa = [t['nama'] for t in jalan if t['nama'] not in sudah]
        print('  ! pool paralel rusak (proses anak mati) -- %d tugas sisa dilanjut seri'
              % len(sisa))
        if sisa:
            hasil.extend(bangun(hanya=sisa, cepat=cepat))

    urut = {t['nama']: i for i, t in enumerate(TUGAS)}
    hasil.sort(key=lambda r: urut.get(r[0], 999))
    return hasil


def bangun(hanya=None, cepat=False, lewati_segar=False):
    hasil = []
    dibangun = set()
    for t in TUGAS:
        if hanya and t['nama'] not in hanya:
            continue
        if cepat and t['nama'] == 'broker_ledger':
            hasil.append((t['nama'], 'dilewati', '--cepat', 0.0))
            continue
        # Induk baru dibangun -> anak WAJIB ikut, walau umurnya masih muda.
        wajib = t['induk'] in dibangun
        if lewati_segar and not wajib and t['cache']:
            u = _umur_terburuk(t)
            if u is not None and u < BASI_JAM:
                hasil.append((t['nama'], 'dilewati', 'masih segar (%.1f jam)' % u, 0.0))
                continue
        t0 = time.time()
        try:
            t['jalan']()
            hasil.append((t['nama'], 'ok', '', time.time() - t0))
            dibangun.add(t['nama'])
        except Exception as exc:
            hasil.append((t['nama'], 'GAGAL', '%s: %s' % (type(exc).__name__, exc),
                          time.time() - t0))
            traceback.print_exc(limit=2)
    return hasil


def laporan(periksa_saja=False, hanya=None, cepat=False, lewati_segar=False, paralel=True, pekerja=4):
    print('=' * 72)
    print('PEMERIKSAAN KESEHATAN  %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    print('=' * 72)

    info, masalah_data = periksa_data()
    print('\n[DATA]')
    print('  hari broker terakhir : %s (%s berkas, %s tanpa baris broker)'
          % (info.get('hari_terakhir'), info.get('n_berkas'),
             info.get('n_tanpa_broker')))
    print('  emiten di Summary    : %s, tanggal terbaru %s'
          % (info.get('n_emiten_summary'), info.get('tanggal_terbaru')))
    tg = info.get('tertinggal') or []
    print('  tertinggal >30 hari  : %d emiten%s'
          % (len(tg), (' (' + ', '.join('%s:%dh' % x for x in tg[:6]) + ')') if tg else ''))
    ok = info.get('baris_ohlc_kosong') or []
    print('  baris Close kosong   : %d emiten' % len(ok))

    masalah_own = periksa_kepemilikan()
    print('  kepemilikan          : %s'
          % ('dua jalur sepakat' if not masalah_own else '%d selisih' % len(masalah_own)))

    masalah_inv = (periksa_ledger() + periksa_live_scan() + periksa_jurnal_pola()
                   + periksa_jurnal_tembus() + periksa_jurnal_kecondongan()
                   + periksa_jurnal_insider() + periksa_jurnal_kejadian() + periksa_baseline())
    print('  invarian             : %s'
          % ('buku besar, live_scan, jurnal pola/tembus/kecondongan/insider/MSCI/PK, baseline konsisten'
             if not masalah_inv
             else '%d pelanggaran' % len(masalah_inv)))
    try:
        from .insider_jurnal import _tarik_terakhir
        tarik = _tarik_terakhir()
        if tarik is not None:
            print('  insider ditarik      : %s (%d hari lalu)'
                  % (tarik.strftime('%Y-%m-%d'), (pd.Timestamp.now().normalize() - tarik).days))
    except Exception:
        pass

    baris_cache, masalah_cache = periksa_cache()
    print('\n[CACHE]')
    print('  %-18s %-30s %10s' % ('nama', 'berkas', 'umur'))
    for nama, berkas, u in baris_cache:
        print('  %-18s %-30s %s'
              % (nama, berkas, ('%.1f jam' % u) if u is not None else 'belum ada'))

    semua = masalah_data + masalah_own + masalah_inv + masalah_cache
    print('\n[MASALAH]  %d' % len(semua))
    for m in semua:
        print('  - %s' % m)
    if not semua:
        print('  (tidak ada)')

    if periksa_saja:
        print('\n--periksa: tidak ada yang dibangun.')
        return semua

    print('\n[BANGUN ULANG]  %s'
          % ('%d proses paralel, urutan ketergantungan dipertahankan' % pekerja
             if paralel else 'seri, urutan ketergantungan dipertahankan'))
    t_bangun = time.time()
    if paralel:
        hasil = bangun_paralel(hanya=hanya, cepat=cepat,
                               lewati_segar=lewati_segar, pekerja=pekerja)
    else:
        hasil = bangun(hanya=hanya, cepat=cepat, lewati_segar=lewati_segar)
    print('  %-18s %-9s %9s  %s' % ('nama', 'status', 'durasi', 'catatan'))
    total = 0.0
    gagal = []
    for nama, status, catatan, dur in hasil:
        total += dur
        if status == 'GAGAL':
            gagal.append(nama)
        print('  %-18s %-9s %8.1fs  %s' % (nama, status, dur, catatan))
    if paralel and not periksa_saja:
        print('\n  jam dinding %.1f menit (jumlah kerja %.1f menit) | gagal: %s'
              % ((time.time() - t_bangun) / 60.0, total / 60.0, ', '.join(gagal) or 'tidak ada'))
    else:
        print('\n  total %.1f menit | gagal: %s' % (total / 60.0, ', '.join(gagal) or 'tidak ada'))

    _, masalah_cache2 = periksa_cache()
    if masalah_cache2:
        print('\n[MASIH BERMASALAH SETELAH DIBANGUN]')
        for m in masalah_cache2:
            print('  - %s' % m)
    return semua + [('gagal: %s' % g) for g in gagal]


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Periksa data & bangun ulang semua cache.')
    ap.add_argument('--periksa', action='store_true', help='periksa saja, tanpa membangun')
    ap.add_argument('--cepat', action='store_true', help='lewati broker_ledger (~2 menit)')
    ap.add_argument('--lewati-segar', action='store_true',
                    help='lewati cache yang masih di bawah %d jam (anak tetap ikut '
                         'kalau induknya dibangun)' % BASI_JAM)
    ap.add_argument('--hanya', nargs='*', help='hanya bangun tugas bernama ini')
    ap.add_argument('--seri', action='store_true',
                    help='bangun satu per satu, bukan paralel (untuk menelusuri kegagalan)')
    ap.add_argument('--pekerja', type=int, default=4, help='jumlah proses paralel (bawaan 4)')
    a = ap.parse_args()

    from . import create_app
    app = create_app()
    with app.app_context():
        sisa = laporan(periksa_saja=a.periksa, hanya=a.hanya,
                       cepat=a.cepat, lewati_segar=a.lewati_segar,
                       paralel=not a.seri, pekerja=a.pekerja)
    sys.exit(1 if sisa else 0)
