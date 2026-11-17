"""
Dicicil Insider: emiten yang sahamnya DIBELI RUTIN oleh orang dalam --
sedikit-sedikit tapi berminggu-minggu, nyaris tanpa jual.

BEDANYA DENGAN RADAR INSIDER
Radar Insider (insider_signal.py) bertanya "kapan transaksi insider
BERARTI buat arah harga?" -- jawabannya cuma di dua konteks harga (Jatuh
Dalam, Akumulasi Palsu), dan insider BELI di luar itu menang 49,5% di
H+40, koin lempar. Halaman ini bertanya hal lain: "SIAPA yang sedang
konsisten menambah posisi?" -- tanpa memandang konteks harga. Itu bahan
pemantauan (pemegang strategis yang mencicil, mis. Grab di SUPA 8 Okt
2026), BUKAN sinyal: belum pernah diuji apakah beli-rutin berminggu-
minggu punya nilai lebih dari beli sekali.

ATURAN "DICICIL" (jendela HARI hari kalender ke belakang dari transaksi
insider terbaru):
  - ada beli di pasar di >= MIN_MINGGU minggu kalender yang berbeda
  - hari jual <= RASIO_JUAL x hari beli
  - posisi bersih para pembeli naik
  - beli terakhir <= SEGAR_HARI hari sebelum transaksi terbaru di data

JEBAKAN DATA YANG SUDAH DITEMUKAN (dan ditangani di sini)
  - Transaksi sama dilaporkan KSEI dan IDX terpisah, dan kedua sumber
    kadang memakai BASIS POSISI BERBEDA untuk pemegang yang sama (IMPC:
    21,1 M vs 5,2 M lembar). Net dihitung dari posisi awal->akhir PER
    SUMBER, lalu diambil sumber dengan catatan terbanyak -- bukan
    menjumlah transaksi (dobel) dan bukan mencampur sumber (kacau).
  - Rekening sekuritas / kustodian / nominee (Samuel Sekuritas bolak-
    balik di NSSS, Pershing, Bank of Singapore) bukan "orang dalam".
  - Harga lapor Rp1 = alokasi program saham karyawan (LTIP), bukan beli
    di pasar (lima direksi SUPA 12 Agu 2026).
  - Buyback perusahaan sendiri ditandai.

TRANSAKSI BESAR (>= 0,5% saham dalam satu laporan) dipilah dua:
  - PINDAH KANTONG -- punya PASANGAN: orang dalam lain melakukan
    transaksi berlawanan dengan jumlah lembar ~sama (selisih <= 2%) dalam
    +-3 hari (IMPC 12 Agu 2026: Tunggal Jaya jual 1,45 M lembar, Phillip
    Tjipto beli 1,45 M di harga sama), atau pemegang yang sama punya
    catatan Transfer non-pasar sejumlah itu (Harimas, IMPC 23-24 Sep).
    Uang muter di kantong yang sama -> netral: DIKELUARKAN dari net posisi
    dan dari hitungan hari/minggu beli.
  - BELI BESAR -- tanpa pasangan: ada yang membayar sungguhan untuk
    porsi besar (Firstindo 5,2% di EURO 14 Sep 2026). Ditandai positif
    beserta harga & premi terhadap close hari itu. Penilaian "positif"
    ini keputusan pemakai, BELUM diuji -- event study insider belum
    pernah memisahkan ukuran transaksi.
  Laporan dobel IDX+KSEI digabung dulu (pemegang & arah sama, jumlah ~sama,
  <= 5 hari) supaya satu transaksi tidak berpasangan dengan dirinya sendiri.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import logging
import os
import pickle
import re
import time
from datetime import timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CACHE_FILE = str(_runtime_file('', 'dicicil_insider_cache.pkl'))

C = {
    'HARI': 60,           # jendela, hari kalender
    'MIN_MINGGU': 4,      # minggu kalender berbeda yang ada belinya
    'RASIO_JUAL': 0.2,    # hari jual <= 20% hari beli
    'SEGAR_HARI': 10,     # beli terakhir maks. 10 hari sebelum transaksi terbaru di data
    'BESAR': 0.005,       # satu laporan >= 0,5% saham = transaksi besar
    'MIRIP': 0.02,        # jumlah lembar dianggap sama kalau selisih <= 2%
    'PASANGAN_HARI': 3,   # jarak maks. transaksi berpasangan (pindah kantong)
    'DOBEL_HARI': 5,      # jarak maks. laporan IDX vs KSEI utk transaksi yg sama
    'HARGA_LTIP': 1.0,    # harga lapor <= ini = alokasi saham karyawan
    'MIN_NILAI': 1e9,     # median nilai 20 hari utk tanda "likuid" (sama dgn riset)
}

NOMINEE = re.compile(
    r'SEKURITAS|SECURITIES|CUSTOD|NOMINEE|PERSHING|CLEARSTREAM|EUROCLEAR|'
    r'\bBANK OF SINGAPORE\b|\bS/A\b|\bA/C\b|UBS AG|CITIBANK|HSBC|DBS BANK|JPMORGAN|'
    r'STANDARD CHARTERED', re.I)


def _norm(nama):
    n = (nama or '').upper()
    n = re.sub(r'\b(PT|TBK|PERSERO)\b|[.,()]', ' ', n)
    return re.sub(r'\s+', ' ', n).strip()


def _net_posisi(h):
    """Perubahan posisi satu pemegang di jendela, per sumber (lihat docstring)."""
    kandidat = []
    for _src, hs in h.groupby('source'):
        awal, akhir = hs['shares_prev'].dropna(), hs['shares_curr'].dropna()
        if len(awal) and len(akhir):
            kandidat.append((len(hs), float(akhir.iloc[-1] - awal.iloc[0])))
    if kandidat:
        return max(kandidat)[1]
    return float((h['arah'] * h['shares_changed'].abs()).sum())


def _mirip(a, b):
    return abs(a - b) <= C['MIRIP'] * max(a, b)


def _transaksi_besar(g, transfer, lembar, close):
    """
    Pilah transaksi besar satu emiten jadi pindah kantong vs beli besar.
    g: transaksi pasar (sudah tanpa nominee/LTIP/buyback), transfer: baris
    non-pasar emiten ini, close: Series close per tanggal (untuk premi).
    Mengembalikan (indeks baris pindah kantong, daftar beli besar, daftar
    pindah kantong, {pemegang: lembar bertanda yang dikeluarkan dari net}).
    """
    if not lembar:
        return set(), [], [], {}
    besar = g[g['shares_changed'].abs() >= C['BESAR'] * lembar].sort_values('date')
    kejadian = []
    for idx, r in besar.iterrows():
        jml = abs(float(r['shares_changed']))
        harga = pd.to_numeric(r['price_reported'], errors='coerce')
        harga = float(harga) if pd.notna(harga) and harga > C['HARGA_LTIP'] else None
        for e in kejadian:
            if (e['pemegang'] == r['pemegang'] and e['arah'] == r['arah'] and _mirip(e['lembar'], jml)
                    and abs((r['date'] - e['date']).days) <= C['DOBEL_HARI']):
                e['idx'].append(idx)
                e['harga'] = e['harga'] or harga
                break
        else:
            kejadian.append({'idx': [idx], 'pemegang': r['pemegang'], 'nama': str(r['name']).title(),
                             'arah': int(r['arah']), 'lembar': jml, 'date': r['date'], 'harga': harga})

    for e in kejadian:
        for f in kejadian:
            if (f is not e and f['arah'] == -e['arah'] and f['pemegang'] != e['pemegang']
                    and _mirip(f['lembar'], e['lembar'])
                    and abs((f['date'] - e['date']).days) <= C['PASANGAN_HARI']):
                e['pasangan'] = f['nama']
                break
        if not e.get('pasangan') and len(transfer):
            t = transfer[(transfer['pemegang'] == e['pemegang'])
                         & ((transfer['date'] - e['date']).dt.days.abs() <= C['PASANGAN_HARI'])]
            if any(_mirip(abs(float(x)), e['lembar']) for x in t['shares_changed'] if pd.notna(x) and x):
                e['pasangan'] = 'transfer internal'

    pindah_idx, kurangi, beli_besar, pindah = set(), {}, [], []
    for e in kejadian:
        info = {'tanggal': e['date'].strftime('%Y-%m-%d'), 'nama': e['nama'],
                'pct': round(e['lembar'] / lembar * 100, 2),
                'arah': 'beli' if e['arah'] == 1 else 'jual', 'harga': e['harga']}
        if e.get('pasangan'):
            pindah_idx.update(e['idx'])
            kurangi[e['pemegang']] = kurangi.get(e['pemegang'], 0.0) + e['arah'] * e['lembar']
            info['pasangan'] = e['pasangan']
            pindah.append(info)
        elif e['arah'] == 1:
            c = close.get(e['date'].normalize()) if close is not None else None
            info['premi'] = round(float(e['harga'] / c - 1) * 100, 1) if e['harga'] and c else None
            beli_besar.append(info)
    return pindah_idx, beli_besar, pindah, kurangi


def _harga(ticker):
    from .stock_hub import load_summary
    df = load_summary(ticker)
    if df is None or len(df) < 21:
        return {}
    df = df.tail(60)
    cl = df['Close'].astype(float)
    return {
        'close': float(cl.iloc[-1]),
        'nilai20_m': float((cl * df['Volume'].astype(float)).tail(20).median()) / 1e9,
        'ret20': float(cl.iloc[-1] / cl.iloc[-21] - 1) * 100,
        'ret_jendela': float(cl.iloc[-1] / cl.iloc[0] - 1) * 100,
        'dari_puncak': float(cl.iloc[-1] / cl.max() - 1) * 100,
    }


def _bangun(hari, min_minggu):
    from .insider_activity import load_all
    from .ownership import build_ownership

    d = load_all()
    if d is None or d.empty:
        return {'available': False, 'message': 'Data insider kosong.'}
    akhir = d['date'].max()
    mulai = akhir - timedelta(days=hari)
    d = d[d['date'] > mulai - timedelta(days=C['PASANGAN_HARI'])].copy()
    d['pemegang'] = d['name'].map(_norm)
    # Baris non-pasar (Transfer, dll.) cuma dipakai untuk mengenali pindah
    # kantong; semua hitungan lain dari transaksi pasar.
    transfer_semua = d[d['is_market_trade'] != True]  # noqa: E712 -- kolom bisa object
    d = d[(d['is_market_trade'] == True) & (d['date'] > mulai)].copy()  # noqa: E712
    d['arah'] = np.where(d['action_type'] == 'ACTION_TYPE_BUY', 1,
                         np.where(d['action_type'] == 'ACTION_TYPE_SELL', -1, 0))
    d = d[d['arah'] != 0]
    d['nominee'] = d['name'].fillna('').str.contains(NOMINEE)
    harga_lapor = pd.to_numeric(d['price_reported'], errors='coerce')
    d['ltip'] = (harga_lapor > 0) & (harga_lapor <= C['HARGA_LTIP'])
    # Minggu dihitung dari awal jendela, supaya pergantian tahun tidak
    # mengacak urutan dan strip mingguan di halaman selalu berurutan.
    d['minggu'] = ((d['date'] - mulai).dt.days // 7).astype(int)
    n_minggu = int((akhir - mulai).days // 7) + 1

    baris, dibuang = [], {'nominee': 0, 'ltip': 0}
    for ticker, g in d.groupby('ticker'):
        dibuang['nominee'] += int(g['nominee'].sum())
        dibuang['ltip'] += int((g['ltip'] & ~g['nominee']).sum())
        g = g[~g['nominee'] & ~g['ltip']]
        if g.empty or not (g['arah'] == 1).any():
            continue
        try:
            o = build_ownership(ticker)
        except Exception:
            o = {}
        lembar = o.get('sec_num') if o.get('available') else None
        emiten = _norm(o.get('name') or '')
        g = g.assign(buyback=g['pemegang'].apply(lambda p: bool(emiten) and (p in emiten or emiten in p)))
        insider_semua = g[~g['buyback']]
        close = None
        try:
            from .stock_hub import load_summary
            s_df = load_summary(ticker)
            if s_df is not None and len(s_df):
                close = pd.Series(s_df['Close'].astype(float).values,
                                  index=pd.to_datetime(s_df['Date']).dt.normalize())
        except Exception:
            close = None
        pindah_idx, beli_besar, pindah, kurangi = _transaksi_besar(
            insider_semua, transfer_semua[transfer_semua['ticker'] == ticker], lembar, close)
        insider = insider_semua.drop(index=list(pindah_idx))
        beli = insider[insider['arah'] == 1]
        jual = insider[insider['arah'] == -1]
        if beli.empty:
            continue
        hari_beli = beli['date'].dt.date.nunique()
        hari_jual = jual['date'].dt.date.nunique()
        minggu_beli = sorted(beli['minggu'].unique().tolist())
        terakhir = beli['date'].max()
        # Net dari POSISI (memuat semua transaksi pemegang itu), lalu jumlah
        # pindah kantongnya dikeluarkan -- pemegang yang seluruh transaksinya
        # pindah kantong jadi nol, bukan hilang dari hitungan.
        net = sum(_net_posisi(h) - kurangi.get(p, 0.0)
                  for p, h in insider_semua.sort_values('date').groupby('pemegang'))
        if not (len(minggu_beli) >= min_minggu and hari_jual <= C['RASIO_JUAL'] * hari_beli
                and net > 0 and terakhir >= akhir - timedelta(days=C['SEGAR_HARI'])):
            continue

        pembeli = []
        for p, h in beli.groupby('pemegang'):
            pembeli.append({'nama': h['name'].iloc[-1].title(), 'n': int(len(h)),
                            'hari': int(h['date'].dt.date.nunique())})
        pembeli.sort(key=lambda x: -x['hari'])
        row = {
            'ticker': ticker,
            'nama': (o.get('name') or '').replace('PT ', '').replace(' Tbk', '').replace(' Tbk.', '')[:34],
            'minggu_beli': len(minggu_beli),
            'strip': [1 if i in minggu_beli else 0 for i in range(n_minggu)],
            'hari_beli': int(hari_beli),
            'hari_jual': int(hari_jual),
            'n_pembeli': len(pembeli),
            'pembeli': pembeli[:4],
            'net_pct': round(net / lembar * 100, 3) if lembar else None,
            'beli_pertama': beli['date'].min().strftime('%Y-%m-%d'),
            'beli_terakhir': terakhir.strftime('%Y-%m-%d'),
            'beli_besar': beli_besar,
            'pindah_kantong': pindah,
            'buyback': bool((g['buyback'] & (g['arah'] == 1)).any()),
        }
        row.update(_harga(ticker))
        row['likuid'] = (row.get('nilai20_m') or 0) * 1e9 >= C['MIN_NILAI']
        baris.append(row)

    baris.sort(key=lambda r: (-r['minggu_beli'], -r['hari_beli']))
    return {
        'available': True,
        'as_of': akhir.strftime('%Y-%m-%d'),
        'mulai': mulai.strftime('%Y-%m-%d'),
        'hari': hari, 'min_minggu': min_minggu, 'n_minggu': n_minggu,
        'n_emiten_beli': int(d[(d['arah'] == 1) & ~d['nominee'] & ~d['ltip']]['ticker'].nunique()),
        'dibuang': dibuang,
        'config': C,
        'rows': baris,
    }


def _sumber_terbaru():
    """mtime terbaru dari data insider maupun Summary (harga ikut tampil)."""
    from .insider_activity import INSIDER_DIR
    from .kesegaran import summary_terbaru
    try:
        insider = max((os.path.getmtime(p) for p in
                       glob.glob(os.path.join(INSIDER_DIR, '*', '*_INSIDER.json'))), default=0)
    except OSError:
        insider = 0
    return max(insider, summary_terbaru() or 0)


def scan(hari=None, min_minggu=None, force=False):
    hari = int(hari or C['HARI'])
    min_minggu = int(min_minggu or C['MIN_MINGGU'])
    kunci = (hari, min_minggu)
    simpan = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                simpan = pickle.load(fh)
        except Exception:
            simpan = {}
    lama = simpan.get(kunci)
    if not force and lama and lama.get('ts', 0) >= _sumber_terbaru():
        hasil = dict(lama['result'])
        hasil['from_cache'] = True
        return hasil

    hasil = _bangun(hari, min_minggu)
    simpan[kunci] = {'ts': time.time(), 'result': hasil}
    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump(simpan, fh)
    except Exception:
        logger.exception('Gagal menyimpan cache Dicicil Insider')
    return hasil
