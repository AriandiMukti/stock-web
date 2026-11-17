"""
Serapan float: akumulasi bersih Top5 diukur terhadap saham yang benar-benar
beredar elektronik (scripless KSEI).

KENAPA INI ADA
Dua aset data terbesar app ini -- arus broker harian (Summary CSV) dan
kepemilikan KSEI (ownership.py) -- selama ini hidup di dua menu terpisah
dan tidak pernah dikalikan. "Top5 net beli 2 juta lot" tidak berarti apa-apa
sampai dibandingkan dengan berapa banyak saham yang sebenarnya ada untuk
dibeli. Rasio itulah yang dihitung di sini:

    serapan% = (Σ Net Top5 All Lot selama N hari x 100 lembar) / scripless

TESIS AWALNYA SALAH, DAN ITU HASIL UTAMANYA
Modul ini dibangun dengan hipotesis "float mengering": makin besar porsi
float yang diserap, makin ketat suplainya, makin besar peluang harga naik.
Hipotesis itu DIUJI DULU sebelum dipakai, dan datanya menolaknya.

7.467 pengamatan, 856 emiten, jendela akumulasi 40 hari, periode Jan-Sep 2026
(pasar turun -- semua angka absolut negatif, jadi yang berarti adalah
selisih terhadap baseline, bukan tanda plus/minusnya):

  Return 40 hari, syarat "akumulasi diam-diam" (harga bergerak -10%..+10%):
    kelompok            n      rata2    median   win%
    baseline         2993     -8,57     -8,50   24,0
    <=0 (distribusi) 1837    -10,08     -9,46   20,7   <- paling buruk
    0 - 0,5%         1019     -6,02     -6,54   29,7   <- paling baik
    0,5 - 1%           80     -9,83    -10,80   26,2
    1 - 2%             45     -5,45     -5,00   17,8   <- win rate terburuk

Kesimpulannya: YANG BERARTI ADALAH TANDANYA, BUKAN BESARNYA.
- Top5 net JUAL terhadap float = kelompok paling buruk, konsisten di semua
  horizon (20/40/60 hari) dan di semua irisan yang diuji.
- Serapan ringan (0-0,5% float) justru kelompok terbaik, konsisten unggul
  ~3-6 poin persen win rate di atas baseline.
- Serapan berat (>1%) TIDAK lebih baik. Rata-ratanya kadang naik karena
  ekor kanan gemuk (sesekali ada pemenang besar), tapi median dan win
  rate-nya di bawah kelompok ringan. Sampelnya kecil (n=45-82), jadi ini
  bukan bukti kuat bahwa serapan berat itu buruk -- tapi jelas tidak ada
  bukti bahwa ia lebih baik.

Jadi halaman ini bukan pencari sinyal beli. Gunanya menyaring: menandai
emiten yang bandarnya sedang MELEPAS relatif terhadap float (kelompok yang
rekam jejaknya paling buruk), dan menempatkan sisanya pada skalanya.

PENYEBUTNYA SCRIPLESS, BUKAN SAHAM TERCATAT
KSEI hanya "melihat" saham yang tercatat elektronik (C-BEST); saham warkat
tidak punya rincian dan praktis tidak berpindah tangan harian. Free float
resmi (Peraturan I-A) sebenarnya penyebut yang lebih tepat, tapi cuma
tersedia untuk 43 dari 1.010 emiten (4%), jadi tidak bisa jadi penyebut
utama. Untuk emiten yang pemegang besarnya menyimpan saham di scripless,
float sesungguhnya lebih kecil, sehingga angka di sini adalah BATAS BAWAH.

BATAS LAIN
- "Top5" bukan satu pihak. Komposisi lima broker teratas berganti tiap hari,
  jadi ini bukan bukti satu bandar mengumpulkan, melainkan ukuran seberapa
  terkonsentrasi penyerapan.
- Periode ujinya hanya ~8 bulan dan didominasi pasar turun.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import pickle
import time

import pandas as pd

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'float_squeeze_cache.pkl'))
def _sumber_terbaru():
    """Summary + seluruh pohon kepemilikan (scripless dari KSEI)."""
    from .kesegaran import summary_terbaru, kepemilikan_terbaru, paling_baru
    return paling_baru(summary_terbaru(), kepemilikan_terbaru())

LOT = 100.0  # 1 lot = 100 lembar

# Ambang diturunkan dari distribusi nyata (633 emiten likuid, jendela 60
# hari): p50 = -0,05%, p75 = 0,02%, p90 = 0,25%, p95 = 0,68%, p99 = 1,71%.
# Tebakan awal 7%/15% tidak pernah tercapai oleh satu emiten pun -- net
# Top5 sebagian besar saling meniadakan sepanjang waktu.
C = {
    'DAYS': 60,
    # Proporsional terhadap jendela, bukan angka tetap -- versi awal memakai
    # 40 baris mati, yang membuat pilihan jendela 20 hari menyaring habis
    # SELURUH emiten (tidak ada yang punya 40 baris di dalam 20 hari).
    'MIN_ROW_RATIO': 0.7,
    'MIN_ROWS_FLOOR': 12,
    'MIN_ADV_VALUE': 200e6,   # Rp200 juta/hari
    'BERAT': 0.5,             # >= ini: serapan berat (p95 ~ 0,68%)
    'RINGAN': 0.0,            # > ini: serapan ringan -- kelompok terbaik historisnya
    'CHURN_DTC': 60.0,        # days-to-cover di atas ini: kemungkinan perputaran
}

# Ditempelkan ke UI apa adanya supaya angkanya bisa dibaca pengguna, bukan
# cuma jadi label. Sumber: calib2.py, jendela akumulasi 40 hari, return 40
# hari, irisan "akumulasi diam-diam" (drift harga -10%..+10%).
KALIBRASI = {
    'jendela_akumulasi': 40,
    'horizon': 40,
    'irisan': 'akumulasi diam-diam (drift harga -10% s.d. +10%)',
    'periode': 'Jan - Sep 2026',
    'n_total': 2993,
    'baris': [
        {'kelompok': 'baseline (semua)', 'n': 2993, 'rata2': -8.57, 'median': -8.50, 'win': 24.0},
        {'kelompok': 'distribusi (<=0%)', 'n': 1837, 'rata2': -10.08, 'median': -9.46, 'win': 20.7},
        {'kelompok': 'serapan ringan (0-0,5%)', 'n': 1019, 'rata2': -6.02, 'median': -6.54, 'win': 29.7},
        {'kelompok': 'serapan sedang (0,5-1%)', 'n': 80, 'rata2': -9.83, 'median': -10.80, 'win': 26.2},
        {'kelompok': 'serapan berat (1-2%)', 'n': 45, 'rata2': -5.45, 'median': -5.00, 'win': 17.8},
    ],
}

LABELS = {
    'distribusi': 'Bandar melepas',
    'ringan': 'Serapan ringan',
    'berat': 'Serapan berat',
}

# Warna mengikuti temuan, bukan intuisi: melepas = merah, ringan = hijau,
# berat = kuning (tidak terbukti lebih baik, jadi tidak boleh hijau).
VERDICTS = {
    'distribusi': 'merah',
    'ringan': 'hijau',
    'berat': 'kuning',
}


def classify(pct):
    if pct is None:
        return 'distribusi'
    if pct <= C['RINGAN']:
        return 'distribusi'
    if pct < C['BERAT']:
        return 'ringan'
    return 'berat'


def scripless_map():
    """
    {ticker: {'scripless': lembar, 'sec_num': lembar, 'month': '2026-08'}}
    dari bulan KSEI terakhir yang memuat ticker itu.

    Dibaca sekali untuk seluruh bursa -- jauh lebih ringan daripada memanggil
    build_ownership() 881 kali (yang juga menarik registri IDX, LBRPE dan
    overrides yang tidak dibutuhkan di sini).
    """
    from .ownership import load_ksei_months

    out = {}
    for payload in load_ksei_months():  # urut lama -> baru
        month = payload.get('month')
        for ticker, rec in (payload.get('securities') or {}).items():
            scripless = (rec.get('local_total') or 0.0) + (rec.get('foreign_total') or 0.0)
            if scripless <= 0:
                continue
            out[ticker] = {'scripless': scripless,
                           'sec_num': rec.get('sec_num') or 0.0,
                           'month': month}
    return out


def _read(stock):
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if 'Date' not in df.columns or df.empty:
        return None
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
    return df if len(df) else None


def measure(stock, days=None, scripless_info=None, df=None):
    """Hitung serapan float satu emiten. None kalau datanya tidak cukup."""
    days = days or C['DAYS']
    if df is None:
        df = _read(stock)
    if df is None:
        return None

    if scripless_info is None:
        scripless_info = scripless_map().get(stock)
    if not scripless_info or not scripless_info.get('scripless'):
        return None

    win = df.tail(days)
    if len(win) < max(C['MIN_ROWS_FLOOR'], int(days * C['MIN_ROW_RATIO'])):
        return None

    def num(col):
        return (pd.to_numeric(win[col], errors='coerce')
                if col in win.columns else pd.Series(dtype=float))

    net_top5 = num('Net Top5 All Lot').fillna(0.0)
    retail = num('Retail').fillna(0.0)
    close = num('Close').dropna()
    volume = num('Volume').fillna(0.0)
    if close.empty:
        return None

    absorbed_lot = float(net_top5.sum())
    absorbed_shares = absorbed_lot * LOT
    scripless = float(scripless_info['scripless'])

    adv_shares = float(volume.mean() or 0.0)
    last_close = float(close.iloc[-1])
    adv_value = adv_shares * last_close
    if adv_value < C['MIN_ADV_VALUE']:
        return None

    absorption_pct = absorbed_shares / scripless * 100.0
    first_close = float(close.iloc[0])
    price_chg = (last_close - first_close) / first_close * 100.0 if first_close else 0.0

    # Puncak inventaris di dalam jendela -- membedakan "menumpuk lalu
    # dilepas lagi" dari "menumpuk dan masih dipegang".
    cum = net_top5.cumsum()
    peak_pct = float(cum.max() - cum.min()) * LOT / scripless * 100.0

    days_to_cover = (abs(absorbed_shares) / adv_shares) if adv_shares > 0 else None
    bucket = classify(absorption_pct)

    return {
        'stock': stock,
        'days': int(len(win)),
        'absorbed_lot': round(absorbed_lot, 0),
        'scripless': scripless,
        'scripless_month': scripless_info.get('month'),
        'scripless_pct_of_listed': (round(scripless / scripless_info['sec_num'] * 100.0, 2)
                                    if scripless_info.get('sec_num') else None),
        'absorption_pct': round(absorption_pct, 3),
        'peak_pct': round(peak_pct, 3),
        'retail_pct': round(float(retail.sum()) * LOT / scripless * 100.0, 3),
        'price_chg_pct': round(price_chg, 2),
        'last_close': round(last_close, 2),
        'adv_value_juta': round(adv_value / 1e6, 1),
        'days_to_cover': round(days_to_cover, 1) if days_to_cover is not None else None,
        'quiet': abs(price_chg) <= 10.0,
        'bucket': bucket,
        'label': LABELS[bucket],
        'verdict': VERDICTS[bucket],
    }


def scan(days=None, force=False, limit=None):
    """
    Pindai seluruh emiten yang punya data KSEI + Summary.

    Diurutkan dari serapan PALING NEGATIF lebih dulu, bukan paling positif --
    karena kelompok "bandar melepas" itulah yang rekam jejaknya paling buruk
    dan paling berguna untuk disaring (pola yang sama dengan Lensa Keramaian:
    yang perlu dilihat duluan adalah yang merah).
    """
    days = days or C['DAYS']
    cache_key = 'scan_%d' % days

    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            entry = cached.get(cache_key)
            if entry and entry.get('ts', 0) >= _sumber_terbaru():
                result = dict(entry['result'])
                result['from_cache'] = True
                return result
        except Exception:
            pass

    smap = scripless_map()
    rows = []
    skipped_no_price = 0
    skipped_thin = 0

    for stock in sorted(smap):
        df = _read(stock)
        if df is None:
            skipped_no_price += 1
            continue
        row = measure(stock, days=days, scripless_info=smap[stock], df=df)
        if row is None:
            skipped_thin += 1
            continue
        rows.append(row)

    rows.sort(key=lambda r: r['absorption_pct'])

    counts = {'distribusi': 0, 'ringan': 0, 'berat': 0}
    for r in rows:
        counts[r['bucket']] += 1

    result = {
        'available': True,
        'days': days,
        'rows': rows[:limit] if limit else rows,
        'total': len(rows),
        'counts': counts,
        'skipped_no_price': skipped_no_price,
        'skipped_thin': skipped_thin,
        'config': dict(C),
        'kalibrasi': KALIBRASI,
        'as_of': time.strftime('%Y-%m-%d %H:%M'),
        'from_cache': False,
    }

    try:
        cached = {}
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
        cached[cache_key] = {'ts': time.time(), 'result': result}
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump(cached, fh)
    except Exception:
        pass

    return result
