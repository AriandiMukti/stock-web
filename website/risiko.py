"""
Takaran Risiko: seberapa keras sebuah emiten akan berayun, bukan ke mana.

KENAPA MODUL INI ADA
Sembilan belas menu di app ini menjawab pertanyaan yang sama: "layak beli
atau tidak". Tidak ada satu pun yang menjawab "kalau dibeli, seberapa
besar". Padahal dari seluruh pengujian yang pernah dilakukan di app ini,
cuma pertanyaan kedua yang datanya sanggup jawab.

Diukur di dua sampel terpisah (kalibrasi 2026, 788 emiten; luar sampel
2016-2025, 21 emiten), korelasi antar-sampel:

    yang diramal                       korelasi 2026 vs 2016-2025
    peluang kena guncangan -20%              +0,87
    peluang lonjakan +30%                    +0,91
    ARAH (naik atau turun)                   -0,14 s/d -0,31

Arah tidak cuma sulit diramal -- korelasinya NEGATIF, artinya daftar
juara satu periode menyesatkan di periode lain (lihat catatan panjang di
pattern_miner.py dan broker_fingerprint.py). Besaran ayunan sebaliknya:
stabil, dan stabilnya bertahan sepuluh tahun.

YANG DITAMPILKAN KELIPATAN, BUKAN PERSENTASE MENTAH -- INI PENTING
Peluang absolutnya sangat bergantung rezim. Peluang sebuah emiten kena
-20% dalam 40 hari:

    di kalibrasi 2026 (pasar liar)  : 57,6% rata-rata
    di 2016-2025 (sepuluh tahun)    : 17,1% rata-rata

Tiga kali lipat bedanya. Jadi menampilkan "peluang rugi 66%" sebagai
angka tunggal akan salah besar begitu rezimnya berganti. Yang REPLIKASI
adalah kelipatannya terhadap pasar saat itu:

    korelasi kelipatan risiko  antar sampel : +0,90
    korelasi kelipatan peluang antar sampel : +0,95

Karena itu angka utama di modul ini "1,4x lebih berisiko dari emiten
biasa", bukan "81,7% peluang rugi". Persentase mentah tetap ditampilkan
tapi SELALU berpasangan dengan rezim asalnya, supaya tidak dibaca sebagai
ramalan.

KENAPA DUA UKURAN INI, BUKAN BETA ATAU ATR
Beta butuh 60 hari return untuk berubah karakter dan mengukur hubungan
dengan pasar, bukan besar ayunannya sendiri. ATR mengukur ayunan tapi
buta terhadap posisi harga. Dua sumbu di bawah dipilih karena keduanya
lolos di dua sampel DAN saling melengkapi: volatilitas menangkap
"seberapa liar sekarang", jarak dari puncak menangkap "seberapa jauh
sudah jatuh" -- dan sel paling ekstrem (liar DAN baru jatuh dalam)
punya kelipatan PELUANG lebih besar daripada kelipatan RISIKO, satu-
satunya sel yang begitu. Itu sel yang sama dengan temuan jatuh_dalam.py,
ditemukan lewat ukuran yang sama sekali berbeda.

BATASNYA -- BACA SEBELUM MEMAKAI
- Ini bukan ramalan untuk satu emiten. Angkanya kecondongan KELOMPOK
  tempat emiten itu berada hari ini.
- Semesta luar sampelnya cuma 21 emiten besar yang semuanya masih hidup
  sampai hari ini. Untuk sisi RISIKO itu bias yang menguntungkan
  (yang jatuh lalu mati hilang dari hitungan), jadi angka risiko
  sebenarnya kemungkinan LEBIH BURUK dari yang tertulis, bukan lebih
  baik. Lihat survivorship.py.
- Tidak ada kaitannya dengan arah. Sel dengan peluang lonjakan tertinggi
  juga punya risiko guncangan tertinggi; keduanya satu tuas yang sama
  (korelasi peluang-naik vs risiko-rugi antar sel: +0,65 di 2026, +0,88
  di 2016-2025). "Risiko kecil tapi potensi besar" tidak ada di data ini.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import logging
import os
import pickle

import numpy as np
import pandas as pd

from .config import DAILY_PATH

logger = logging.getLogger(__name__)

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'risiko_cache.pkl'))

C = {
    'HOR': 40,            # horizon pengukuran, hari bursa
    'RUGI': 20.0,         # ambang guncangan (%), disentuh kapan saja dalam horizon
    'NAIK': 30.0,         # ambang lonjakan (%), disentuh kapan saja dalam horizon
    'VOL_W': 20,          # jendela volatilitas harian
    'PUNCAK_W': 60,       # jendela puncak acuan -- 60, mengikuti jatuh_dalam.py
    'LIKUID_MIN': 1e9,    # Rp1 M/hari; di bawah ini eksekusi jadi masalah sendiri
}

# BATASNYA TETAP, BUKAN KUANTIL -- DAN ITU DISENGAJA.
# Kuantil lintas-saham per hari tidak bisa dipakai: ia berubah arti setiap
# hari (emiten yang sama bisa pindah keranjang tanpa berubah apa pun) dan
# tidak bisa dihitung di sampel luar yang cuma berisi 21 emiten. Batas
# tetap membuat sel yang sama berarti hal yang sama di kedua sampel --
# itulah sebabnya tabel di bawah bisa diuji silang sama sekali.
VOL_BIN = [0, 1.5, 2.5, 3.5, 5.0, 1e9]
VOL_LAB = ['<1,5%', '1,5-2,5%', '2,5-3,5%', '3,5-5%', '>5%']
DD_BIN = [-1.01, -0.40, -0.20, 1e9]
DD_LAB = ['jatuh >40%', 'jatuh 20-40%', 'dekat puncak']

# Kelipatan terhadap rata-rata pasar pada sampelnya masing-masing.
# (kelipatan_risiko, kelipatan_peluang) -- rata-rata dua sampel, supaya
# tidak ada satu periode pun yang menentukan sendirian.
#   n_26 / n_16 = jumlah pengamatan di tiap sampel, ditampilkan supaya
#   sel bersampel tipis ketahuan.
GRID = {
    ('<1,5%',     'dekat puncak'): {'x_rugi': 0.37, 'x_naik': 0.16, 'n26': 973,  'n16': 5222},
    ('1,5-2,5%',  'jatuh 20-40%'): {'x_rugi': 0.95, 'x_naik': 0.57, 'n26': 986,  'n16': 2181},
    ('1,5-2,5%',  'dekat puncak'): {'x_rugi': 0.63, 'x_naik': 0.52, 'n26': 2084, 'n16': 11621},
    ('2,5-3,5%',  'jatuh 20-40%'): {'x_rugi': 1.08, 'x_naik': 0.74, 'n26': 1198, 'n16': 1970},
    ('2,5-3,5%',  'dekat puncak'): {'x_rugi': 0.94, 'x_naik': 0.69, 'n26': 1311, 'n16': 7473},
    ('3,5-5%',    'jatuh >40%'):   {'x_rugi': 1.43, 'x_naik': 2.63, 'n26': 723,  'n16': 245},
    ('3,5-5%',    'jatuh 20-40%'): {'x_rugi': 1.29, 'x_naik': 1.01, 'n26': 1464, 'n16': 1571},
    ('3,5-5%',    'dekat puncak'): {'x_rugi': 1.20, 'x_naik': 1.06, 'n26': 1060, 'n16': 3950},
    ('>5%',       'jatuh >40%'):   {'x_rugi': 1.45, 'x_naik': 2.73, 'n26': 2042, 'n16': 403},
    ('>5%',       'jatuh 20-40%'): {'x_rugi': 1.32, 'x_naik': 1.47, 'n26': 1862, 'n16': 983},
    ('>5%',       'dekat puncak'): {'x_rugi': 1.75, 'x_naik': 1.55, 'n26': 1034, 'n16': 2384},
}

# Empat sel tidak punya pengamatan cukup di kedua sampel, semuanya di
# pojok "tenang tapi sudah jatuh dalam". Itu bukan kebetulan: emiten yang
# baru jatuh 40% hampir tidak pernah tenang.
#
# Sel kosong diisi rata-rata BARIS dan KOLOM, bukan baris saja. Versi
# pertama memakai baris saja dan hasilnya salah arah: MYOR (volat 1,3%,
# sudah jatuh 24%) mendapat 0,37x -- angka milik sel "dekat puncak",
# satu-satunya sel terisi di barisnya -- padahal kolom "jatuh 20-40%"
# rata-ratanya 1,16x. Mengambil keduanya memberi 0,77x, yang menghormati
# dua sumbu sekaligus. Sel hasil isian SELALU ditandai `interpolasi`
# supaya tidak dibaca setara dengan sel yang benar-benar diukur.
def _cari_sel(vlab, dlab):
    sel = GRID.get((vlab, dlab))
    if sel:
        return dict(sel, interpolasi=False)
    baris = [v for (vv, _), v in GRID.items() if vv == vlab]
    kolom = [v for (_, dd), v in GRID.items() if dd == dlab]
    if not baris and not kolom:
        return None

    def campur(kunci):
        bagian = []
        if baris:
            bagian.append(float(np.mean([s[kunci] for s in baris])))
        if kolom:
            bagian.append(float(np.mean([s[kunci] for s in kolom])))
        return round(float(np.mean(bagian)), 2)

    return {'x_rugi': campur('x_rugi'), 'x_naik': campur('x_naik'),
            'n26': 0, 'n16': 0, 'interpolasi': True}

# Peluang absolut rata-rata pasar di tiap sampel. Dipakai HANYA untuk
# menerjemahkan kelipatan jadi persentase, dan selalu ditampilkan
# berpasangan dengan nama rezimnya.
BASELINE = {
    '2026': {'rugi': 57.6, 'naik': 18.1, 'label': 'pasar liar seperti 2026'},
    '2016-2025': {'rugi': 17.1, 'naik': 20.1, 'label': 'pasar biasa seperti 2016-2025'},
}

# Angka hasil pengujian, ditaruh di sini supaya halaman menampilkan yang
# SAMA PERSIS dengan docstring -- bukan diketik ulang di template dan
# menyimpang diam-diam. Konvensi yang sama dipakai jatuh_dalam.BUKTI.
BUKTI = {
    'sampel_kalibrasi': '788 emiten, Jan-Sep 2026 (semesta penuh, termasuk emiten kecil)',
    'sampel_luar': '21 emiten, 2016-2025 (folder Test, periode & semesta terpisah)',
    'horizon': 'peluang MENYENTUH ambang kapan saja dalam 40 hari bursa, dihitung dari high/low',
    'replikasi': [
        {'yang_diramal': 'Peringkat risiko guncangan -20%', 'korelasi': 0.87},
        {'yang_diramal': 'Peringkat peluang lonjakan +30%', 'korelasi': 0.91},
        {'yang_diramal': 'Kelipatan risiko terhadap pasar', 'korelasi': 0.90},
        {'yang_diramal': 'Kelipatan peluang terhadap pasar', 'korelasi': 0.95},
        {'yang_diramal': 'ARAH return (pembanding)', 'korelasi': -0.31},
    ],
    'replikasi_catatan': (
        'Baris terakhir pembanding, bukan bagian modul ini. Diuji 16.000 kombinasi '
        'syarat masuk x aturan keluar: yang unggul di 2026 cuma 32-39% yang masih '
        'unggul di 2016-2025, di bawah lempar koin. Arah tidak sekadar sulit diramal '
        '-- peringkatnya menyesatkan. Besaran ayunan justru stabil.'),
    'regime': [
        {'rezim': 'Kalibrasi 2026 (788 emiten)', 'rugi': 57.6, 'naik': 18.1},
        {'rezim': 'Luar sampel 2016-2025 (21 emiten)', 'rugi': 17.1, 'naik': 20.1},
    ],
    'regime_catatan': (
        'Peluang absolut berbeda tiga kali lipat antar rezim, jadi persentase mentah '
        'TIDAK boleh dibaca sebagai ramalan. Yang replikasi kelipatannya, bukan '
        'levelnya -- itu sebabnya angka utama di halaman ini kelipatan.'),
    'satu_tuas': (
        'Peluang lonjakan dan risiko guncangan bergerak bersama: korelasi antar sel '
        '+0,65 di 2026 dan +0,88 di 2016-2025. Tidak ada kelompok "risiko kecil tapi '
        'potensi besar" — yang ada cuma pilihan titik di satu tuas. Satu-satunya sel '
        'yang kelipatan peluangnya melebihi kelipatan risikonya adalah "liar + baru '
        'jatuh >40%" (2,6-2,7x peluang lawan 1,4x risiko) — sel yang sama dengan '
        'temuan jatuh_dalam.py, ditemukan lewat ukuran yang berbeda.'),
    'survivorship': (
        'Semesta luar sampel 21 emiten yang semuanya masih diperdagangkan hari ini. '
        'Emiten yang jatuh lalu disuspend permanen tidak terwakili, jadi angka RISIKO '
        'di sini kemungkinan terlalu optimistis, bukan terlalu pesimistis. '
        'Lihat Emiten Hilang (survivorship.py) untuk ukurannya.'),
}


def _label_risiko(x_rugi):
    if x_rugi is None:
        return 'tidak diketahui', 'netral'
    if x_rugi >= 1.40:
        return 'sangat liar', 'merah'
    if x_rugi >= 1.10:
        return 'liar', 'oranye'
    if x_rugi >= 0.85:
        return 'sedang', 'kuning'
    if x_rugi >= 0.55:
        return 'tenang', 'hijau'
    return 'sangat tenang', 'hijau'


def _muat(stock):
    """Baca satu Summary; None kalau tidak ada / tidak cukup panjang."""
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock.upper())
    if not os.path.exists(path):
        return None
    KOL = ['Date', 'High', 'Low', 'Close', 'Volume', 'Avg Price']
    try:
        # [KOL] WAJIB: usecols mengembalikan kolom dalam urutan BERKAS, bukan
        # urutan daftar. Tanpa ini nama kolom tertukar diam-diam.
        d = pd.read_csv(path, usecols=KOL)[KOL]
    except Exception:
        return None
    d.columns = ['date', 'high', 'low', 'close', 'volume', 'avgp']
    d['date'] = pd.to_datetime(d['date'], format='%d-%b-%y', errors='coerce')
    d = d.dropna(subset=['date']).sort_values('date')
    for c in ['high', 'low', 'close', 'volume', 'avgp']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d[d['close'] > 0]
    return d if len(d) >= C['PUNCAK_W'] else None


def _ukur(d):
    """vol20, dari_puncak60, dan nilai transaksi 20 hari dari satu Summary."""
    r = d['close'].pct_change()
    vol = float(r.tail(C['VOL_W']).std() * 100) if r.tail(C['VOL_W']).notna().sum() >= 12 else None
    puncak = float(d['close'].tail(C['PUNCAK_W']).max())
    close = float(d['close'].iloc[-1])
    dari = (close / puncak - 1) if puncak > 0 else None
    nilai = d['avgp'] * d['volume']
    adv = float(nilai.tail(20).mean()) if nilai.tail(20).notna().sum() >= 12 else None
    return vol, dari, close, adv


def _keranjang(vol, dari):
    if vol is None or dari is None or not np.isfinite(vol) or not np.isfinite(dari):
        return None, None
    v = pd.cut([vol], VOL_BIN, labels=VOL_LAB)[0]
    dd = pd.cut([dari], DD_BIN, labels=DD_LAB)[0]
    return (str(v) if v is not None and not pd.isna(v) else None,
            str(dd) if dd is not None and not pd.isna(dd) else None)


def untuk_ticker(stock, df=None):
    """
    Takaran risiko satu emiten. Dipakai stock_hub, digest, dan rontgen
    portofolio -- semuanya harus menampilkan angka yang sama, jadi
    perhitungannya cuma ada di sini.
    """
    d = df if df is not None else _muat(stock)
    if d is None:
        return None
    vol, dari, close, adv = _ukur(d)
    vlab, dlab = _keranjang(vol, dari)
    if not vlab or not dlab:
        return None
    sel = _cari_sel(vlab, dlab)
    if not sel:
        return None
    label, warna = _label_risiko(sel['x_rugi'])
    peluang = {}
    for nama, b in BASELINE.items():
        peluang[nama] = {
            'label': b['label'],
            'rugi': round(min(b['rugi'] * sel['x_rugi'], 99.0), 1),
            'naik': round(min(b['naik'] * sel['x_naik'], 99.0), 1),
        }
    return {
        'stock': stock.upper(),
        'harga': close,
        'volat': round(vol, 2),
        'dari_puncak': round(dari * 100, 1),
        'keranjang_volat': vlab,
        'keranjang_jatuh': dlab,
        'x_rugi': sel['x_rugi'],
        'x_naik': sel['x_naik'],
        'interpolasi': sel.get('interpolasi', False),
        'n_kalibrasi': sel.get('n26', 0),
        'n_luar': sel.get('n16', 0),
        'adv': adv,
        'label': label,
        'verdict': warna,
        'peluang': peluang,
        # Ukuran posisi yang menyamakan risiko: berapa persen dari ukuran
        # normal supaya sumbangan risikonya sama dengan emiten rata-rata.
        'ukuran_setara': round(100.0 / sel['x_rugi']) if sel['x_rugi'] else None,
    }


def _sumber_terbaru():
    from .kesegaran import summary_terbaru
    return summary_terbaru()


def scan(force=False):
    """Takaran risiko seluruh emiten likuid. Cache mtime-keyed."""
    if not force:
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            if cached.get('ts', 0) >= _sumber_terbaru():
                return cached['hasil']
        except Exception:
            pass

    import glob
    baris = []
    dilewati_tipis = 0
    for path in glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')):
        stock = os.path.basename(path).split('_')[0].upper()
        try:
            d = _muat(stock)
            if d is None:
                continue
            r = untuk_ticker(stock, df=d)
            if not r:
                continue
            if not r['adv'] or r['adv'] < C['LIKUID_MIN']:
                dilewati_tipis += 1
                continue
            baris.append(r)
        except Exception:
            logger.exception('Takaran risiko gagal untuk %s', stock)

    baris.sort(key=lambda x: (-x['x_naik'], x['x_rugi']))
    hasil = {
        'available': True,
        'baris': baris,
        'jumlah': len(baris),
        'dilewati_tipis': dilewati_tipis,
        'bukti': BUKTI,
        'grid': [dict(volat=k[0], jatuh=k[1], **v) for k, v in GRID.items()],
        'config': C,
    }
    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'ts': _sumber_terbaru(), 'hasil': hasil}, fh)
    except Exception:
        logger.exception('Gagal menulis cache Takaran Risiko')
    return hasil
