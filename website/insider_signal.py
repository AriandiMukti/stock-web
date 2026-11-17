"""
Radar Insider: insider_activity.py dibaca DALAM KONTEKS, bukan sendirian.

KENAPA INI ADA
Event study lurus "insider BELI -> harga naik?" lemah (menang cuma ~5-7pp
dari nebak-buta, lihat docstring insider_activity.py). Digali lebih jauh
lewat serangkaian pengujian -- hasilnya BUKAN "insider adalah sinyal",
tapi "insider adalah KONFIRMASI yang cuma berarti kalau konteksnya pas".

BELI: NOL INFORMASI SENDIRIAN, BERARTI KALAU DIKONFIRMASI KONTEKS HARGA
Diukur H+40, 1.546 event insider BELI bersih (April-Sep 2026, 409
emiten): insider BELI di LUAR dua konteks di bawah -- 1.172 dari 1.546
kejadian (75,8%) -- win rate 49,5%, rata2 +0,21%. Koin lempar murni.

Nilainya MUNCUL kalau disilang sama dua sinyal yang masing-masing sudah
punya fondasi sendiri di app ini:
  - Jatuh Dalam (jatuh >40% dari puncak 60h, lihat jatuh_dalam.py):
    kombo BELI+zona win 57,1% (H+20) / 67,6% (H+40) vs zona sendirian
    50,6%/54,2%, vs insider BELI sendirian 52,8%/52,9%.
  - Akumulasi Palsu, sel "turun + Top5 beli" (lihat fake_accumulation.py):
    kombo +insider BELI win 58,8% (H+40) vs +insider JUAL di sel yang
    sama 36,2% -- insider jadi penentu ketiga saat broker besar & harga
    sudah sepakat duluan.
Dua kombo ini largely BEDA SAHAM (overlap cuma 33 dari 374 kejadian) --
saling melengkapi, bukan duplikat. Numpuk keduanya sekaligus TIDAK lebih
kuat dari Jatuh Dalam sendirian (60,6% vs 68,7%) -- menumpuk sinyal
tervalidasi tidak otomatis lebih sakti, jadi halaman ini tidak mencoba
"skor gabungan", cuma menandai alasan kombo yang kena.

JUAL: BUKAN KONFIRMASI, TAPI PERINGATAN DINI
Dibalik arah pertanyaannya: bukan "insider jual -> harga turun?" tapi
"insider jual -> saham ini lebih mungkin JATUH DALAM ke depan?". Semesta
409 ticker, saham yang BELUM di zona Jatuh Dalam:

    Baseline (tanpa insider jual 20h terakhir)      P(masuk zona 40h) = 25,3%
    Ada insider JUAL 20 hari terakhir               P = 52,0%  (+26,7pp)

Dikontrol GANDA -- level dari_puncak SAMA (-20%~-40%) DAN momentum 20
hari sebelumnya SAMA (7 kelompok) -- supaya bukan cuma "insider ikut
tren yang sudah jalan": efeknya BERTAHAN di semua 7 kelompok momentum,
+15,6pp sampai +33,7pp. Bukan echo tren, ada info tambahan asli.

STATUS: KALIBRASI, BUKAN TERUJI -- INI HARUS DIBACA
Ketiga temuan di atas cuma diukur di SATU periode (April-Sep 2026, 409
emiten yang kebetulan ada transaksi insidernya). Kombo Jatuh Dalam+BELI
sempat dicek ke potongan Agu-Sep (n=17, KONFIRMASI arahnya tapi kelewat
kecil buat jadi bukti). Kombo Akumulasi Palsu+BELI dan JUAL sbg
peringatan dini BELUM PERNAH dicek ke potongan waktu terpisah sama
sekali -- yang terakhir malah TIDAK BISA dicek: butuh 60 hari histori +
40 hari ke depan, dan itu menghabiskan semua 6 bulan data yang ada (nol
sisa buat holdout). Lihat status_bukti.py -- ini TIDAK didaftarkan
sebagai "teruji", cuma "kalibrasi". Jangan dibaca sebagai rekomendasi
beli/jual, apalagi buat daftar JUAL yang sifatnya peringatan, bukan
ramalan pasti.

SOAL TANGGAL, DAN JURNAL MAJUNYA (23 Sep 2026)
Kalibrasi di atas membaca transaksi di HARI TRANSAKSINYA -- kolom `date`
di data Stockbit adalah tanggal transaksi. Laporan insider terbit sampai
~10 hari sesudahnya, dan data di sini ditarik kira-kira sebulan sekali
(25 Mei, 25 Jun, 25 Jul, 31 Agu, 20 Sep), jadi sebagian jendela 40 hari
sudah lewat sebelum peringatannya bisa dilihat. Pratinjau di data yang
sama (insider_jurnal.py -- in-sample, kejadian tidak tumpang tindih,
pembanding dicocokkan hari + momentum, n 41-62):
    terlihat di hari transaksi      +17,5pp
    tarikan nyata app ini           +11,0pp  (jeda median 17 hari)
insider_jurnal.py mencatat sejak 22 Sep 2026 tiap transaksi PADA HARI IA
PERTAMA TERLIHAT, lalu menunggu 40 hari bursa -- uji luar sampel yang
tidak bisa dilakukan dengan data yang ada.

BATAS LAIN
- n untuk JUAL peringatan dini dihitung dari ticker-HARI (tumpang
  tindih -- banyak baris bertetangga berasal dari episode jual insider
  yang SAMA), bukan sebanyak episode independen yang sebenarnya.
- Belum dicek bias survivorship (jatuh_dalam.py sendiri mencatat 36,4%
  emiten di zona jatuh berhenti kirim data -- tujuh kali lipat dari
  emiten biasa). Kalau saham di daftar JUAL ini delisting/suspend,
  kemungkinan skenario terburuknya justru yang paling sering hilang
  dari pengukuran.
- Daftar JUAL peringatan dini di halaman ini SENGAJA dibatasi ke pita
  dari_puncak -20%~-40% -- satu-satunya pita yang sudah dikontrol
  ganda di atas. Insider jual di luar pita itu TIDAK ditampilkan di
  sini karena belum diukur di level itu.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import logging
import os
import pickle
import time

import pandas as pd

from . import insider_activity as ia
from .config import DAILY_PATH

logger = logging.getLogger(__name__)

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'insider_signal_cache.pkl'))

C = {
    'LOOKBACK': 20,        # hari kalender, insider dilihat ke belakang dari bar terakhir
    'PUNCAK_W': 60,        # jendela puncak Jatuh Dalam -- sama seperti jatuh_dalam.py
    'DALAM': -40.0,
    'JUAL_LO': -40.0,      # pita dari_puncak yang sudah dikontrol ganda utk daftar JUAL
    'JUAL_HI': -20.0,
    'MIN_ADV': 200e6,      # Rp200 juta/hari -- sama seperti jatuh_dalam.py
    'FA_WINDOW': 20,       # jendela harga & arus Akumulasi Palsu -- sama seperti fake_accumulation.py
}

# Angka hasil pengujian, ditaruh di sini supaya halaman menampilkan yang
# SAMA PERSIS dengan docstring -- konvensi yang sama dipakai jatuh_dalam.BUKTI.
BUKTI = {
    'sampel': '409 emiten yang pernah ada transaksi insider, April-Sep 2026',
    'beli_polos': {'n': 1172, 'mean': 0.21, 'win': 49.5,
                   'catatan': '75,8% dari semua event insider BELI jatuh di sini -- nol informasi.'},
    'kombo_jatuh_dalam': {
        'sendirian':      {'h20': {'mean': 2.75, 'win': 50.6}, 'h40': {'mean': 7.81, 'win': 54.2}},
        'plus_beli':       {'h20': {'mean': 7.76, 'win': 57.1}, 'h40': {'mean': 16.58, 'win': 67.6}},
        'plus_jual':       {'h20': {'mean': -2.53, 'win': 31.8}, 'h40': {'mean': -11.38, 'win': 28.2}},
        'holdout_agu_sep': 'n=17, arah konfirmasi tapi kelewat kecil buat jadi bukti',
    },
    'kombo_akumulasi_palsu': {
        'cell': 'harga turun 20h + Top5 broker net beli',
        'plus_beli': {'n': 160, 'mean': 4.82, 'win': 58.8},
        'plus_jual': {'n': 58, 'mean': -2.87, 'win': 36.2},
    },
    'overlap': {'n_fa': 160, 'n_jd': 247, 'n_overlap': 33,
                'cuma_fa': {'n': 127, 'win': 58.3}, 'cuma_jd': {'n': 214, 'win': 68.7},
                'dua_duanya': {'n': 33, 'win': 60.6},
                'catatan': 'Numpuk dua kombo TIDAK lebih kuat dari Jatuh Dalam sendirian.'},
    'jual_peringatan_dini': {
        'horizon': 40, 'lookback': 20,
        'baseline_kasar': 25.3, 'sell_kasar': 52.0,
        'kontrol_ganda': [
            {'momentum': '< -20%', 'baseline': 47.0, 'sell': 75.8},
            {'momentum': '-20% ~ -10%', 'baseline': 29.6, 'sell': 63.2},
            {'momentum': '-10% ~ -5%', 'baseline': 24.9, 'sell': 54.8},
            {'momentum': '-5% ~ 5% (datar)', 'baseline': 26.5, 'sell': 42.1},
            {'momentum': '5% ~ 10%', 'baseline': 39.2, 'sell': 65.9},
            {'momentum': '10% ~ 20%', 'baseline': 45.8, 'sell': 70.9},
            {'momentum': '> 20%', 'baseline': 63.5, 'sell': 85.3},
        ],
        'catatan': 'Semua diukur di pita dari_puncak -20%~-40% saja. Nol data holdout -- '
                   'forward 40h menghabiskan semua 6 bulan yang ada.',
    },
    'status': 'kalibrasi',
}

_MOMENTUM_BINS = [-1e9, -20, -10, -5, 5, 10, 20, 1e9]
_MOMENTUM_LABELS = ['< -20%', '-20% ~ -10%', '-10% ~ -5%', '-5% ~ 5% (datar)',
                     '5% ~ 10%', '10% ~ 20%', '> 20%']


def _momentum_lookup():
    return {row['momentum']: row for row in BUKTI['jual_peringatan_dini']['kontrol_ganda']}


def _read(ticker):
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % ticker)
    try:
        df = pd.read_csv(path, usecols=['Date', 'Close', 'High', 'Volume', 'Net Top5 All Lot']).fillna(0)
    except Exception:
        return None
    if df.empty or 'Date' not in df.columns:
        return None
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
    return df if len(df) >= C['PUNCAK_W'] else None


def _state(df):
    """Keadaan pada bar terakhir: dari_puncak, zona Jatuh Dalam, sel Akumulasi Palsu, momentum."""
    i = len(df) - 1
    close = df['Close']
    harga = float(close.iloc[i])
    if harga <= 0:
        return None

    adv = float(close.iloc[-20:].mean() * df['Volume'].iloc[-20:].mean())
    puncak = float(df['High'].iloc[-C['PUNCAK_W']:].max())
    if puncak <= 0:
        return None
    dari_puncak = (harga / puncak - 1) * 100
    in_zone = dari_puncak <= C['DALAM'] and adv >= C['MIN_ADV']

    w = C['FA_WINDOW']
    if i - w < 0:
        fa_turun_beli = False
        trail_pct = None
    else:
        p0 = float(close.iloc[i - w])
        trail_pct = (harga - p0) / p0 * 100 if p0 > 0 else None
        top5_sum = float(df['Net Top5 All Lot'].iloc[i - w + 1:i + 1].sum())
        fa_turun_beli = bool(trail_pct is not None and trail_pct <= -5.0 and top5_sum > 0)

    return {
        'date': df['Date'].iloc[i], 'harga': harga, 'dari_puncak': round(dari_puncak, 1),
        'in_zone': bool(in_zone), 'adv': adv, 'fa_turun_beli': fa_turun_beli,
        'trail_pct': round(trail_pct, 1) if trail_pct is not None else None,
    }


def _momentum_bucket(trail_pct):
    if trail_pct is None:
        return None
    idx = pd.cut([trail_pct], bins=_MOMENTUM_BINS, labels=_MOMENTUM_LABELS)[0]
    return None if pd.isna(idx) else str(idx)


def _bangun():
    df_insider = ia.load_all()
    trade = df_insider[df_insider['is_market_trade']].copy()
    if trade.empty:
        return {'available': False, 'message': 'Tidak ada data insider ditemukan.'}
    trade['day'] = trade['date'].dt.normalize()

    beli_rows, jual_rows = [], []
    momentum_lookup = _momentum_lookup()

    for ticker in sorted(trade['ticker'].unique()):
        df = _read(ticker)
        if df is None:
            continue
        state = _state(df)
        if state is None:
            continue

        lo = state['date'] - pd.Timedelta(days=C['LOOKBACK'])
        recent = trade[(trade['ticker'] == ticker) & (trade['day'] >= lo) & (trade['day'] <= state['date'])]
        if recent.empty:
            continue
        has_buy = (recent['action_type'] == 'ACTION_TYPE_BUY').any()
        has_sell = (recent['action_type'] == 'ACTION_TYPE_SELL').any()
        if has_buy and has_sell:
            continue  # campuran -- dibuang, sama seperti event study

        insiders = [{'name': r['name'], 'date': r['day'].strftime('%Y-%m-%d'), 'badges': r['badges']}
                    for _, r in recent.sort_values('day', ascending=False).iterrows()]

        if has_buy and (state['in_zone'] or state['fa_turun_beli']):
            alasan = []
            if state['in_zone']:
                alasan.append('jatuh_dalam')
            if state['fa_turun_beli']:
                alasan.append('akumulasi_palsu')
            beli_rows.append({
                'ticker': ticker, 'harga': state['harga'], 'dari_puncak': state['dari_puncak'],
                'trail_pct': state['trail_pct'], 'alasan': alasan, 'n_insiders': len(insiders),
                'insiders': insiders[:6], 'last_action_date': insiders[0]['date'],
            })
        elif has_sell and not state['in_zone'] and C['JUAL_LO'] < state['dari_puncak'] <= C['JUAL_HI']:
            bucket = _momentum_bucket(state['trail_pct'])
            angka = momentum_lookup.get(bucket)
            jual_rows.append({
                'ticker': ticker, 'harga': state['harga'], 'dari_puncak': state['dari_puncak'],
                'trail_pct': state['trail_pct'], 'momentum_bucket': bucket,
                'baseline_p': angka['baseline'] if angka else None,
                'sell_p': angka['sell'] if angka else None,
                'uplift': round(angka['sell'] - angka['baseline'], 1) if angka else None,
                'n_insiders': len(insiders), 'insiders': insiders[:6],
                'last_action_date': insiders[0]['date'],
            })

    beli_rows.sort(key=lambda r: (len(r['alasan']) == 1, r['dari_puncak']))
    jual_rows.sort(key=lambda r: -(r['uplift'] or 0))

    return {
        'available': True,
        'as_of': max((r['last_action_date'] for r in beli_rows + jual_rows), default=None),
        'n_beli': len(beli_rows),
        'n_jual': len(jual_rows),
        'beli': beli_rows,
        'jual_peringatan': jual_rows,
        'bukti': BUKTI,
        'config': dict(C),
        'dibangun': time.strftime('%Y-%m-%d %H:%M'),
        'from_cache': False,
    }


def _sumber_terbaru():
    from .kesegaran import summary_terbaru
    return summary_terbaru()


def scan(force=False):
    """Daftar kandidat hari ini. Di-cache terhadap mtime Summary terbaru."""
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                simpan = pickle.load(fh)
            if simpan.get('ts', 0) >= _sumber_terbaru():
                hasil = dict(simpan['result'])
                hasil['from_cache'] = True
                return hasil
        except Exception:
            pass

    hasil = _bangun()
    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'result': hasil}, fh)
    except Exception:
        logger.exception('Gagal menyimpan cache Radar Insider')
    return hasil
