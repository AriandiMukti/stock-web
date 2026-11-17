"""
Profil kalibrasi twin: semua angka yang diambil dari DATA NYATA.

Sumber dan apa yang diambil darinya:

  IHSG (Yahoo ^JKSE)           return harian 2016-sekarang -> bahan faktor
                               pasar twin (dibootstrap per blok), level awal,
                               beta tiap saham.
  Daily\\Summary\\<T>.csv       harga awal (mentah, sudah di grid fraksi),
                               volume & nilai transaksi rata-rata 60 hari.
  research_cache harga_*.pkl   return 2 tahun (disesuaikan Yahoo) untuk
                               volatilitas, ekor, clustering -> target
                               realisme, bukan input.
  harga_mentah_close.pkl       frekuensi ARA/ARB nyata sejak aturan ARB 15%.
  Monthly\\Ownership\\ksei      jumlah saham, kapitalisasi, komposisi
                               pemilik (individu lokal = ritel, asing,
                               institusi lokal, korporasi = pengendali yang
                               tidak ikut berdagang) -> kepemilikan awal agen.
  Daily\\All JSON (s/d 15 Sep)  nilai BRUTO per broker + `type` + `freq` ->
                               porsi aktivitas tiap persona dan ukuran
                               transaksinya.
  broker_ledger.pkl            arus NETTO harian per broker (Jan-Okt 2026)
                               -> perilaku persona (ikut tren atau melawan)
                               dan jejak "bandar": broker lokal non-ritel
                               yang arahnya kompak berhari-hari.
  <T>_ORDER_BOOK.json          kedalaman antrean & spread nyata (16 hari,
                               24 Agu-15 Sep 2026) -> pembanding buku twin.

Yang TIDAK ada di data dan karena itu disintesis di agen.py: individu di
balik tiap broker, urutan order intraday, nilai wajar, aliran berita.

Cache mengikuti aturan kesegaran.py: basi begitu ada sumber yang lebih baru
daripada cache-nya, bukan karena umur.
"""
try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import hashlib
import json
import os
import pickle
import time

import numpy as np
import pandas as pd

from ..config import DAILY_PATH, OWNERSHIP_PATH
from ..kesegaran import summary_terbaru, berkas_terbaru, kepemilikan_terbaru, paling_baru
from . import aturan

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
ALL_DIR = os.path.join(DAILY_PATH, 'All')
KSEI_DIR = os.path.join(OWNERSHIP_PATH, 'ksei')
IDX_DIR = os.path.join(OWNERSHIP_PATH, 'idx')
WEB_DIR = os.path.dirname(os.path.dirname(__file__))
RESEARCH_CACHE = str(_runtime_file('', 'research_cache'))
LEDGER_FILE = str(_runtime_file('', 'broker_ledger.pkl'))
CACHE_DIR = str(_runtime_file('twin', 'cache'))

# Daftar broker ritel yang sudah dipakai app ini (analyze.py) -- sengaja
# disamakan supaya "ritel" di twin berarti hal yang sama dengan di menu lain.
BROKER_RITEL = ('YP', 'PD', 'XL', 'NI', 'CC', 'XC', 'KK', 'SQ', 'GR', 'DH')
# Cadangan kalau peta tipe dari JSON gagal dibangun (juga dari analyze.py).
BROKER_ASING_CADANGAN = ('KZ', 'AK', 'RX', 'YU', 'ZP', 'BK', 'CS', 'MS')

# Saham contoh bawaan: empat big cap yang dikuasai asing, dua saham komoditas
# yang ramai ritel, dan dua lapis bawah (<Rp30 T) tempat bandar otomatis
# dipasang. GOTO sengaja tidak: harganya menempel di Rp50 (batas bawah), jadi
# satu fraksi = 2% dan dinamikanya didominasi lantai harga, bukan agen.
BAWAAN = ['BBCA', 'BBRI', 'TLKM', 'ASII', 'ANTM', 'BUMI', 'DEWA', 'RAJA']

HARI_ADV = 60          # rata-rata volume/nilai transaksi
HARI_STAT = 500        # jendela statistik return (sekitar 2 tahun bursa)
HARI_JSON = 40         # hari JSON terakhir untuk komposisi bruto
HARI_BANDAR = 60       # jendela jejak bandar di buku besar


# ---------------------------------------------------------------- utilitas
def _pastikan_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _f(v, d=None):
    """float yang aman untuk JSON (NaN/inf -> d)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return d
    return v if np.isfinite(v) else d


# ------------------------------------------------------------------- IHSG
def ihsg(paksa_unduh=False):
    """
    Seri penutupan IHSG (pd.Series, indeks tanggal) dari Yahoo ^JKSE.

    Kesegaran: diunduh ulang kalau cache lebih tua daripada berkas Summary
    terbaru (artinya ada hari bursa baru), bukan per jam. Kalau unduhan
    gagal (offline), pakai cache lama atau seri ihsg_*.pkl di research_cache
    -- twin tetap jalan, hanya tanggal akhirnya lebih tua dan dicatat.
    """
    _pastikan_cache_dir()
    berkas = str(_runtime_file('twin/cache', 'ihsg_yahoo.pkl'))
    lama = None
    if os.path.exists(berkas):
        try:
            with open(berkas, 'rb') as fh:
                lama = pickle.load(fh)
        except Exception:
            lama = None
    if lama is not None and not paksa_unduh and lama.get('ts', 0) >= summary_terbaru():
        return lama['seri'], lama['sumber']

    try:
        import yfinance as yf
        df = yf.download('^JKSE', start='2016-01-01', interval='1d',
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        s = df['Close'].dropna()
        s.index = pd.to_datetime(s.index).tz_localize(None)
        # Baris hari ini selama bursa masih buka adalah harga berjalan, bukan
        # penutupan. Dibuang supaya level awal twin = penutupan sah terakhir.
        hari_ini = pd.Timestamp(time.strftime('%Y-%m-%d'))
        if len(s) and s.index[-1] >= hari_ini and time.localtime().tm_hour < 17:
            s = s.iloc[:-1]
        s = s[~s.index.duplicated(keep='last')]
        if len(s) < 500:
            raise ValueError('seri IHSG Yahoo terlalu pendek (%d)' % len(s))
        with open(berkas, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'seri': s, 'sumber': 'Yahoo ^JKSE'}, fh)
        return s, 'Yahoo ^JKSE'
    except Exception as exc:
        if lama is not None:
            return lama['seri'], lama['sumber'] + ' (cache; unduh gagal: %s)' % type(exc).__name__
        kandidat = sorted(glob.glob(str(_runtime_file('research_cache', 'ihsg_*.pkl'))))
        if not kandidat:
            raise RuntimeError('IHSG tidak bisa diunduh dan tidak ada cache: %s' % exc)
        with open(kandidat[0], 'rb') as fh:
            s = pickle.load(fh)
        s = s[~s.index.duplicated()]
        return s, 'research_cache %s (unduh gagal)' % os.path.basename(kandidat[0])


def ringkas_ihsg(seri, sumber):
    lr = np.log(seri).diff().dropna()
    return {
        'sumber': sumber,
        'dari': str(seri.index[0].date()),
        'sampai': str(seri.index[-1].date()),
        'level': float(seri.iloc[-1]),
        'n': int(len(lr)),
        'tanggal': [str(d.date()) for d in lr.index],
        'ret': lr.values.astype(float),
        'vol_harian': float(lr.tail(HARI_STAT).std()),
        'ret_20h': float(seri.iloc[-1] / seri.iloc[-21] - 1) if len(seri) > 21 else 0.0,
    }


# ---------------------------------------------------------------- harga
def baca_summary(t):
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % t)
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date']).set_index('Date').sort_index()
    df = df[~df.index.duplicated(keep='last')]
    for k in ('Open', 'High', 'Low', 'Close', 'Volume'):
        df[k] = pd.to_numeric(df[k], errors='coerce')
    return df[df['Close'] > 0]


_YAHOO = {}


def _harga_yahoo():
    """Pickle harga Yahoo dengan baris terbanyak (sama dengan
    riset_pola_naik/panel.sumber_harga, tanpa mengimpor paket riset)."""
    if 'data' in _YAHOO:
        return _YAHOO['data']
    terbaik, kunci_terbaik = {}, (0, 0)
    for path in glob.glob(str(_runtime_file('research_cache', 'harga_*.pkl'))):
        if 'mentah' in path:
            continue
        try:
            with open(path, 'rb') as fh:
                data = pickle.load(fh)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        kunci = (sum(len(v) for v in data.values()), len(data))
        if kunci > kunci_terbaik:
            terbaik, kunci_terbaik = data, kunci
    _YAHOO['data'] = terbaik
    return terbaik


def _harga_mentah():
    if 'mentah' in _YAHOO:
        return _YAHOO['mentah']
    path = str(_runtime_file('research_cache', 'harga_mentah_close.pkl'))
    try:
        with open(path, 'rb') as fh:
            _YAHOO['mentah'] = pickle.load(fh)
    except Exception:
        _YAHOO['mentah'] = {}
    return _YAHOO['mentah']


def fakta_return(r, volume=None):
    """
    'Stylized facts' satu deret return log harian. Fungsi yang SAMA dipakai
    untuk data asli dan hasil twin (validasi.py), supaya yang dibandingkan
    benar-benar setara.
    """
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 30:
        return None
    sd = r.std()
    a = np.abs(r - r.mean())

    def acf(x, lag):
        x = x - x.mean()
        den = (x * x).sum()
        if den <= 0 or lag >= len(x):
            return 0.0
        return float((x[:-lag] * x[lag:]).sum() / den)

    k = float(((r - r.mean()) ** 4).mean() / (sd ** 4) - 3.0) if sd > 0 else 0.0
    keluar = {
        'n': int(len(r)),
        'vol_harian': float(sd),
        'kurtosis_lebih': k,
        'acf_r1': acf(r, 1),
        'acf_abs_1_10': float(np.mean([acf(a, l) for l in range(1, 11)])),
        'ekor_3sd': float((np.abs(r - r.mean()) > 3 * sd).mean()) if sd > 0 else 0.0,
    }
    if volume is not None:
        v = np.asarray(volume, dtype=float)[-len(r):]
        ok = np.isfinite(v) & (v > 0)
        if ok.sum() > 30:
            keluar['corr_vol_absr'] = float(np.corrcoef(np.log(v[ok]), np.abs(r[ok]))[0, 1])
    return keluar


def vol_kokoh(r):
    """Simpangan baku versi kokoh: 1,4826 x median simpangan absolut. Sama
    dengan std untuk distribusi normal, tapi tidak diseret satu-dua hari
    ekstrem -- dipakai kalibrasi mikro di KEDUA sisi (asli & twin)."""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 10:
        return float(np.std(r)) if len(r) else 0.0
    return float(1.4826 * np.median(np.abs(r - np.median(r))))


def fakta_jendela(r, volume, panjang):
    """Median 'stylized facts' atas jendela-jendela tak bertumpuk sepanjang
    `panjang` hari. Dipakai supaya data asli dibandingkan dengan twin pada
    PANJANG YANG SAMA: ACF |r| atau kurtosis 2 tahun memuat pergantian
    rezim (mis. crash April 2025) yang tidak mungkin ada di jendela 60 hari,
    jadi membandingkannya dengan twin 60 hari tidak adil ke dua arah."""
    r = np.asarray(r, dtype=float)
    v = None if volume is None else np.asarray([np.nan if x is None else x for x in volume], dtype=float)
    panjang = int(max(panjang, 30))
    hasil = []
    for a in range(len(r) - panjang, -1, -panjang):
        f = fakta_return(r[a:a + panjang], None if v is None else v[a:a + panjang])
        if f:
            hasil.append(f)
    if not hasil:
        return fakta_return(r, v)
    kunci = set.intersection(*[set(f) for f in hasil])
    return {k: float(np.median([f[k] for f in hasil])) for k in kunci}


def _hit_batas(close):
    """Porsi hari yang ditutup tepat di ARA / ARB, dari harga mentah."""
    c = close.dropna().values
    if len(c) < 30:
        return None, None
    ara = arb = 0
    for i in range(1, len(c)):
        lo, hi = aturan.batas_harian(c[i - 1])
        if c[i] >= hi:
            ara += 1
        elif c[i] <= lo and c[i] < c[i - 1]:
            arb += 1
    n = len(c) - 1
    return ara / n, arb / n


# ----------------------------------------------------------------- KSEI
def ksei_terbaru():
    berkas = sorted(glob.glob(os.path.join(KSEI_DIR, '20??-??.json')))
    if not berkas:
        return None
    with open(berkas[-1], encoding='utf-8') as fh:
        return json.load(fh)


def komposisi_pemilik(rec):
    """
    Satu baris KSEI -> porsi saham yang BEREDAR untuk diperdagangkan twin.

    Korporasi (CP lokal & asing) diperlakukan sebagai pengendali/strategis
    yang tidak ikut berdagang -- tidak selalu benar (ada korporasi yang
    trader), tapi pengendali hampir selalu tercatat sebagai CP, dan
    memasukkan 51% RAJA milik induknya ke "float" akan membuat bandar twin
    tidak pernah bisa menguasai apa pun.
    """
    lokal = rec.get('local') or {}
    asing = rec.get('foreign') or {}
    scripless = float(rec.get('local_total') or 0) + float(rec.get('foreign_total') or 0)
    if scripless <= 0:
        return None
    cp = float(lokal.get('CP', 0)) + float(asing.get('CP', 0))
    ritel = float(lokal.get('ID', 0)) + float(asing.get('ID', 0))
    asing_dagang = float(rec.get('foreign_total') or 0) - float(asing.get('CP', 0)) - float(asing.get('ID', 0))
    inst = float(rec.get('local_total') or 0) - float(lokal.get('CP', 0)) - float(lokal.get('ID', 0))
    beredar = max(ritel + asing_dagang + inst, 0.15 * scripless)
    return {
        'sec_num': float(rec.get('sec_num') or 0),
        'harga_ksei': float(rec.get('price') or 0),
        'mcap': float(rec.get('sec_num') or 0) * float(rec.get('price') or 0),
        'scripless': scripless,
        'beredar_lot': beredar / aturan.LOT,
        'pct_pengendali': cp / scripless,
        'porsi_pemilik': {
            'ritel': ritel / beredar,
            'asing': max(asing_dagang, 0) / beredar,
            'institusi': max(inst, 0) / beredar,
        },
    }


_SEKTOR = {}


def peta_sektor():
    """{kode: sektor} dari registri IDX. Disimpan di memori selama pohon
    kepemilikan tidak berubah -- membaca ~900 berkas tiap buka halaman
    Digital Twin makan ~2 detik."""
    ts = kepemilikan_terbaru()
    if _SEKTOR.get('ts') == ts and 'peta' in _SEKTOR:
        return _SEKTOR['peta']
    sek = {}
    for f in glob.glob(os.path.join(IDX_DIR, '*', '*.json')):
        try:
            with open(f, encoding='utf-8') as fh:
                j = json.load(fh)
        except Exception:
            continue
        if j.get('sector') and j.get('ticker'):
            sek[j['ticker']] = j['sector']
    _SEKTOR.update({'ts': ts, 'peta': sek})
    return sek


# ------------------------------------------------------- broker (bruto)
def _folder_json(n):
    """n folder tanggal terakhir yang berisi JSON Stockbit (s/d 15 Sep 2026)."""
    hasil = []
    for nama in sorted(os.listdir(ALL_DIR), reverse=True):
        p = os.path.join(ALL_DIR, nama)
        if not os.path.isdir(p):
            continue
        if glob.glob(os.path.join(p, 'BBCA_ALL_*.json')) or glob.glob(os.path.join(p, '*_ALL_*.json'))[:1]:
            hasil.append(p)
        if len(hasil) >= n:
            break
    return hasil


def _baca_json(path):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)['data']['broker_summary']
    except Exception:
        return None


def peta_tipe_broker(folder):
    """{kode: 'Asing'/'Lokal'/'Pemerintah'} dari field `type` JSON. Tipe
    adalah sifat broker, jadi beberapa saham besar di beberapa hari cukup."""
    peta = {}
    for p in folder[:3]:
        for t in ('BBCA', 'BBRI', 'TLKM', 'ASII', 'BMRI', 'GOTO', 'ANTM', 'BUMI', 'ADRO', 'UNVR'):
            for f in glob.glob(os.path.join(p, '%s_ALL_*.json' % t)):
                bs = _baca_json(f)
                if not bs:
                    continue
                for r in (bs.get('brokers_buy') or []) + (bs.get('brokers_sell') or []):
                    k = r.get('netbs_broker_code')
                    if k and r.get('type'):
                        peta[k] = r['type']
    if not peta:
        peta = {k: 'Asing' for k in BROKER_ASING_CADANGAN}
    return peta


def kelompok_broker(kode, tipe):
    if kode in BROKER_RITEL:
        return 'ritel'
    if tipe.get(kode) == 'Asing':
        return 'asing'
    return 'lokal'


def komposisi_bruto(t, folder, tipe):
    """
    Porsi nilai BRUTO tiap kelompok broker + nilai rata-rata per transaksi.

    Daftar beli/jual JSON terpisah per broker (net buyer ATAU net seller):
      net buyer : beli bruto = bvalv, jual bruto = bvalv - bval
      net seller: jual bruto = svalv, beli bruto = svalv - |sval|
    Jumlah bruto beli+jual seluruh broker = 2x nilai transaksi pasar.
    """
    bruto = {'ritel': 0.0, 'asing': 0.0, 'lokal': 0.0}
    frek = {'ritel': 0.0, 'asing': 0.0, 'lokal': 0.0}
    searah = {'ritel': [], 'asing': [], 'lokal': []}
    hari = 0
    for p in folder:
        fs = glob.glob(os.path.join(p, '%s_ALL_*.json' % t))
        if not fs:
            continue
        bs = _baca_json(fs[0])
        if not bs:
            continue
        hari += 1
        net_h = {'ritel': 0.0, 'asing': 0.0, 'lokal': 0.0}
        bruto_h = {'ritel': 0.0, 'asing': 0.0, 'lokal': 0.0}
        for r in bs.get('brokers_buy') or []:
            g = kelompok_broker(r.get('netbs_broker_code'), tipe)
            bv, net = _f(r.get('bvalv'), 0), abs(_f(r.get('bval'), 0))
            bruto_h[g] += max(2 * bv - net, 0)
            net_h[g] += net
            frek[g] += _f(r.get('freq'), 0)
        for r in bs.get('brokers_sell') or []:
            g = kelompok_broker(r.get('netbs_broker_code'), tipe)
            sv, net = _f(r.get('svalv'), 0), abs(_f(r.get('sval'), 0))
            bruto_h[g] += max(2 * sv - net, 0)
            net_h[g] -= net
            frek[g] += _f(r.get('freq'), 0)
        for g in bruto:
            bruto[g] += bruto_h[g]
            if bruto_h[g] > 0:
                searah[g].append(abs(net_h[g]) / bruto_h[g])
    tot = sum(bruto.values())
    if hari == 0 or tot <= 0:
        return None
    return {
        'hari': hari,
        'porsi': {g: bruto[g] / tot for g in bruto},
        'nilai_per_transaksi': {g: (bruto[g] / frek[g] if frek[g] > 0 else None) for g in bruto},
        'nilai_harian': tot / 2 / hari,
        # seberapa SEARAH arus satu kelompok dalam sehari: |netto| / bruto.
        # 0 = beli dan jual seimbang (kelompoknya beragam), 1 = semua satu arah.
        'searah': {g: (float(np.median(v)) if v else None) for g, v in searah.items()},
    }


# ----------------------------------------------------- broker (netto)
def perilaku_ledger(tickers, tipe, harga):
    """
    Dari buku besar broker (arus NETTO harian), per saham:
      - korelasi arus netto tiap kelompok dengan return HARI YANG SAMA dan
        dengan return 5 hari SEBELUMNYA (ikut tren vs melawan) -- target
        perilaku yang dibandingkan dengan twin di validasi.py;
      - jejak bandar: broker lokal non-ritel yang arah netto hariannya
        kompak (|jumlah| / jumlah |harian| >= 0,5) dan besarnya >= 2% volume.
    """
    from ..broker_ledger import load
    df, meta = load()
    if df is None:
        return {}, None
    sub = df[df['stock'].astype(str).isin(tickers)]
    if sub.empty:
        return {}, meta
    sub = sub.assign(
        stock=sub['stock'].astype(str), broker=sub['broker'].astype(str),
        tanda=np.where(sub['side'].astype(str) == 'buy', 1.0, -1.0))
    sub = sub.assign(nilai_net=sub['tanda'] * sub['value'], lot_net=sub['tanda'] * sub['lot'],
                     grup=[kelompok_broker(b, tipe) for b in sub['broker']])
    keluar = {}
    for t, s in sub.groupby('stock'):
        h = harga.get(t)
        if h is None or len(h) < 40:
            continue
        nilai_pasar = (h['Close'] * h['Volume']).rename('nilai')
        r = np.log(h['Close']).diff().rename('r')
        r5_lalu = r.rolling(5).sum().shift(1).rename('r5_lalu')
        r5_depan = r.rolling(5).sum().shift(-5).rename('r5_depan')
        net = s.pivot_table(index='date', columns='grup', values='nilai_net', aggfunc='sum').fillna(0.0)
        gab = pd.concat([net, nilai_pasar, r, r5_lalu, r5_depan], axis=1, join='inner').dropna()
        if len(gab) < 30:
            continue
        kor = {}
        for g in ('ritel', 'asing', 'lokal'):
            if g not in gab:
                continue
            x = gab[g] / gab['nilai']
            if x.std() <= 0:
                continue
            kor[g] = {
                'hari_sama': _f(np.corrcoef(x, gab['r'])[0, 1], 0.0),
                'tren_5h_lalu': _f(np.corrcoef(x, gab['r5_lalu'])[0, 1], 0.0),
                'tren_5h_depan': _f(np.corrcoef(x, gab['r5_depan'])[0, 1], 0.0),
            }

        # jejak bandar di jendela terakhir. Pembaginya volume Summary ATAU
        # separuh jumlah |netto| seluruh broker, mana yang lebih besar: buku
        # besar ikut memuat pasar negosiasi (crossing), Summary tidak --
        # tanpa ini GOTO memunculkan broker dengan "porsi" 108% volume.
        tgl = sorted(s['date'].unique())[-HARI_BANDAR:]
        w = s[(s['date'].isin(tgl)) & (s['grup'] == 'lokal')]
        vol_reg = (h['Volume'] / aturan.LOT).reindex(pd.to_datetime(tgl)).sum()
        vol_net = s[s['date'].isin(tgl)]['lot'].sum() / 2.0
        vol_lot = max(vol_reg, vol_net)
        kandidat = []
        if vol_lot > 0:
            for b, x in w.groupby('broker'):
                harian = x.groupby('date')['lot_net'].sum()
                tot_abs = harian.abs().sum()
                if tot_abs <= 0 or len(harian) < 0.3 * len(tgl):
                    continue
                kompak = abs(harian.sum()) / tot_abs
                porsi = tot_abs / vol_lot
                if kompak >= 0.5 and porsi >= 0.02:
                    kandidat.append({'broker': b, 'kompak': float(kompak), 'porsi': float(porsi),
                                     'arah': 'akumulasi' if harian.sum() > 0 else 'distribusi',
                                     'hari_hadir': int(len(harian))})
        kandidat.sort(key=lambda k: -k['porsi'])
        keluar[t] = {
            'korelasi': kor,
            'n_hari': int(len(gab)),
            'bandar': kandidat[:3],
            'porsi_bandar': float(min(0.4, sum(k['porsi'] for k in kandidat))),
        }
    return keluar, meta


# ----------------------------------------------------------- order book
def buku_nyata(t):
    """Spread (dalam fraksi) dan kedalaman 5 level per sisi dari snapshot
    <T>_ORDER_BOOK.json -- hanya ada 24 Agu-15 Sep 2026."""
    spread, dalam_bid, dalam_offer, asing = [], [], [], []
    for f in sorted(glob.glob(os.path.join(ALL_DIR, '*', '%s_ORDER_BOOK.json' % t))):
        try:
            with open(f, encoding='utf-8') as fh:
                d = json.load(fh)['data']
            bid = [(float(x['price']), float(x['volume'])) for x in d.get('bid') or [] if float(x['volume'] or 0) > 0]
            off = [(float(x['price']), float(x['volume'])) for x in d.get('offer') or [] if float(x['volume'] or 0) > 0]
        except Exception:
            continue
        if not bid or not off:
            continue
        bid.sort(key=lambda x: -x[0])
        off.sort(key=lambda x: x[0])
        if off[0][0] > bid[0][0]:
            spread.append((off[0][0] - bid[0][0]) / float(aturan.fraksi(bid[0][0])))
        dalam_bid.append(sum(v for _, v in bid[:5]) / aturan.LOT)
        dalam_offer.append(sum(v for _, v in off[:5]) / aturan.LOT)
        if d.get('foreign') not in (None, ''):
            asing.append(_f(d.get('foreign'), None))
    if not spread:
        return None
    return {
        'hari': len(spread),
        'spread_fraksi': float(np.median(spread)),
        'dalam_5_bid_lot': float(np.median(dalam_bid)),
        'dalam_5_offer_lot': float(np.median(dalam_offer)),
        'porsi_asing_pct': float(np.nanmedian([a for a in asing if a is not None])) if asing else None,
    }


# --------------------------------------------------------------- profil
def _profil_saham(t, ih, ksei, sektor, folder, tipe):
    h = baca_summary(t)
    if h is None or len(h) < 40:
        return None, 'data Summary %s tidak ada / terlalu pendek' % t
    akhir = h.tail(HARI_ADV)
    p0 = aturan.bulat_dekat(float(h['Close'].iloc[-1]))
    adv_lot = float(akhir['Volume'].mean() / aturan.LOT)
    adv_nilai = float((akhir['Volume'] * akhir['Close']).mean())

    # statistik return: Yahoo 2 tahun (disesuaikan aksi korporasi) kalau ada
    y = _harga_yahoo().get(t)
    if y is not None and len(y) > 260:
        cy = y['Close'].astype(float)
        cy = cy[cy > 0]
        cy = cy[~cy.index.duplicated(keep='last')].tail(HARI_STAT + 1)
        r = np.log(cy).diff().dropna()
        v = y['Volume'].reindex(r.index).astype(float)
        sumber_stat = 'Yahoo %s s/d %s' % (str(r.index[0].date()), str(r.index[-1].date()))
    else:
        r = np.log(h['Close']).diff().dropna()
        v = h['Volume'].reindex(r.index)
        sumber_stat = 'Summary 2026'
    fakta = fakta_return(r.values, v.values)
    ret_asli = [float(x) for x in r.values]
    vol_asli = [float(x) if np.isfinite(x) else None for x in v.values]

    # beta terhadap IHSG
    ih_r = pd.Series(ih['ret'], index=pd.to_datetime(ih['tanggal']))
    gab = pd.concat([r.rename('s'), ih_r.rename('m')], axis=1, join='inner').dropna()
    if len(gab) > 60 and gab['m'].var() > 0:
        beta = float(np.cov(gab['s'], gab['m'])[0, 1] / gab['m'].var())
        r2 = float(np.corrcoef(gab['s'], gab['m'])[0, 1] ** 2)
    else:
        beta, r2 = 1.0, 0.0
    beta = float(np.clip(beta, 0.1, 2.5))

    # ARA/ARB nyata sejak ARB 15% (8 Apr 2025)
    m = _harga_mentah().get(t)
    if m is not None:
        m = m[~m.index.duplicated(keep='last')]
        m = m[m.index >= '2025-04-08']
    ara, arb = _hit_batas(m) if m is not None else (None, None)

    rec = (ksei or {}).get('securities', {}).get(t)
    pemilik = komposisi_pemilik(rec) if rec else None
    bruto = komposisi_bruto(t, folder, tipe) if folder else None
    buku = buku_nyata(t)

    return {
        'kode': t,
        'sektor': sektor.get(t, '-'),
        'harga': p0,
        'tanggal_harga': str(h.index[-1].date()),
        'adv_lot': adv_lot,
        'adv_nilai': adv_nilai,
        'beta': beta,
        'r2_ihsg': r2,
        'fakta': fakta,
        'ret_asli': ret_asli,
        'vol_asli': vol_asli,
        'sumber_stat': sumber_stat,
        'ara_nyata': ara,
        'arb_nyata': arb,
        'pemilik': pemilik,
        'bruto': bruto,
        'buku_nyata': buku,
        'riwayat_close': [float(x) for x in h['Close'].tail(120)],
        'riwayat_tanggal': [str(d.date()) for d in h.index[-120:]],
    }, None


VERSI_PROFIL = 4      # naikkan kalau isi profil berubah bentuk


# Episode MSCI nyata di data project. Hari 0 = hari bursa pertama yang
# bereaksi terhadap pengumuman (diumumkan malam waktu AS).
EPISODE_MSCI = {
    'jan2026': {'tanggal0': '2026-01-28',
                'judul': 'MSCI membekukan rebalancing Indonesia (free float), 28 Jan 2026'},
    'jun2026': {'tanggal0': '2026-06-24',
                'judul': 'MSCI menunda review status & beri tenggat November, 24 Jun 2026'},
}
PANJANG_EPISODE = 10


def episode_msci(tickers, tipe, harga, ih):
    """
    Untuk tiap episode: return log IHSG per hari (hari 0..9), lalu per saham
    arus netto asing/ritel/lokal per hari DIBAGI nilai transaksi harian
    rata-rata 60 hari sebelum episode, plus return kumulatif nyata (untuk
    validasi). Dipakai event 'msci' mode putar ulang di skenario.py.
    """
    from ..broker_ledger import load
    df, _ = load()
    ih_s = pd.Series(ih['ret'], index=pd.to_datetime(ih['tanggal']))
    sub = None
    if df is not None:
        sub = df[df['stock'].astype(str).isin(tickers)]
        sub = sub.assign(stock=sub['stock'].astype(str),
                         grup=[kelompok_broker(b, tipe) for b in sub['broker'].astype(str)],
                         net=np.where(sub['side'].astype(str) == 'buy', 1.0, -1.0) * sub['value'])
        sub = sub.pivot_table(index=['date', 'stock'], columns='grup', values='net', aggfunc='sum').fillna(0.0)
    keluar = {}
    for nama, ep in EPISODE_MSCI.items():
        d0 = pd.Timestamp(ep['tanggal0'])
        tgl = ih_s.index[ih_s.index >= d0][:PANJANG_EPISODE]
        if len(tgl) < PANJANG_EPISODE:
            continue
        per = {}
        for t in tickers:
            h = harga.get(t)
            if h is None or (h.index < d0).sum() < 10:   # Summary mulai 2 Jan 2026
                continue
            adv = float((h['Close'] * h['Volume'])[h.index < d0].tail(60).mean())
            p0 = float(h['Close'][h.index < d0].iloc[-1])
            cl = h['Close'].reindex(tgl)
            arus = {}
            for gname in ('asing', 'ritel', 'lokal'):
                if sub is not None and t in sub.index.get_level_values('stock') and gname in sub.columns:
                    x = sub.xs(t, level='stock')[gname].reindex(tgl).fillna(0.0) / max(adv, 1.0)
                    arus[gname] = [float(v) for v in x]
                else:
                    arus[gname] = [0.0] * len(tgl)
            per[t] = {'ret_kum': [None if not np.isfinite(v) else float(v / p0 - 1) for v in cl.values],
                      'arus': arus}
        keluar[nama] = {'judul': ep['judul'], 'tanggal': [str(d.date()) for d in tgl],
                        'ihsg_r': [float(v) for v in ih_s.reindex(tgl).values], 'saham': per}
    return keluar


def _kunci_cache(tickers):
    return hashlib.md5((','.join(sorted(tickers)) + '#%d' % VERSI_PROFIL).encode()).hexdigest()[:12]


def profil(tickers=None, paksa=False):
    """
    Profil kalibrasi untuk sekumpulan saham. Return dict:
      ihsg   ringkasan IHSG (level, return harian, sumber)
      saham  {kode: profil}
      perilaku  {kode: korelasi arus persona + jejak bandar}
      pasar  kapitalisasi seluruh pasar (untuk menghitung dampak ke IHSG)
      catatan  hal-hal yang perlu diketahui pembaca (data hilang, dsb.)
    """
    tickers = [t.strip().upper() for t in (tickers or BAWAAN) if t and t.strip()]
    tickers = list(dict.fromkeys(tickers))
    _pastikan_cache_dir()
    berkas = str(_runtime_file('twin/cache', 'profil_%s.pkl' % _kunci_cache(tickers)))
    sumber_ts = paling_baru(summary_terbaru(), berkas_terbaru(LEDGER_FILE), kepemilikan_terbaru())
    if not paksa and os.path.exists(berkas):
        try:
            with open(berkas, 'rb') as fh:
                c = pickle.load(fh)
            if c.get('ts', 0) >= sumber_ts:
                return c['profil']
        except Exception:
            pass

    catatan = []
    seri, sumber = ihsg()
    ih = ringkas_ihsg(seri, sumber)
    if 'gagal' in sumber:
        catatan.append('IHSG: %s' % sumber)

    ksei = ksei_terbaru()
    if ksei is None:
        catatan.append('Data KSEI tidak ada -- kepemilikan awal memakai bawaan.')
    sektor = peta_sektor()
    folder = _folder_json(HARI_JSON)
    tipe = peta_tipe_broker(folder) if folder else {k: 'Asing' for k in BROKER_ASING_CADANGAN}

    saham = {}
    for t in tickers:
        p, err = _profil_saham(t, ih, ksei, sektor, folder, tipe)
        if p is None:
            catatan.append(err)
            continue
        saham[t] = p
    if not saham:
        raise ValueError('Tidak ada saham yang punya data cukup: %s' % ', '.join(tickers))

    harga = {t: baca_summary(t) for t in saham}
    perilaku, meta = perilaku_ledger(list(saham), tipe, harga)
    try:
        episode = episode_msci(list(saham), tipe, harga, ih)
    except Exception as exc:
        episode = {}
        catatan.append('Episode MSCI tidak terbaca: %s' % exc)

    mcap_total = None
    if ksei:
        mcap_total = float(sum((r.get('sec_num') or 0) * (r.get('price') or 0)
                               for r in ksei['securities'].values()))

    hasil = {
        'dibangun': time.strftime('%Y-%m-%d %H:%M'),
        'ihsg': ih,
        'saham': saham,
        'perilaku': perilaku,
        'episode_msci': episode,
        'pasar': {
            'mcap_total': mcap_total,
            'ksei_bulan': (ksei or {}).get('as_of'),
            'json_hari': len(folder),
            'json_sampai': os.path.basename(folder[0]) if folder else None,
            'ledger': {k: (meta or {}).get(k) for k in ('dari', 'sampai', 'n_hari')} if meta else None,
        },
        'tipe_broker': tipe,
        'catatan': catatan,
    }
    try:
        with open(berkas, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'profil': hasil}, fh)
    except Exception:
        pass
    return hasil


def kandidat():
    """Saham yang bisa dipilih: punya Summary + KSEI. Diurut kapitalisasi."""
    ksei = ksei_terbaru() or {'securities': {}}
    ada = {n[:-12] for n in os.listdir(SUMMARY_DIR) if n.endswith('_Summary.csv')}
    keluar = []
    for t, rec in ksei['securities'].items():
        if t not in ada:
            continue
        mcap = float(rec.get('sec_num') or 0) * float(rec.get('price') or 0)
        if mcap > 0:
            keluar.append({'kode': t, 'mcap_t': mcap / 1e12})
    keluar.sort(key=lambda r: -r['mcap_t'])
    return keluar
