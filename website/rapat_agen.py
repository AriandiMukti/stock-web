"""
Rapat Agen: beberapa "agen" berperan, tiap pagi merapatkan kandidat saham
-- tanpa model bahasa. Setiap agen adalah sekumpulan aturan, dan SETIAP
argumen yang mereka ucapkan menempel ke hasil uji yang sudah ada di app
ini. Agen tidak menciptakan informasi baru; yang mereka lakukan adalah
menimbang semua yang sudah diketahui, secara konsisten, untuk tiap saham,
lalu mencatat keputusannya supaya bisa dinilai maju.

PERAN
  Pengumpul      dua sumber kandidat (permintaan pengguna, 9 Okt 2026):
                 (a) harga dekat support chart (0-2% di atas support terdekat,
                     rumus support = utilities.compute_levels 100 bar, sama
                     dengan chart Halaman Saham), emiten likuid;
                 (b) saham yang sedang DICICIL insider (dicicil_insider.py).
  Analis         argumen UNTUK: pantul support + di atas MA200, Skor Kecondongan
                 desil 10, insider beli dalam konteks Akumulasi Palsu, plus fakta
                 kandidat (jarak support, cicilan insider). Tembus basis & puncak
                 52 minggu SENGAJA tidak dipakai (keputusan pengguna, 9 Okt 2026):
                 rapat ini menilai kandidat support/insider dengan kakinya sendiri.
  Pembantah      argumen MELAWAN: daftar "hindari" yang kokoh (jebol support,
                 desil 1, insider jual, jatuh tajam 5 hari, Jatuh Dalam, ...).
                 Tiap keberatan berbobot veto / berat / ringan.
  Manajer Risiko stop = garis jebol support (support -3%), ukuran posisi dari
                 anggaran risiko 1% modal, dikoreksi Takaran Risiko.
  Pengamat Pasar kabar semalam (S&P 500, komoditas) -- lampu merah PAGI saja,
                 lihat riset_pola_naik/lintas_pasar.py. Tidak pernah lampu hijau.
  Hakim          AMBIL / PANTAU / TOLAK dengan aturan tetap (di bawah).
  Notulen        semua keputusan masuk rapat_agen_jurnal.csv; evaluasi H+1/5/20
                 membandingkan tiap keputusan dengan SEMUA kandidat (= aturan
                 murni tanpa rapat). Itu satu-satunya cara tahu apakah rapat
                 menambah nilai.

ATURAN HAKIM (versi 2, berlaku 9 Okt 2026 -- jurnal dimulai dengan versi ini)
  - ada veto                                              -> TOLAK
  - >= 2 keberatan berat                                  -> TOLAK
  - 1 keberatan berat                                     -> PANTAU
  - >= 1 argumen pendukung (bobot lemah), <= 1 keberatan
    ringan, stop <= 12%                                   -> AMBIL
  - selain itu                                            -> PANTAU
JUJURNYA: semua argumen pendukung di sini LEMAH (t<2, atau cuma kalibrasi
2026). Dekat/memantul support ~netral di luar sampel
(riset_pola_naik/chart_support.py), dan beli-rutin insider belum pernah diuji.
AMBIL di rapat ini berarti "lolos semua saringan hindari + ada alasan lemah",
BUKAN "terbukti condong naik" -- jurnal maju yang akan menjawabnya.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import csv
import glob
import logging
import os
import pickle
import time

import numpy as np
import pandas as pd

from .config import DAILY_PATH

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = str(_runtime_file('', 'rapat_agen_cache.pkl'))
JURNAL_FILE = str(_runtime_file('', 'rapat_agen_jurnal.csv'))
PASAR_FILE = str(_runtime_file('', 'rapat_agen_pasar.pkl'))
SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')

C = {
    'SUPPORT_DEKAT': 0.02,     # close 0..2% di atas support terdekat (= ember J1 di chart_support.py)
    'JEBOL': 0.97,             # close < support kemarin x 0,97 = jebol (chart_support.py)
    'JEBOL_HARI': 5,           # jebol dalam 5 hari terakhir dihitung
    'MIN_NILAI': 1e9,          # median nilai 20 hari, Rp
    'MIN_HARGA': 100.0,
    'MIN_AKTIF': 0.9,
    'RISIKO_MODAL': 0.01,      # anggaran risiko per posisi: 1% modal
    'PORSI_MAKS': 0.20,
    'STOP_MAKS': 0.12,         # stop lebih jauh dari ini -> tidak AMBIL
    'RINGAN_MAKS': 1,          # keberatan ringan maksimal untuk AMBIL
    'PASAR_TTL': 3600,
}

BOBOT = {'kuat': 2, 'lemah': 1, 'info': 0, 'veto': -99, 'berat': -2, 'ringan': -1}

# Bukti tiap argumen -- satu tempat, supaya halaman dan jurnal bicara sama.
BUKTI = {
    'desil10': ('lemah', 'Skor Kecondongan desil 10: +5,0%/60h di validasi, ~0 di 2013-2019 -- sisi naik lemah.'),
    'pantul_ma200': ('lemah', 'Memantul dari support chart + di atas MA200: positif lemah di 4 irisan '
                              '(+0,5..+1,1%/60h, t<2).'),
    'support': ('info', 'Dekat/tertahan di support chart: ~netral di luar sampel (chart_support.py). '
                        'Bahan pantauan, bukan alasan beli.'),
    'dicicil': ('info', 'Dicicil insider berminggu-minggu: BELUM pernah diuji. Insider BELI polos menang 49,5% '
                        'di H+40 -- koin lempar.'),
    'insider_kombo': ('lemah', 'Insider BELI dalam konteks Akumulasi Palsu: win 58,8% H+40 -- tapi kalibrasi '
                               '2026 saja, belum luar sampel.'),
    # keberatan
    'jebol': ('veto', 'Jebol support chart: −1,5..−2%/20h vs pasar, kokoh di 4 irisan (t sampai −5).'),
    'desil1': ('veto', 'Skor Kecondongan desil 1 (jauh dari puncak + liar): kalah dari pasar di 4 sel, '
                       '−2,6..−13,5%/60h, negatif 12 dari 14 tahun.'),
    'insider_jual': ('berat', 'Insider JUAL 20 hari terakhir: peluang masuk zona Jatuh Dalam ~+11pp '
                              '(setelah dedup, kontrol momentum, dan jeda tarik data nyata).'),
    'jatuh5': ('berat', 'Turun >15% dalam 5 hari: −3,0%/20h vs pasar (t −4,3) di validasi, '
                        'sudah negatif sejak H+3.'),
    'jatuh_dalam': ('berat', 'Jatuh >40% dari puncak 60h dan masih bergejolak: −3,3%/20h, −6,9%/60h (t −5,1). '
                             '"Jatuh Dalam" gagal di semesta luas.'),
    'tipis': ('berat', 'Likuiditas < Rp1 M/hari: di luar semesta semua uji; ongkos keluar-masuk bisa menelan selisihnya.'),
    'ruang_res': ('ringan', 'Ruang ke resistance >15%: di uji justru jebakan (−4,5..−5%/60h).'),
    'kejar_volume': ('ringan', 'Volume >3x di hari naik kuat: negatif jangka pendek di validasi (−0,7% H+3).'),
    'liar': ('ringan', 'Takaran Risiko "sangat liar": peluang guncangan −20% jauh di atas emiten biasa.'),
    'tanpa_support': ('berat', 'Di bawah semua level chart (tak ada support tersisa): negatif di uji.'),
}


def _num(v, d=2):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, d) if np.isfinite(v) else None


# ------------------------------------------------------------ harga & level
def _levels(df):
    from .utilities import compute_levels
    return np.array(compute_levels(df.tail(100).reset_index(drop=True)) or [], float)


def _support_info(df):
    """Support/resistance terdekat hari ini + apakah jebol dalam JEBOL_HARI hari."""
    if df is None or len(df) < 105:
        return None
    close = float(df['Close'].iloc[-1])
    lv = _levels(df)
    sup = lv[lv <= close]
    res = lv[lv >= close]
    jebol = None
    for k in range(1, C['JEBOL_HARI'] + 1):
        kemarin = _levels(df.iloc[:-k])
        c_k = float(df['Close'].iloc[-k])
        s_prev = kemarin[kemarin <= float(df['Close'].iloc[-k - 1])]
        if len(s_prev) and c_k < s_prev[-1] * C['JEBOL']:
            jebol = {'hari_lalu': k - 1, 'support': float(s_prev[-1]), 'close': c_k}
            break
    return {'close': close, 'n_level': len(lv),
            'support': float(sup[-1]) if len(sup) else None,
            'resistance': float(res[0]) if len(res) else None,
            'jarak_sup': close / sup[-1] - 1 if len(sup) else None,
            'jarak_res': res[0] / close - 1 if len(res) else None,
            'jebol': jebol,
            'sentuh5': bool(len(sup) and df['Low'].tail(5).min() <= sup[-1] * 1.01)}


def _konteks(f):
    """Ukuran harga dari panel sambungan (Summary + Yahoo) tembus_basis._panel()."""
    c = f['close']
    out = {'close': float(c.iloc[-1]), 'nilai20': _num(f['nilai20'].iloc[-1], 0),
           'aktif30': _num(f['aktif30'].iloc[-1], 2), 'layak': bool(f['layak'].iloc[-1]),
           'dari_puncak': _num(f['dari_puncak'].iloc[-1], 4)}
    out['ma200'] = bool(len(c) >= 200 and c.iloc[-1] > c.tail(200).mean()) if len(c) >= 200 else None
    out['ret5'] = _num(c.iloc[-1] / c.iloc[-6] - 1, 4) if len(c) > 6 else None
    if len(c) >= 60:
        out['dd60'] = _num(c.iloc[-1] / c.tail(60).max() - 1, 4)
        w = c.tail(20)
        out['range20'] = _num((w.max() - w.min()) / c.iloc[-1], 4)
    else:
        out['dd60'] = out['range20'] = None
    out['vol_x'] = _num(f['vol_x'].iloc[-1], 2)
    out['naik'] = _num(f['naik'].iloc[-1], 4)
    out['posisi'] = _num(f['posisi'].iloc[-1], 2)
    return out


# ------------------------------------------------------------ pengamat pasar
KEMBAR_KOMODITAS = {
    'ADRO': 'BZ=F', 'PTBA': 'BZ=F', 'ITMG': 'BZ=F', 'BUMI': 'BZ=F', 'AADI': 'BZ=F', 'HRUM': 'BZ=F', 'INDY': 'BZ=F',
    'ANTM': 'GC=F', 'MDKA': 'GC=F', 'BRMS': 'GC=F', 'PSAB': 'GC=F', 'ARCI': 'GC=F',
    'INCO': 'HG=F', 'NCKL': 'HG=F', 'MBMA': 'HG=F',
    'MEDC': 'BZ=F', 'ELSA': 'BZ=F', 'AKRA': 'BZ=F', 'ENRG': 'BZ=F',
    'AALI': 'BZ=F', 'LSIP': 'BZ=F', 'SIMP': 'BZ=F', 'TAPG': 'BZ=F', 'DSNG': 'BZ=F',
}
# Batubara Rotterdam (MTF=F) berhenti di Yahoo Des 2025 -> emiten batubara
# memakai Brent, yang di uji lintas_pasar juga searah (ADRO/PTBA/ITMG oc 0,04-0,12).
NAMA_PASAR = {'^GSPC': 'S&P 500', 'BZ=F': 'Minyak Brent', 'GC=F': 'Emas', 'HG=F': 'Tembaga'}


def _ambang_q1():
    """Batas kuintil terbawah return semalam, 2020-2026, dari cache riset lintas_pasar."""
    ambang = {'^GSPC': -0.006, 'BZ=F': -0.015, 'GC=F': -0.007, 'HG=F': -0.011}
    try:
        from .riset_pola_naik import lintas_pasar as L
        with open(L.GLOBAL_FILE, 'rb') as fh:
            g = pickle.load(fh)['data']
        for k in ambang:
            s = np.log(g[k]['Close'].dropna())
            r = s.diff().loc['2020-01-01':].dropna()
            ambang[k] = float(r.quantile(0.2))
    except Exception:
        logger.info('Ambang pasar memakai nilai bawaan (cache lintas_pasar tidak terbaca)')
    return ambang


def pengamat_pasar(force=False):
    """Kabar semalam: return sesi luar negeri yang sudah final sejak close IDX terakhir."""
    if not force and os.path.exists(PASAR_FILE):
        try:
            with open(PASAR_FILE, 'rb') as fh:
                s = pickle.load(fh)
            if time.time() - s['ts'] < C['PASAR_TTL']:
                return s['hasil']
        except Exception:
            pass
    try:
        import yfinance as yf
        d = yf.download(list(NAMA_PASAR), period='15d', auto_adjust=False, progress=False, group_by='ticker')
        ambang = _ambang_q1()
        # close IDX terakhir: tanggal terbaru di Summary BBCA (pasti selalu ada)
        from .tembus_basis import _baca_summary
        bb = _baca_summary(os.path.join(SUMMARY_DIR, 'BBCA_Summary.csv'))
        idx_terakhir = bb.index[-1]
        # Sesi bertanggal D baru final setelah settlement/close sore ET (~17:00 ET).
        # Sebelum itu bar Yahoo tanggal D masih bergerak -- dibuang.
        kini_et = pd.Timestamp.now(tz='America/New_York')
        final = pd.Timestamp(kini_et.date()) - pd.Timedelta(days=0 if kini_et.hour >= 17 else 1)
        hasil = {'available': True, 'idx_terakhir': idx_terakhir.strftime('%Y-%m-%d'),
                 'final_sampai': final.strftime('%Y-%m-%d'), 'seri': {}}
        for k, nama in NAMA_PASAR.items():
            c = d[k]['Close'].dropna()
            c = c[~c.index.duplicated(keep='last')]
            c = c[c.index <= final]      # bar sesi yang masih berjalan BUKAN kabar final
            baru = c[c.index >= idx_terakhir]
            lama = c[c.index < idx_terakhir]
            if not len(baru) or not len(lama):
                hasil['seri'][k] = {'nama': nama, 'ret': None, 'merah': False, 'sesi': None}
                continue
            r = float(np.log(baru.iloc[-1] / lama.iloc[-1]))
            hasil['seri'][k] = {'nama': nama, 'ret': round(r * 100, 2), 'ambang': round(ambang[k] * 100, 2),
                                'merah': r <= ambang[k], 'sesi': baru.index[-1].strftime('%Y-%m-%d')}
        hasil['dibangun'] = time.strftime('%Y-%m-%d %H:%M')
    except Exception as exc:
        logger.exception('Pengamat pasar gagal')
        hasil = {'available': False, 'message': 'Kabar semalam tidak terbaca: %s' % exc}
    try:
        with open(PASAR_FILE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'hasil': hasil}, fh)
    except Exception:
        pass
    return hasil


def _lampu_pasar(stock, likuid_tebal, pasar):
    """Lampu merah PAGI untuk satu saham -- tidak pernah lampu hijau."""
    if not pasar or not pasar.get('available'):
        return []
    out = []
    spx = pasar['seri'].get('^GSPC') or {}
    if spx.get('merah') and not likuid_tebal:
        out.append('S&P 500 jatuh %.2f%% semalam (20%% malam terburuk): saham lapis 2-3 rata-rata masih turun '
                   '0,3-0,5%% dari open ke close -- tunda beli pagi.' % spx['ret'])
    k = KEMBAR_KOMODITAS.get(stock)
    if k:
        s = pasar['seri'].get(k) or {}
        if s.get('merah'):
            out.append('%s jatuh %.2f%% semalam: saham komoditasnya lanjut turun open->close (−0,3..−0,4%%, '
                       'negatif 13 dari 14 tahun) -- jangan beli pagi; kalau pegang, jual di open.' % (s['nama'], s['ret']))
    return out


# ------------------------------------------------------------ rapat
def _rapat_satu(stock, sumber, f, sup, konteks, ins, desil, insider, risiko_row):
    pro, kontra = [], []

    def tambah(lst, kunci, teks=None):
        bobot, dasar = BUKTI[kunci]
        lst.append({'kunci': kunci, 'bobot': bobot, 'teks': teks or dasar, 'bukti': dasar})

    # --- Analis
    if 'support' in sumber and sup and sup['jarak_sup'] is not None:
        tambah(pro, 'support', 'Close %s, %.1f%% di atas support chart %s.'
               % (_fmt(sup['close']), sup['jarak_sup'] * 100, _fmt(sup['support'])))
        if sup['sentuh5'] and konteks.get('ma200'):
            tambah(pro, 'pantul_ma200', 'Menyentuh support dalam 5 hari dan masih di atas MA200.')
    if 'dicicil' in sumber and ins:
        tambah(pro, 'dicicil', 'Dicicil %d minggu (%d hari beli, %d hari jual), net posisi +%s%% oleh %s.'
               % (ins['minggu_beli'], ins['hari_beli'], ins['hari_jual'], _fmt(ins['net_pct'], 2),
                  ', '.join(p['nama'] for p in ins['pembeli'][:2])))
    if desil == 10:
        tambah(pro, 'desil10')
    if insider.get('kombo'):
        tambah(pro, 'insider_kombo', 'Insider BELI dikonfirmasi konteks: %s.' % ', '.join(insider['kombo']))

    # --- Pembantah
    if sup and sup['jebol']:
        j = sup['jebol']
        tambah(kontra, 'jebol', 'Jebol support %s (close %s, %s).'
               % (_fmt(j['support']), _fmt(j['close']), 'hari ini' if j['hari_lalu'] == 0 else '%d hari lalu' % j['hari_lalu']))
    if sup and sup['support'] is None and sup['n_level'] > 0:
        tambah(kontra, 'tanpa_support')
    if desil == 1:
        tambah(kontra, 'desil1')
    if insider.get('jual'):
        tambah(kontra, 'insider_jual', 'Insider JUAL dalam 20 hari terakhir (%s).' % insider['jual'])
    if konteks.get('ret5') is not None and konteks['ret5'] <= -0.15:
        tambah(kontra, 'jatuh5', 'Turun %.1f%% dalam 5 hari.' % (konteks['ret5'] * 100))
    if (konteks.get('dd60') is not None and konteks['dd60'] <= -0.40
            and (konteks.get('range20') or 0) >= 0.25):
        tambah(kontra, 'jatuh_dalam', '%.0f%% dari puncak 60 hari, rentang 20 hari %.0f%%.'
               % (konteks['dd60'] * 100, konteks['range20'] * 100))
    if (konteks.get('nilai20') or 0) < C['MIN_NILAI']:
        tambah(kontra, 'tipis', 'Median nilai 20 hari Rp%s M.' % _fmt((konteks.get('nilai20') or 0) / 1e9, 2))
    if sup and sup['jarak_res'] is not None and sup['jarak_res'] > 0.15:
        tambah(kontra, 'ruang_res', 'Resistance terdekat %.0f%% di atas.' % (sup['jarak_res'] * 100))
    if (konteks.get('vol_x') or 0) > 3 and (konteks.get('naik') or 0) > 0.03 and (konteks.get('posisi') or 0) > 0.7:
        tambah(kontra, 'kejar_volume', 'Hari ini naik %.1f%% dengan volume %.1fx.'
               % (konteks['naik'] * 100, konteks['vol_x']))
    if risiko_row and risiko_row.get('label') == 'sangat liar':
        tambah(kontra, 'liar', 'Takaran Risiko: sangat liar (x%s risiko guncangan −20%%).' % _fmt(risiko_row.get('x_rugi'), 2))

    # --- Manajer Risiko
    risk = {'label': (risiko_row or {}).get('label'), 'x_rugi': (risiko_row or {}).get('x_rugi')}
    close = konteks['close']
    stop = sup['support'] * C['JEBOL'] if sup and sup['support'] else None
    jarak = close / stop - 1 if stop else None
    if jarak is None or jarak > 0.10 / 0.90:
        # support tak ada / terlalu jauh di bawah -> stop TS10 (-10% dari harga beli)
        stop, jarak = close * 0.90, 0.10 / 0.90
        risk['dasar_stop'] = 'TS10 (support tak ada / >10% di bawah)'
    else:
        risk['dasar_stop'] = 'jebol support (support x 0,97)'
    risk['stop'] = _num(stop, 0)
    risk['jarak_stop'] = _num(jarak * 100 if jarak else None, 1)
    porsi = None
    if jarak and jarak > 0:
        porsi = min(C['RISIKO_MODAL'] / (jarak / (1 + jarak)), C['PORSI_MAKS'])
        faktor = {'sangat liar': 0.5, 'liar': 0.75}.get(risk['label'], 1.0)
        porsi *= faktor
    risk['porsi'] = _num(porsi * 100 if porsi else None, 1)
    risk['keluar'] = 'Trailing 10% dari close tertinggi sejak beli (TS10) -- aturan keluar terbaik yang pernah diuji.'
    if sup and sup.get('resistance'):
        risk['resistance'] = _num(sup['resistance'], 0)

    # --- Hakim
    n_veto = sum(1 for k in kontra if k['bobot'] == 'veto')
    n_berat = sum(1 for k in kontra if k['bobot'] == 'berat')
    n_ringan = sum(1 for k in kontra if k['bobot'] == 'ringan')
    dukung = [p for p in pro if p['bobot'] in ('kuat', 'lemah')]
    skor = sum(BOBOT[p['bobot']] for p in pro) + sum(BOBOT[k['bobot']] for k in kontra if k['bobot'] != 'veto')
    if n_veto:
        keputusan, alasan = 'TOLAK', 'Ada veto: %s.' % '; '.join(k['kunci'] for k in kontra if k['bobot'] == 'veto')
    elif n_berat >= 2:
        keputusan, alasan = 'TOLAK', '%d keberatan berat.' % n_berat
    elif n_berat == 1:
        keputusan, alasan = 'PANTAU', 'Satu keberatan berat (%s) -- tunggu sampai hilang.' % next(
            k['kunci'] for k in kontra if k['bobot'] == 'berat')
    elif dukung and n_ringan <= C['RINGAN_MAKS'] and jarak is not None and jarak <= C['STOP_MAKS']:
        keputusan, alasan = 'AMBIL', 'Lolos semua saringan hindari, didukung %s, stop %.1f%% (bukti pendukung lemah).' % (
            ', '.join(p['kunci'] for p in dukung), jarak * 100)
    elif dukung and n_ringan > C['RINGAN_MAKS']:
        keputusan, alasan = 'PANTAU', '%d keberatan ringan -- terlalu banyak catatan untuk diambil.' % n_ringan
    elif dukung:
        keputusan, alasan = 'PANTAU', 'Ada pendukung, tapi stop %.1f%% terlalu jauh.' % ((jarak or 0) * 100)
    else:
        keputusan, alasan = 'PANTAU', ('Tak ada keberatan berat, tapi juga tak ada argumen pendukung -- '
                                        'dekat support / dicicil insider sendirian belum terbukti.')
    if keputusan == 'TOLAK':
        risk['porsi'] = None

    return {'stock': stock, 'sumber': sorted(sumber), 'keputusan': keputusan, 'alasan': alasan,
            'skor': skor, 'close': _num(close, 0), 'pro': pro, 'kontra': kontra, 'risiko': risk,
            'jarak_sup': _num(sup['jarak_sup'] * 100 if sup and sup['jarak_sup'] is not None else None, 1),
            'support': _num(sup['support'], 0) if sup and sup['support'] else None,
            'desil': desil, 'dari_puncak': _num((konteks.get('dari_puncak') or np.nan) * 100, 1),
            'nilai_m': _num((konteks.get('nilai20') or 0) / 1e9, 2)}


def _fmt(v, d=0):
    try:
        return ('{:,.%df}' % d).format(float(v)).replace(',', '_').replace('.', ',').replace('_', '.')
    except (TypeError, ValueError):
        return '—'


def _bangun():
    from .tembus_basis import _panel, _baca_summary
    from .dicicil_insider import scan as di_scan
    from .kecondongan import scan as kc_scan
    from .insider_signal import scan as is_scan
    from . import risiko

    t0 = time.time()
    panel = _panel()
    if not panel or not panel['fit']:
        return {'available': False, 'message': 'Tidak ada berkas Summary yang bisa dibaca.'}
    fit = panel['fit']
    hari_pasar = max(f.index[-1] for f in fit.values())

    def _aman(fn, nama):
        try:
            return fn()
        except Exception:
            logger.exception('Rapat Agen: %s gagal' % nama)
            return {}

    di = _aman(di_scan, 'dicicil_insider')
    kc = _aman(kc_scan, 'kecondongan')
    isg = _aman(is_scan, 'insider_signal')

    desil = {r['stock']: r['desil'] for r in kc.get('semua') or []}
    jual = {r['ticker']: r for r in isg.get('jual_peringatan') or []}
    beli_kombo = {r['ticker']: r.get('alasan') or [] for r in isg.get('beli') or []}
    dicicil = {r['ticker']: r for r in di.get('rows') or []}

    # --- Pengumpul: (a) dekat support, emiten likuid segar
    kandidat = {}
    n_cek = 0
    for s, f in fit.items():
        if f.index[-1] != hari_pasar:
            continue
        last = f.iloc[-1]
        if not (last['close'] >= C['MIN_HARGA'] and (last['nilai20'] or 0) >= C['MIN_NILAI']
                and (last['aktif30'] or 0) >= C['MIN_AKTIF']):
            continue
        df = _baca_summary(os.path.join(SUMMARY_DIR, '%s_Summary.csv' % s))
        if df is None:
            continue
        n_cek += 1
        sup = _support_info(df)
        if sup and sup['jarak_sup'] is not None and 0 <= sup['jarak_sup'] <= C['SUPPORT_DEKAT']:
            kandidat[s] = {'sumber': {'support'}, 'sup': sup}
    # (b) dicicil insider -- semua likuiditas; yang tipis akan dibantah
    for s in dicicil:
        if s in kandidat:
            kandidat[s]['sumber'].add('dicicil')
        else:
            df = _baca_summary(os.path.join(SUMMARY_DIR, '%s_Summary.csv' % s))
            kandidat[s] = {'sumber': {'dicicil'}, 'sup': _support_info(df) if df is not None else None}

    rows = []
    for s, k in kandidat.items():
        f = fit.get(s)
        if f is None:
            continue
        konteks = _konteks(f)
        ins = {}
        if s in jual:
            ins['jual'] = ', '.join(sorted({i['name'] for i in jual[s].get('insiders') or []})[:2]) or 'ada'
        kombo = [a for a in beli_kombo.get(s, []) if a == 'akumulasi_palsu']
        if kombo:
            ins['kombo'] = ['Akumulasi Palsu']
        try:
            rr = risiko.untuk_ticker(s)
        except Exception:
            rr = None
        rows.append(_rapat_satu(s, k['sumber'], f, k['sup'], konteks, dicicil.get(s),
                                desil.get(s), ins, rr))

    urut = {'AMBIL': 0, 'PANTAU': 1, 'TOLAK': 2}
    rows.sort(key=lambda r: (urut[r['keputusan']], -r['skor'], r['stock']))
    tanggal = hari_pasar.strftime('%Y-%m-%d')
    try:
        dicatat = catat(rows, tanggal)
    except Exception as exc:
        logger.exception('Gagal mencatat jurnal Rapat Agen')
        dicatat = {'tercatat': 0, 'pesan': 'gagal: %s' % exc}
    try:
        jurnal = evaluasi(fit)
    except Exception as exc:
        logger.exception('Gagal mengevaluasi jurnal Rapat Agen')
        jurnal = {'available': False, 'message': 'Gagal mengevaluasi: %s' % exc}

    return {
        'available': True, 'as_of': tanggal,
        'n_dicek_support': n_cek, 'n_dicicil': len(dicicil),
        'n': {k: sum(1 for r in rows if r['keputusan'] == k) for k in urut},
        'rows': rows, 'catat': dicatat, 'jurnal': jurnal,
        'config': C, 'bukti': {k: {'bobot': v[0], 'teks': v[1]} for k, v in BUKTI.items()},
        'durasi': round(time.time() - t0, 1),
        'dibangun': time.strftime('%Y-%m-%d %H:%M'), 'from_cache': False,
    }


# ------------------------------------------------------------ notulen
KOLOM = ['tanggal', 'stock', 'sumber', 'keputusan', 'skor', 'close', 'jarak_stop', 'pro', 'kontra']


def catat(rows, tanggal):
    ada = set()
    if os.path.exists(JURNAL_FILE):
        with open(JURNAL_FILE, newline='', encoding='utf-8') as fh:
            ada = {(r['tanggal'], r['stock']) for r in csv.DictReader(fh)}
    baru = [r for r in rows if (tanggal, r['stock']) not in ada]
    if baru:
        tulis_kepala = not os.path.exists(JURNAL_FILE)
        with open(JURNAL_FILE, 'a', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            if tulis_kepala:
                w.writerow(KOLOM)
            for r in baru:
                w.writerow([tanggal, r['stock'], '+'.join(r['sumber']), r['keputusan'], r['skor'], r['close'],
                            r['risiko'].get('jarak_stop'), '|'.join(p['kunci'] for p in r['pro']),
                            '|'.join(k['kunci'] for k in r['kontra'])])
    return {'tanggal': tanggal, 'tercatat': len(baru), 'sudah_ada': len(rows) - len(baru)}


def evaluasi(fit, horizons=(1, 5, 20)):
    """Return majemuk tiap keputusan vs SEMUA kandidat hari yang sama (= aturan murni tanpa rapat).
    Masuk di close hari rapat; satu baris per emiten per tanggal."""
    if not os.path.exists(JURNAL_FILE):
        return {'available': False, 'message': 'Jurnal belum ada.'}
    j = pd.read_csv(JURNAL_FILE)
    if j.empty:
        return {'available': False, 'message': 'Jurnal kosong.'}
    j['tanggal'] = pd.to_datetime(j['tanggal'])
    out = {'available': True, 'mulai': j['tanggal'].min().strftime('%Y-%m-%d'),
           'n_hari': int(j['tanggal'].nunique()), 'n_baris': len(j), 'horizon': []}
    for h in horizons:
        rets = []
        for _, r in j.iterrows():
            f = fit.get(r['stock'])
            if f is None or r['tanggal'] not in f.index:
                rets.append(np.nan)
                continue
            i = f.index.get_loc(r['tanggal'])
            rets.append(np.log(f['close'].iloc[i + h] / f['close'].iloc[i]) if i + h < len(f) else np.nan)
        j['r'] = rets
        m = j.dropna(subset=['r'])
        baris = {'horizon': h, 'n_matang': len(m), 'kelompok': []}
        if len(m):
            for kel in ('semua kandidat', 'AMBIL', 'PANTAU', 'TOLAK'):
                g = m if kel == 'semua kandidat' else m[m['keputusan'] == kel]
                baris['kelompok'].append({
                    'nama': kel, 'n': len(g),
                    'majemuk': _num((np.exp(g['r'].mean()) - 1) * 100, 2) if len(g) else None,
                    'win': _num((g['r'] > 0).mean() * 100, 1) if len(g) else None})
        out['horizon'].append(baris)
    out['cukup'] = any(b['n_matang'] >= 100 for b in out['horizon'])
    return out


# ------------------------------------------------------------ pintu masuk
def _sumber_terbaru():
    from .tembus_basis import _sumber_terbaru as tb_sumber
    return tb_sumber()


def scan(force=False):
    hasil = None
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                simpan = pickle.load(fh)
            if simpan.get('ts', 0) >= _sumber_terbaru():
                hasil = dict(simpan['result'])
                hasil['from_cache'] = True
        except Exception:
            hasil = None
    if hasil is None:
        hasil = _bangun()
        if hasil.get('available'):
            try:
                with open(CACHE_FILE, 'wb') as fh:
                    pickle.dump({'ts': time.time(), 'result': hasil}, fh)
            except Exception:
                logger.exception('Gagal menyimpan cache Rapat Agen')
    if not hasil.get('available'):
        return hasil
    # Pengamat Pasar dipasang tiap permintaan: kabar semalam berubah jam 04:00 WIB,
    # sedangkan cache rapat cuma berubah saat Summary baru masuk.
    pasar = pengamat_pasar(force=force)
    hasil['pasar'] = pasar
    for r in hasil['rows']:
        r['lampu_pagi'] = _lampu_pasar(r['stock'], (r.get('nilai_m') or 0) >= 20, pasar)
    return hasil


def cek():
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    h = scan(force=True)
    if not h.get('available'):
        print(h.get('message'))
        return
    print('%s | dicek support %d, dicicil %d | %s | %.1fs'
          % (h['as_of'], h['n_dicek_support'], h['n_dicicil'], h['n'], h['durasi']))
    p = h.get('pasar') or {}
    for k, s in (p.get('seri') or {}).items():
        print('  pasar %-14s %s%%  ambang %s  merah=%s' % (s['nama'], s.get('ret'), s.get('ambang'), s.get('merah')))
    for r in h['rows']:
        print('%-6s %-7s %-16s skor %3d stop %5s%% porsi %5s%% | %s'
              % (r['stock'], r['keputusan'], '+'.join(r['sumber']), r['skor'],
                 r['risiko'].get('jarak_stop'), r['risiko'].get('porsi'), r['alasan']))
        for k in r['kontra']:
            print('        - [%s] %s' % (k['bobot'], k['teks']))
        for l in r['lampu_pagi']:
            print('        ! %s' % l)


if __name__ == '__main__':
    cek()
