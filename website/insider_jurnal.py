"""
Jurnal maju Radar Insider -- terutama PERINGATAN DINI insider JUAL.

KENAPA INI ADA
==============
insider_signal.py menemukan: saham yang insidernya JUAL dalam 20 hari
terakhir lebih mungkin masuk zona Jatuh Dalam dalam 40 hari bursa -- 52,0%
lawan 25,3% (+26,7pp), bertahan dikontrol ganda (level + momentum). Itu
temuan terkuat di menu itu, dan sekaligus yang PALING tidak teruji: diukur
di satu periode (Apr-Sep 2026), dan tidak bisa dicek di periode terpisah
karena 60 hari riwayat + 40 hari ke depan menghabiskan semua data.

Ada masalah kedua yang lebih diam: TANGGAL. Kolom `date` di data Stockbit
adalah tanggal TRANSAKSI. Kalibrasi menghitung jendela 40 hari dari situ,
padahal laporan insider baru terbit sampai ~10 hari sesudahnya, dan app ini
menarik datanya kira-kira SEBULAN sekali (mtime folder Monthly\\All: 25 Mei,
25 Jun, 25 Jul, 31 Agu, 20 Sep 2026). Sebagian jendela itu sudah lewat
sebelum infonya bisa dilihat di sini.

Jurnal ini menjawab keduanya: tiap transaksi insider dicatat PADA HARI IA
PERTAMA KALI TERLIHAT di data app, bersama keadaan sahamnya hari itu, lalu
ditunggu 40 hari bursa. Tanggal transaksinya tetap disimpan (kolom `jeda` =
hari kalender dari transaksi sampai terlihat), jadi efek jeda bisa dibaca
terpisah.

PRATINJAU: KALAU INFONYA TELAT (in-sample Apr-Sep 2026, BUKAN bukti)
Aturan yang sama dijalankan ulang di data lama, dengan tanggal "terlihat"
digeser (`python -m website.insider_jurnal pratinjau`, 23 Sep 2026).
P(masuk zona dalam 40 hari bursa), JUAL vs pembanding hari + momentum sama:

    terlihat di hari transaksi      60 kejadian   60,0% vs 42,5%   +17,5pp
    terlihat +5 hari                62            66,1% vs 47,8%   +18,4pp
    terlihat +10 hari               57            57,9% vs 46,5%   +11,4pp
    tarikan nyata app ini           41            61,0% vs 50,0%   +11,0pp
      (mtime berkas, jeda median 17 hari)

Dua bacaan. Pertama, dengan kejadian yang tidak tumpang tindih dan
pembanding yang dicocokkan momentum, klaim kasar +26,7pp menyusut ke
~+17pp -- masih besar. Kedua, dengan jadwal tarik data yang sebenarnya
dipakai di sini, tinggal ~+11pp. n kecil (galat baku ~6-8pp per baris),
jadi urutannya indikasi, bukan kepastian -- tapi arahnya masuk akal: info
yang telat 2-3 minggu sudah memakan separuh jendela 40 hari.

APA YANG DICATAT
- Semua transaksi pasar insider (BELI dan JUAL) saat pertama terlihat.
  BELI ikut dicatat supaya kombo Jatuh Dalam / Akumulasi Palsu + BELI
  nanti bisa diuji dengan cara yang sama.
- `tanggal` = hari bursa terakhir yang datanya sudah ada saat baris
  dicatat. Info itu paling cepat bisa dipakai di sesi BERIKUTNYA, jadi
  jendela 40 hari dihitung mulai hari bursa sesudah `tanggal`.
- Keadaan saham hari itu: dari puncak 60h, zona Jatuh Dalam, momentum 20h,
  ADV. Ditulis SEBELUM hasilnya ada -- yang dinilai adalah potret itu.
- Pencatatan pertama kali (seluruh isi data saat jurnal dipasang) ditandai
  `awal=1` dan TIDAK ikut dinilai: kapan baris-baris itu pertama terlihat
  tidak diketahui.
- Kunci baris = kode + tanggal transaksi + jenis + jumlah lembar, BUKAN
  nama: ejaan nama beda antar sumber (KSEI vs IDX) untuk orang yang sama,
  jadi laporan IDX yang datang belakangan untuk transaksi yang sudah
  tercatat dari KSEI tidak dihitung dua kali. Dua insider berbeda dengan
  kunci sama (lumrah untuk lembar bulat) dibedakan lewat `urutan`.

CARA MENILAI (sama dengan kalibrasi insider_signal.py)
- Kejadian = JUAL yang terlihat di hari d, saham belum di zona, pita dari
  puncak (-40%, -20%], tidak ada BELI insider 20 hari kalender sebelum d
  (campuran dibuang, sama dengan kalibrasi). Satu kejadian per emiten per
  20 hari bursa -- kalibrasi menghitung emiten-HARI yang tumpang tindih.
- Hasil = masuk zona Jatuh Dalam (<= -40% dari puncak 60h, ADV >= Rp200
  juta) di salah satu dari 40 hari bursa sesudah d.
- Pembanding = emiten di semesta insider yang sama, di pita yang sama, di
  hari yang sama, tanpa insider JUAL 20 hari terakhir -- dicocokkan per
  kelompok momentum 20h (7 kelompok, sama dengan tabel kontrol ganda).

BATASNYA
- Masuk zona bukan berarti rugi -- itu ukuran risiko, bukan ramalan harga.
- Emiten yang disuspend sebelum 40 hari lewat tidak punya hasil; dihitung
  terpisah, tidak dianggap aman.
- Jeda info mengikuti KEBIASAAN MENARIK data di sini. Kalau data insider
  ditarik lebih sering, jurnal yang sama mengukur versi yang lebih cepat.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import json
import logging
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

from . import insider_activity as ia
from .config import DAILY_PATH

logger = logging.getLogger(__name__)

HERE = os.path.dirname(__file__)
SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
JURNAL_FILE = str(_runtime_file('', 'insider_jurnal.csv'))
HARI_FILE = str(_runtime_file('', 'insider_jurnal_hari.csv'))
CACHE_FILE = str(_runtime_file('', 'insider_jurnal_cache.pkl'))

# SAMA dengan insider_signal.C -- aturan yang dikalibrasi.
C = {
    'LOOKBACK': 20,        # hari kalender: BELI dalam jendela ini = campuran, dibuang
    'PUNCAK_W': 60,
    'DALAM': -40.0,
    'JUAL_LO': -40.0,      # pita dari puncak yang dikontrol ganda
    'JUAL_HI': -20.0,
    'MIN_ADV': 200e6,
    'HORIZON': 40,         # hari bursa
    'JEDA_EMITEN': 20,     # satu kejadian per emiten per 20 hari bursa
    'MIN_N': 30,           # angka baru ditampilkan setelah sekian kejadian matang
    'INSIDER_BASI': 35,    # hari: data insider lebih tua dari ini = tarikan bulanan terlewat
}
MOMENTUM_BINS = [-1e9, -20, -10, -5, 5, 10, 20, 1e9]
MOMENTUM_LABELS = ['< -20%', '-20% ~ -10%', '-10% ~ -5%', '-5% ~ 5% (datar)',
                   '5% ~ 10%', '10% ~ 20%', '> 20%']

KLAIM = {'kasar': {'baseline': 25.3, 'jual': 52.0, 'selisih': 26.7},
         'kontrol_ganda': '+15,6pp s/d +33,7pp di ketujuh kelompok momentum'}

# Dari `python -m website.insider_jurnal pratinjau`, 23 Sep 2026 -- angka
# yang SAMA dengan docstring, supaya halaman tidak mengetik ulang angka.
# In-sample (Apr-Sep 2026), kejadian tidak tumpang tindih, pembanding
# dicocokkan hari + momentum. n kecil: galat bakunya ~6-8pp per baris.
PRATINJAU = [
    {'versi': 'Hari transaksi (cara kalibrasi)', 'jeda_median': 0, 'n_matang': 60,
     'p_jual': 60.0, 'p_pembanding': 42.5, 'selisih': 17.5},
    {'versi': 'Terlihat +5 hari', 'jeda_median': 5, 'n_matang': 62,
     'p_jual': 66.1, 'p_pembanding': 47.8, 'selisih': 18.4},
    {'versi': 'Terlihat +10 hari', 'jeda_median': 10, 'n_matang': 57,
     'p_jual': 57.9, 'p_pembanding': 46.5, 'selisih': 11.4},
    {'versi': 'Tarikan nyata app ini (mtime berkas)', 'jeda_median': 17, 'n_matang': 41,
     'p_jual': 61.0, 'p_pembanding': 50.0, 'selisih': 11.0},
]

KOLOM_JURNAL = ['tanggal', 'dicatat', 'stock', 'tanggal_transaksi', 'jeda', 'aksi', 'lembar',
                'nama', 'jabatan', 'sumber', 'pengendali', 'harga', 'awal', 'kunci', 'urutan',
                'close', 'dari_puncak', 'zona', 'tren20', 'adv', 'segar']
KOLOM_HARI = ['tanggal', 'dicatat', 'n_baru', 'n_pasar', 'transaksi_terbaru', 'tarik_terakhir']


# ---------------------------------------------------------------------------
# DATA HARGA
# ---------------------------------------------------------------------------
def _seri(ticker):
    """Summary satu emiten + ukuran zona. None kalau tidak ada / terlalu pendek."""
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % ticker)
    try:
        df = pd.read_csv(path, usecols=['Date', 'Close', 'High', 'Volume'])
    except Exception:
        return None
    df['date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['date']).drop_duplicates('date', keep='last').sort_values('date').reset_index(drop=True)
    for kol in ('Close', 'High', 'Volume'):
        df[kol] = pd.to_numeric(df[kol], errors='coerce').fillna(0.0)
    if len(df) < C['PUNCAK_W']:
        return None
    puncak = df['High'].rolling(C['PUNCAK_W'], min_periods=C['PUNCAK_W']).max()
    out = pd.DataFrame({'date': df['date'], 'close': df['Close']})
    out['dari_puncak'] = (df['Close'] / puncak.replace(0, np.nan) - 1) * 100
    out['adv'] = df['Close'].rolling(20).mean() * df['Volume'].rolling(20).mean()
    out['zona'] = (out['dari_puncak'] <= C['DALAM']) & (out['adv'] >= C['MIN_ADV'])
    out['tren20'] = (df['Close'] / df['Close'].shift(20).replace(0, np.nan) - 1) * 100
    z = out['zona'].astype(float)
    # masuk zona di salah satu baris i+1 .. i+HORIZON
    out['masuk'] = z[::-1].rolling(C['HORIZON'], min_periods=1).max()[::-1].shift(-1)
    out['matang'] = np.arange(len(out)) + C['HORIZON'] <= len(out) - 1
    return out


def _hari_pasar():
    """(hari bursa terakhir, daftar hari bursa) dari berkas Summary terbesar --
    emiten paling likuid praktis tidak pernah bolong (sama dengan pola_jurnal)."""
    berkas = glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv'))
    if not berkas:
        return None, []
    df = pd.read_csv(max(berkas, key=os.path.getsize), usecols=['Date'])
    d = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce').dropna().sort_values().unique()
    d = pd.DatetimeIndex(d)
    return (d[-1] if len(d) else None), d


def _momentum(v):
    if v is None or not np.isfinite(v):
        return None
    i = np.searchsorted(MOMENTUM_BINS, v, side='left') - 1
    return MOMENTUM_LABELS[max(0, min(i, len(MOMENTUM_LABELS) - 1))]


def _num(v, d=None):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return round(v, d) if d is not None else v


def _tarik_terakhir():
    """mtime berkas insider paling baru = kapan scraper terakhir jalan."""
    terbaru = 0.0
    for path in glob.glob(os.path.join(ia.INSIDER_DIR, '*', '*_INSIDER.json')):
        try:
            terbaru = max(terbaru, os.path.getmtime(path))
        except OSError:
            continue
    return pd.Timestamp(terbaru, unit='s').normalize() if terbaru else None


# ---------------------------------------------------------------------------
# MENCATAT
# ---------------------------------------------------------------------------
def _muat():
    """(jurnal, hari). Berkas yang ada tapi tak terbaca -> melempar, BUKAN
    kosong: penulis tidak boleh mengira jurnal kosong lalu mencatat ulang
    semuanya sebagai 'awal' di atas riwayat yang cuma gagal dibaca."""
    j = (pd.read_csv(JURNAL_FILE, dtype={'tanggal': str, 'stock': str, 'kunci': str})
         if os.path.exists(JURNAL_FILE) else pd.DataFrame(columns=KOLOM_JURNAL))
    h = (pd.read_csv(HARI_FILE, dtype={'tanggal': str})
         if os.path.exists(HARI_FILE) else pd.DataFrame(columns=KOLOM_HARI))
    if len(j):
        j = j.drop_duplicates(['kunci', 'urutan'], keep='first')
    if len(h):
        h = h.drop_duplicates('tanggal', keep='last')
    return j, h


def _transaksi_pasar():
    df = ia.load_all()
    if df is None or df.empty:
        return pd.DataFrame()
    t = df[df['is_market_trade']].copy()
    t['kunci'] = (t['ticker'] + '|' + t['date'].dt.strftime('%Y-%m-%d') + '|' + t['action_type'] + '|'
                  + t['shares_changed'].round().astype('int64').astype(str))
    # Urutan stabil antar-run: dua insider dengan kunci sama selalu dapat
    # nomor yang sama, apa pun urutan berkas yang dibaca load_all().
    t = t.sort_values(['kunci', 'name', 'source'])
    t['urutan'] = t.groupby('kunci').cumcount()
    return t


def catat():
    """Catat transaksi insider yang BARU pertama kali terlihat. Idempoten."""
    try:
        lama, _ = _muat()
    except Exception as exc:
        logger.exception('Jurnal insider tidak terbaca -- tidak menulis apa pun')
        return {'tercatat': 0, 'pesan': 'jurnal tidak terbaca: %s' % exc}
    pertama = not os.path.exists(JURNAL_FILE)

    t = _transaksi_pasar()
    hari, _ = _hari_pasar()
    if t.empty or hari is None:
        return {'tercatat': 0, 'pesan': 'tidak ada data insider atau Summary'}
    tanggal = hari.strftime('%Y-%m-%d')

    sudah = set(zip(lama['kunci'].astype(str), lama['urutan'].astype(int))) if len(lama) else set()
    baru = t[[(k, int(u)) not in sudah for k, u in zip(t['kunci'], t['urutan'])]]

    seri = {}
    rows = []
    for r in baru.itertuples():
        if r.ticker not in seri:
            seri[r.ticker] = _seri(r.ticker)
        s = seri[r.ticker]
        st = {}
        if s is not None:
            s0 = s[s['date'] <= hari]
            if len(s0):
                x = s0.iloc[-1]
                st = {'close': _num(x['close'], 2), 'dari_puncak': _num(x['dari_puncak'], 2),
                      'zona': int(bool(x['zona'])), 'tren20': _num(x['tren20'], 2),
                      'adv': _num(x['adv'], 0), 'segar': int(x['date'] == hari)}
        rows.append(dict({
            'tanggal': tanggal, 'dicatat': time.strftime('%Y-%m-%d %H:%M'), 'stock': r.ticker,
            'tanggal_transaksi': r.date.strftime('%Y-%m-%d'),
            'jeda': int((hari - r.date.normalize()).days),
            'aksi': 'BELI' if r.action_type == 'ACTION_TYPE_BUY' else 'JUAL',
            'lembar': abs(int(round(r.shares_changed))), 'nama': r.name,
            'jabatan': ', '.join(r.badges or []), 'sumber': r.source,
            'pengendali': int(bool(r.is_controller)), 'harga': _num(r.price_reported, 2),
            'awal': int(pertama), 'kunci': r.kunci, 'urutan': int(r.urutan),
        }, **st))
    if rows:
        pd.DataFrame(rows, columns=KOLOM_JURNAL).to_csv(
            JURNAL_FILE, mode='a', index=False, header=not os.path.exists(JURNAL_FILE))
    tarik = _tarik_terakhir()
    pd.DataFrame([{'tanggal': tanggal, 'dicatat': time.strftime('%Y-%m-%d %H:%M'), 'n_baru': len(rows),
                   'n_pasar': len(t), 'transaksi_terbaru': t['date'].max().strftime('%Y-%m-%d'),
                   'tarik_terakhir': tarik.strftime('%Y-%m-%d') if tarik is not None else None}],
                 columns=KOLOM_HARI).to_csv(HARI_FILE, mode='a', index=False,
                                             header=not os.path.exists(HARI_FILE))
    return {'tanggal': tanggal, 'tercatat': len(rows), 'awal': pertama,
            'jual_baru': int(sum(1 for r in rows if r['aksi'] == 'JUAL'))}


# ---------------------------------------------------------------------------
# MENILAI
# ---------------------------------------------------------------------------
def _nilai(kejadian, trans, seri, universe):
    """
    kejadian: DataFrame [stock, tanggal (Timestamp hari terlihat), jeda] untuk JUAL.
    trans:    transaksi pasar (untuk membuang campuran & menyaring pembanding).
    Mengembalikan statistik kejadian vs pembanding hari & momentum yang sama.
    """
    jual = trans[trans['action_type'] == 'ACTION_TYPE_SELL'].groupby('ticker')['date'].apply(
        lambda s: np.sort(s.dt.normalize().values))
    beli = trans[trans['action_type'] == 'ACTION_TYPE_BUY'].groupby('ticker')['date'].apply(
        lambda s: np.sort(s.dt.normalize().values))
    lb = np.timedelta64(C['LOOKBACK'], 'D')

    def ada(tab, t, d):
        arr = tab.get(t)
        if arr is None or not len(arr):
            return False
        i = np.searchsorted(arr, np.datetime64(d) - lb, side='left')
        return i < len(arr) and arr[i] <= np.datetime64(d)

    # --- kejadian ---
    ev = []
    for r in kejadian.sort_values(['stock', 'tanggal']).itertuples():
        s = seri.get(r.stock)
        if s is None:
            ev.append({'stock': r.stock, 'status': 'tanpa_data'})
            continue
        pos = s.index[s['date'] == r.tanggal]
        if not len(pos):
            ev.append({'stock': r.stock, 'status': 'basi'})
            continue
        x = s.loc[pos[0]]
        if bool(x['zona']) or not (C['JUAL_LO'] < (x['dari_puncak'] if np.isfinite(x['dari_puncak']) else 99) <= C['JUAL_HI']):
            ev.append({'stock': r.stock, 'status': 'di_luar_pita'})
            continue
        if ada(beli, r.stock, r.tanggal):
            ev.append({'stock': r.stock, 'status': 'campuran'})
            continue
        ev.append({'stock': r.stock, 'status': 'kejadian', 'tanggal': r.tanggal, 'p': int(pos[0]),
                   'jeda': r.jeda, 'bucket': _momentum(x['tren20']),
                   'matang': bool(x['matang']), 'masuk': x['masuk']})
    ev = pd.DataFrame(ev)
    hitung = ev['status'].value_counts().to_dict() if len(ev) else {}
    k = ev[ev['status'] == 'kejadian'].copy() if len(ev) else pd.DataFrame()
    if len(k):
        # satu kejadian per emiten per JEDA_EMITEN baris
        pilih = []
        for _, g in k.groupby('stock'):
            akhir = -10 ** 9
            for idx, p in zip(g.index, g['p']):
                if p - akhir >= C['JEDA_EMITEN']:
                    pilih.append(idx)
                    akhir = p
        k = k.loc[pilih]

    # --- pembanding: semesta insider, pita sama, hari sama, tanpa JUAL 20h ---
    tanggal = set(k['tanggal']) if len(k) else set()
    kontrol = []
    for t in universe:
        s = seri.get(t)
        if s is None or not tanggal:
            continue
        sub = s[s['date'].isin(tanggal) & ~s['zona'] & (s['dari_puncak'] > C['JUAL_LO'])
                & (s['dari_puncak'] <= C['JUAL_HI']) & s['matang']]
        for x in sub.itertuples():
            if ada(jual, t, x.date):
                continue
            kontrol.append({'tanggal': x.date, 'bucket': _momentum(x.tren20), 'masuk': x.masuk})
    kontrol = pd.DataFrame(kontrol)
    if len(kontrol):
        p_hb = kontrol.groupby(['tanggal', 'bucket'])['masuk'].mean().to_dict()
        p_h = kontrol.groupby('tanggal')['masuk'].mean().to_dict()
    else:
        p_hb, p_h = {}, {}

    def ringkas(sub):
        m = sub[sub['matang'].astype(bool)] if len(sub) else sub
        if not len(m):
            return {'n': int(len(sub)), 'n_matang': 0}
        base = [p_hb.get((r.tanggal, r.bucket), p_h.get(r.tanggal, np.nan)) for r in m.itertuples()]
        base = np.array(base, float)
        ok = np.isfinite(base)
        return {'n': int(len(sub)), 'n_matang': int(len(m)),
                'p_jual': _num(m['masuk'].mean() * 100, 1),
                'p_pembanding': _num(np.nanmean(base) * 100, 1) if ok.any() else None,
                'selisih': _num((m['masuk'][ok].mean() - base[ok].mean()) * 100, 1) if ok.any() else None,
                'n_pembanding': int(len(kontrol))}

    per_jeda = []
    if len(k):
        for lab, lo, hi in (('<= 10 hari', -10 ** 6, 10), ('11-20 hari', 10, 20), ('> 20 hari', 20, 10 ** 6)):
            sub = k[(k['jeda'] > lo) & (k['jeda'] <= hi)]
            r = ringkas(sub)
            r['jeda'] = lab
            per_jeda.append(r)
    return {'semua': ringkas(k), 'per_jeda': per_jeda, 'hitung': {str(a): int(b) for a, b in hitung.items()}}


def _semesta(trans):
    tickers = sorted(trans['ticker'].unique())
    return tickers, {t: _seri(t) for t in tickers}


def evaluasi(force=False):
    """Hasil jurnal (cache terhadap mtime Summary & jurnal)."""
    from .kesegaran import summary_terbaru, berkas_terbaru, paling_baru
    sumber = paling_baru(summary_terbaru(), berkas_terbaru(JURNAL_FILE, HARI_FILE))
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                simpan = pickle.load(fh)
            if simpan.get('ts', 0) >= sumber:
                return simpan['result']
        except Exception:
            pass
    try:
        hasil = _evaluasi()
    except Exception as exc:
        logger.exception('Gagal mengevaluasi jurnal insider')
        return {'available': False, 'message': 'Gagal mengevaluasi: %s' % exc}
    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'result': hasil}, fh)
    except Exception:
        logger.exception('Gagal menyimpan cache jurnal insider')
    return hasil


def _evaluasi():
    j, h = _muat()
    hari, kal = _hari_pasar()
    cakupan = {'n_hari': int(len(h)), 'n_baris': int(len(j)),
               'n_awal': int((j['awal'].astype(int) == 1).sum()) if len(j) else 0,
               'mulai': str(h['tanggal'].min()) if len(h) else None, 'terlewat': []}
    if cakupan['mulai'] and hari is not None:
        tercatat = set(h['tanggal'].astype(str))
        cakupan['terlewat'] = [d.strftime('%Y-%m-%d') for d in kal
                               if pd.Timestamp(cakupan['mulai']) <= d <= hari
                               and d.strftime('%Y-%m-%d') not in tercatat]
    data = {}
    if len(h):
        akhir = h.sort_values('tanggal').iloc[-1]
        data = {'tarik_terakhir': akhir.get('tarik_terakhir'), 'transaksi_terbaru': akhir.get('transaksi_terbaru')}
        if data['tarik_terakhir'] and hari is not None and isinstance(data['tarik_terakhir'], str):
            data['umur_hari'] = int((pd.Timestamp.now().normalize() - pd.Timestamp(data['tarik_terakhir'])).days)

    maju = j[j['awal'].astype(int) == 0] if len(j) else j
    jual = maju[maju['aksi'] == 'JUAL'] if len(maju) else maju
    hasil = {'available': True, 'cakupan': cakupan, 'data_insider': data, 'klaim': KLAIM,
             'pratinjau': PRATINJAU, 'config': dict(C),
             'n_jual': int(len(jual)), 'n_beli': int((maju['aksi'] == 'BELI').sum()) if len(maju) else 0,
             'jeda_median': _num(jual['jeda'].median(), 0) if len(jual) else None}
    if len(jual):
        trans = _transaksi_pasar()
        universe, seri = _semesta(trans)
        kejadian = pd.DataFrame({'stock': jual['stock'], 'tanggal': pd.to_datetime(jual['tanggal']),
                                 'jeda': jual['jeda'].astype(int)})
        nilai = _nilai(kejadian, trans, seri, universe)
        hasil.update(nilai)
        # berapa hari bursa lagi sampai kejadian tertua yang belum matang matang
        if hari is not None and nilai['semua'].get('n', 0) > nilai['semua'].get('n_matang', 0):
            tgl = pd.to_datetime(jual['tanggal']).min()
            pos = {d: i for i, d in enumerate(kal)}
            if tgl in pos and hari in pos:
                hasil['sisa_hari'] = max(0, pos[tgl] + C['HORIZON'] + 1 - pos[hari])
    hasil['terbaru'] = [
        {'stock': r['stock'], 'tanggal': r['tanggal'], 'tanggal_transaksi': r['tanggal_transaksi'],
         'jeda': int(r['jeda']), 'nama': r['nama'], 'jabatan': r['jabatan'] if isinstance(r['jabatan'], str) else '',
         'dari_puncak': _num(r['dari_puncak'], 1)}
        for _, r in jual.sort_values(['tanggal', 'tanggal_transaksi'], ascending=False).head(12).iterrows()
    ] if len(jual) else []
    return hasil


def jalankan():
    """Untuk kesehatan.py dan halaman: catat dulu, lalu nilai (cache)."""
    c = catat()
    e = evaluasi(force=bool(c.get('tercatat')))
    if isinstance(e, dict):
        e = dict(e)
        e['catat'] = c
    return e


# ---------------------------------------------------------------------------
# PRATINJAU: aturan yang sama di data lama, tanggal "terlihat" digeser
# ---------------------------------------------------------------------------
def pratinjau():
    """
    Kejadian JUAL Apr-Sep 2026 dengan tanggal terlihat = tanggal transaksi
    + L hari (L = 0, 5, 10), dan 'tarikan nyata' = hari berkas yang memuat
    transaksi itu PERTAMA kali ditulis scraper (mtime). In-sample -- periode
    yang sama dengan kalibrasi -- jadi ini ukuran kepekaan, bukan bukti.
    """
    trans = _transaksi_pasar()
    hari, kal = _hari_pasar()
    universe, seri = _semesta(trans)
    jual = trans[trans['action_type'] == 'ACTION_TYPE_SELL']

    # tanggal berkas pertama yang memuat tiap transaksi
    pertama = {}
    for path in glob.glob(os.path.join(ia.INSIDER_DIR, '*', '*_INSIDER.json')):
        try:
            mt = pd.Timestamp(os.path.getmtime(path), unit='s').normalize()
            with open(path, encoding='utf-8') as fh:
                mv = json.load(fh).get('data', {}).get('movement', [])
        except Exception:
            continue
        tkr = os.path.basename(path).split('_')[0].upper()
        for m in mv:
            try:
                d = pd.to_datetime(m.get('date'), format='%d %b %y')
            except Exception:
                continue
            kunci = '%s|%s|%s|%d' % (tkr, d.strftime('%Y-%m-%d'), m.get('action_type'),
                                      int(round(ia._num((m.get('changes') or {}).get('value')))))
            if kunci not in pertama or mt < pertama[kunci]:
                pertama[kunci] = mt

    def ke_hari_bursa(ts):
        i = kal.searchsorted(ts, side='left')
        return kal[i] if i < len(kal) else None

    baris = []
    for nama, geser in (('hari transaksi (cara kalibrasi)', 0), ('+5 hari', 5), ('+10 hari', 10),
                        ('tarikan nyata (mtime berkas)', None)):
        rows = []
        for r in jual.itertuples():
            if geser is None:
                t0 = pertama.get(r.kunci)
                if t0 is None:
                    continue
            else:
                t0 = r.date.normalize() + pd.Timedelta(days=geser)
            d = ke_hari_bursa(t0)
            if d is None:
                continue
            rows.append({'stock': r.ticker, 'tanggal': d, 'jeda': int((d - r.date.normalize()).days)})
        kej = pd.DataFrame(rows).drop_duplicates(['stock', 'tanggal'])
        n = _nilai(kej, trans, seri, universe)['semua']
        n['versi'] = nama
        n['jeda_median'] = _num(kej['jeda'].median(), 0) if len(kej) else None
        baris.append(n)
    return baris


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'pratinjau':
        for b in pratinjau():
            print('%-34s jeda median %4s | kejadian matang %4s | P(masuk zona) jual %5s%% vs pembanding %5s%% -> selisih %5s pp'
                  % (b['versi'], b.get('jeda_median'), b.get('n_matang'), b.get('p_jual'),
                     b.get('p_pembanding'), b.get('selisih')))
    else:
        t0 = time.time()
        h = jalankan()
        print('catat:', h.get('catat'))
        print('cakupan:', h.get('cakupan'))
        print('data insider:', h.get('data_insider'), '| JUAL terlihat (non-awal):', h.get('n_jual'))
        print('semua:', h.get('semua'), '| sisa hari:', h.get('sisa_hari'))
        print('%.1f detik' % (time.time() - t0))
