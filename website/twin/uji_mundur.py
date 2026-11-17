"""
Uji mundur twin: apakah twin MENEBAK reaksi harga terhadap event nyata
lebih baik daripada patokan naif? (9 Okt 2026)

Twin dibuat untuk "bagaimana jika", bukan ramalan. Pertanyaan di sini:
kalau event yang benar-benar terjadi dimasukkan ke twin, apakah selisih
dunia-skenario vs dunia-baseline-nya menebak reaksi harga ASLI lebih baik
daripada aturan sederhana? Kalau tidak, twin tidak boleh dipakai untuk
"prediksi otomatis" event mendatang.

EVENT YANG DIUJI
  1. Dividen (ex-date Yahoo, imbal hasil = dividen / close mentah sehari
     sebelum ex). Jendela: pra10 (10 hari bursa menjelang ex), ex (hari ex),
     ex2 (hari ex + sehari sesudahnya; menampung ARB 7% era 2020-2023),
     pasca10 (10 hari sesudahnya). Harga mentah (sudah disesuaikan split,
     BELUM dividen), return abnormal = return - beta x IHSG.
  2. Keputusan BI rate (tabel RDG bi.go.id, research_cache/bi_rate_riwayat.csv,
     Apr 2016 - Sep 2026: 127 keputusan, 38 perubahan). Jendela dari close
     sehari sebelum RDG: d01 (s/d sehari sesudah, pengumuman ~14:00 WIB saat
     bursa masih buka), d05, d20. Level IHSG dan lintas saham (return
     abnormal per saham, harga Yahoo disesuaikan dividen).

TWIN
  Profil saham = kondisi SEKARANG (begitulah twin dipakai untuk event
  mendatang) -- untuk event lama ini ketidakcocokan yang diakui. Tiap saham
  disimulasikan di kelompok 8 saham (konfigurasi yang divalidasi), 2000 agen,
  8 seed. Dividen: grid imbal hasil x saham, lalu diinterpolasi ke imbal hasil
  tiap event; cum 10 hari (tanggal pengumuman asli tidak ada di data).
  BI rate: -50/-25/+25/+50 bp, preset suku_bunga apa adanya (durasi 20).

PROTOKOL (aturan project: pisah periode DAN semesta)
  Kalibrasi = semesta A (16 saham yang dipakai membangun twin) x sebelum 2022.
  Uji       = semesta B (8 saham yang tak pernah dipakai menyetel + 16 saham
              pembayar dividen yang belum pernah disentuh twin) x 2022 dst.
  Model yang dibandingkan per jendela:
    nol           tebakan 0 (tidak ada reaksi di luar beta x IHSG)
    mekanis       ex/ex2 = log(1 - imbal hasil), lainnya 0         (dividen)
    historis      OLS dari data kalibrasi: a + b x imbal hasil / bp / sektor
    twin          selisih twin apa adanya (konstanta asumsi skenario.py)
    twin_kal      a + b x twin, dikalibrasi ulang di sel kalibrasi
    historis+twin historis ditambah twin -- apakah twin MENAMBAH info?
  R2 luar sampel = 1 - SSE model / SSE pembanding.

HASIL (9 Okt 2026; 2.440 dunia twin, 40 saham, 8 seed)
=======================================================
Data: 633 ex-date dividen (kalibrasi A x P1 143, UJI B x P2 163), 127
keputusan RDG (38 perubahan; P2 17 perubahan x 24 saham B = 408 baris).
Angka = R2 luar sampel vs tebakan 0, sel UJI kecuali disebut lain.

1. DIVIDEN -- twin tidak lebih baik dari aritmetika / rata-rata historis.
   ex2 (2 hari ex)  mekanis (-dividen) +0,740 | historis +0,627 | twin +0,726
                    | twin_kal +0,574. Twin ~ aritmetika (CI90 twin vs mekanis
                    -0,16..+0,03). Historis kalah karena rasio turun/dividen
                    BERGESER: 0,76-0,80 (2013-21) -> 0,85-0,87 (2022+).
   ex (hari ex)     historis +0,737 terbaik; twin +0,627; twin_kal +0,708
                    (CI90 vs historis -0,28..-0,00). Twin turun 1,12-1,29x
                    dividen (run-up cum dikembalikan di hari ex); aslinya
                    0,57-0,63x (2013-21) dan 0,76-0,78x (2022+).
   pra10 (run-up)   aktual rata-rata +0,7..+1,5% di semua sel, tapi semua
                    model < 5%: twin +0,030, twin_kal +0,046, historis -0,083
                    (garis lurus kebablasan di dividen jumbo), historis
                    dibatasi 10% -0,024. Bentuk kurva twin = konstanta asumsi
                    skenario.py; bagian KHAS-SAHAM twin (hasil dinamika agen)
                    cuma r +0,00..+0,12 per event, ~+0,3 per saham -- sd-nya
                    0,23%, di bawah biaya transaksi.
   pasca10          tidak ada yang menebak (twin +0,004).
   Bagian khas-saham twin di ex2 malah TERBALIK di keempat sel (r -0,06..
   -0,40; per saham -0,53..-0,57): saham yang menurut twin turun paling dalam (CTRA,
   RAJA, SCMA) aslinya turun lebih dangkal, dan sebaliknya (PTBA, ITMG, DMAS).
2. BI RATE -- arah asumsi twin salah; tidak ada yang mengalahkan tebakan 0.
   IHSG d01: twin +25 bp = -0,70%; aslinya sesudah KENAIKAN +0,59% (2016-21)
   dan +0,90% (2022+), sesudah penurunan -0,15% dan +1,19%. Twin di bawah
   nol di semua sel (perubahan saja: -0,75 P1, -0,12 P2; d05/d20 -0,04..
   -0,16). Garis historis P1 juga gagal di P2 (d01 -0,01, d20 -0,25):
   reaksi pasar ditentukan KEJUTAN terhadap konsensus, yang tidak ada di data.
   Lintas saham (siapa bereaksi lebih kuat): IC twin -0,001 (d01), -0,065
   (d05), +0,018 (d20), positif di 8/17 event; twin mentah -0,27, twin_kal ~0.
Kesimpulan: twin TIDAK layak dipakai untuk "prediksi otomatis" event. Di
dividen ia menyamai aritmetika paling banter; di BI rate arahnya terbalik.
Bagian yang benar-benar hasil dinamika agen (beda antar saham) tidak membantu
-- di hari ex malah terbalik. Twin tetap alat bagaimana-jika.

PEMAKAIAN (dari <project>/)
    python -m website.twin.uji_mundur              # simulasi (bisa dilanjut) + evaluasi
    python -m website.twin.uji_mundur --evaluasi   # evaluasi dari cache simulasi saja
"""
import argparse
import json
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

from . import jalan, kalibrasi, skenario
from .simulasi import Dunia

RC = kalibrasi.RESEARCH_CACHE
KELOMPOK = {
    'A1': ['BBCA', 'BBRI', 'TLKM', 'ASII', 'ANTM', 'BUMI', 'DEWA', 'RAJA'],
    'A2': ['BMRI', 'BBNI', 'ICBP', 'UNVR', 'ADRO', 'MDKA', 'HRUM', 'ERAA'],
    'B1': ['BRIS', 'UNTR', 'CPIN', 'PGAS', 'MEDC', 'CTRA', 'ACES', 'ESSA'],
    'B2': ['ITMG', 'PTBA', 'AKRA', 'AALI', 'TOWR', 'BFIN', 'KLBF', 'INDF'],
    'B3': ['AUTO', 'MYOR', 'SMGR', 'JPFA', 'SCMA', 'DMAS', 'AMRT', 'MARK'],
}
BATAS_PERIODE = pd.Timestamp('2022-01-01')
GRID_Y = (0.01, 0.02, 0.04, 0.07, 0.11, 0.16, 0.22)
GRID_BP = (-50, -25, 25, 50)
SEEDS = tuple(range(101, 109))
HARI = 35          # hari rekam twin
H0 = 10            # hari event di twin (pengumuman dividen / RDG)
CUM = 10           # panjang periode cum dividen di twin (ex = H0 + CUM)
Y_MAKS = 0.30      # imbal hasil di atasnya = dividen khusus/spin-off, dibuang

# jendela (awal, akhir) relatif ke hari event E: return dari close[E+awal] ke close[E+akhir]
JENDELA_DIV = {'pra10': (-11, -1), 'ex': (-1, 0), 'ex2': (-1, 1), 'pasca10': (1, 11)}
JENDELA_BI = {'d01': (-1, 1), 'd05': (-1, 5), 'd20': (-1, 20)}


def _semesta(k):
    return 'A' if k in KELOMPOK['A1'] + KELOMPOK['A2'] else 'B'


def _periode(t):
    return 'P1' if t < BATAS_PERIODE else 'P2'


# ======================================================== data pasar asli
def muat_pasar():
    mentah = kalibrasi._harga_mentah()
    yahoo = kalibrasi._harga_yahoo()
    ih_lama = pickle.load(open(os.path.join(RC, 'ihsg_2012-01-01_2026-09-09.pkl'), 'rb'))
    ih_baru, _ = kalibrasi.ihsg()
    ih = pd.concat([ih_lama[ih_lama.index < ih_baru.index[0]], ih_baru]).astype(float)
    ih = ih[~ih.index.duplicated(keep='last')].sort_index()
    return mentah, yahoo, ih


def _bersih(s):
    s = s[~s.index.duplicated(keep='last')].astype(float)
    return s[s > 0].dropna().sort_index()


def _beta(ya, ih, sampai, n=250):
    """Beta harian (Yahoo disesuaikan) terhadap IHSG, 250 hari bursa sampai
    tanggal `sampai` (eksklusif)."""
    if ya is None:
        return 1.0
    r = np.log(ya[ya.index < sampai]).diff().dropna().tail(n)
    m = np.log(ih).diff().reindex(r.index)
    ok = m.notna() & np.isfinite(r)
    if ok.sum() < 120 or m[ok].var() <= 0:
        return 1.0
    return float(np.clip(np.cov(r[ok], m[ok])[0, 1] / m[ok].var(), -0.5, 3.0))


def _ret_ih(ih, t_awal, t_akhir):
    a, b = ih.asof(t_awal), ih.asof(t_akhir)
    return float(np.log(b / a)) if np.isfinite(a) and np.isfinite(b) and a > 0 else np.nan


def event_dividen(mentah, yahoo, ih):
    aksi = pickle.load(open(os.path.join(RC, 'aksi_korporasi.pkl'), 'rb'))['aksi']
    rows = []
    for k in sum(KELOMPOK.values(), []):
        a = aksi.get(k)            # dict atau DataFrame (kolom Dividends / Stock Splits)
        if a is None or 'Dividends' not in a or k not in mentah:
            continue
        c = _bersih(mentah[k])
        ya = _bersih(yahoo[k]['Close']) if k in yahoo else None
        dv = a['Dividends'].dropna()
        dv = dv[dv > 0].copy()
        dv.index = pd.to_datetime(dv.index).normalize()
        dv = dv.groupby(level=0).sum()                     # dua baris di ex-date yang sama
        sp = a.get('Stock Splits')
        split = [] if sp is None else list(pd.to_datetime(sp[sp > 0].index).normalize())
        for t, v in dv.items():
            if t < pd.Timestamp('2013-01-01'):
                continue
            E = int(c.index.searchsorted(t))
            if E < 12 or E + 1 >= len(c) or (c.index[E] - t).days > 5:
                continue
            if any(abs((s - t).days) <= 25 for s in split):
                continue
            y = float(v / c.iloc[E - 1])
            if not 0.001 <= y <= Y_MAKS:
                continue
            beta = _beta(ya, ih, c.index[E - 11])
            r = {'kode': k, 'tanggal': c.index[E], 'imbal': y, 'beta': beta,
                 'semesta': _semesta(k), 'periode': _periode(c.index[E])}
            for w, (a0, a1) in JENDELA_DIV.items():
                if E + a1 >= len(c):
                    r[w] = np.nan
                    continue
                ta, tb = c.index[E + a0], c.index[E + a1]
                r[w] = float(np.log(c.iloc[E + a1] / c.iloc[E + a0])) - beta * _ret_ih(ih, ta, tb)
            rows.append(r)
    return pd.DataFrame(rows)


def event_bi(yahoo, ih):
    bi = pd.read_csv(os.path.join(RC, 'bi_rate_riwayat.csv'), comment='#', parse_dates=['tanggal'])
    bi = bi.dropna(subset=['ubah_bp'])
    pasar, saham = [], []
    tgl_ih = ih.index
    harga = {k: _bersih(yahoo[k]['Close']) for k in sum(KELOMPOK.values(), []) if k in yahoo}
    for r in bi.itertuples():
        t = pd.Timestamp(r.tanggal)
        E = int(tgl_ih.searchsorted(t))
        if E < 1 or E >= len(tgl_ih) or (tgl_ih[E] - t).days > 3:
            continue
        p = {'tanggal': tgl_ih[E], 'bp': int(r.ubah_bp), 'periode': _periode(tgl_ih[E])}
        for w, (a0, a1) in JENDELA_BI.items():
            p[w] = float(np.log(ih.iloc[E + a1] / ih.iloc[E + a0])) if E + a1 < len(tgl_ih) else np.nan
        pasar.append(p)
        if r.ubah_bp == 0:
            continue
        for k, ya in harga.items():
            J = int(ya.index.searchsorted(t))
            if J < 1 or J >= len(ya) or (ya.index[J] - t).days > 3:
                continue
            beta = _beta(ya, ih, ya.index[J - 1])
            s = {'kode': k, 'tanggal': ya.index[J], 'bp': int(r.ubah_bp), 'beta': beta,
                 'semesta': _semesta(k), 'periode': p['periode']}
            for w, (a0, a1) in JENDELA_BI.items():
                if J + a1 >= len(ya):
                    s[w] = np.nan
                    continue
                ta, tb = ya.index[J + a0], ya.index[J + a1]
                s[w] = float(np.log(ya.iloc[J + a1] / ya.iloc[J + a0])) - beta * _ret_ih(ih, ta, tb)
            saham.append(s)
    return pd.DataFrame(pasar), pd.DataFrame(saham)


# ============================================================ simulasi twin
_KONTEKS = {}


def _init_proses(konteks):
    _KONTEKS.update(konteks)


def _events(kunci):
    if kunci[0] == 'div':
        return [{'hari': H0, 'jenis': 'dividen', 'target': kunci[1], 'besar': kunci[2], 'durasi': CUM}]
    if kunci[0] == 'bi':
        return [{'hari': H0, 'jenis': 'suku_bunga', 'target': 'semua', 'besar': kunci[1], 'durasi': 20}]
    return []


def _satu_dunia(tugas):
    kel, seed, kunci = tugas
    prof, kal, cfg = _KONTEKS[kel]
    ev, peringatan = skenario.siapkan(_events(kunci), prof, cfg['kodes'], cfg['hari'])
    if kunci[0] != 'base' and not ev:
        return tugas, None
    w = Dunia(prof, cfg, seed, ev, kal, skenario.butuh_cadangan(ev))
    w.jalan()
    return tugas, {'close': w.rek['close'].copy(), 'ihsg': w.rek['ihsg'].copy()}


class _Kanal(jalan._KanalCetak):
    pass


def siapkan_kelompok():
    """Profil + kalibrasi mikro tiap kelompok (cache bawaan twin)."""
    konteks, info = {}, {}
    for kel, kodes in KELOMPOK.items():
        t0 = time.time()
        prof = kalibrasi.profil(kodes)
        ada = [k for k in kodes if k in prof['saham']]
        c = jalan.normalisasi({'kodes': ada, 'hari': HARI})
        kal = jalan.kalibrasi_mikro(prof, c, ada, None)
        cfg = jalan._cfg_dunia(c, ada)
        konteks[kel] = (prof, kal, cfg)
        info[kel] = {'kodes': ada, 'beta': {k: prof['saham'][k]['beta'] for k in ada},
                     'sektor': {k: prof['saham'][k].get('sektor', '-') for k in ada}}
        print('[%s] %s siap (%.0f dtk)%s' % (kel, ' '.join(ada), time.time() - t0,
                                           '' if len(ada) == len(kodes) else
                                           ' -- TANPA ' + ' '.join(sorted(set(kodes) - set(ada)))), flush=True)
    return konteks, info


def _berkas_sim():
    return os.path.join(RC, 'twin_uji_mundur_sim_v%d.pkl' % jalan.VERSI_MODEL)


def simulasi(n_proses):
    konteks, info = siapkan_kelompok()
    berkas = _berkas_sim()
    hasil = {}
    if os.path.exists(berkas):
        with open(berkas, 'rb') as fh:
            simpan = pickle.load(fh)
        if simpan.get('kunci') == _kunci_sim():
            hasil = simpan['hasil']
    tugas = []
    for kel, (prof, kal, cfg) in konteks.items():
        kunci = [('base',)] + [('bi', bp) for bp in GRID_BP] + \
                [('div', k, y) for k in cfg['kodes'] for y in GRID_Y]
        tugas += [(kel, sd, kc) for sd in SEEDS for kc in kunci]
    sisa = [t for t in tugas if t not in hasil]
    print('Dunia twin: %d total, %d sudah di cache, %d dijalankan dengan %d proses'
          % (len(tugas), len(tugas) - len(sisa), len(sisa), n_proses), flush=True)

    def simpan_cache():
        with open(berkas + '.tmp', 'wb') as fh:
            pickle.dump({'kunci': _kunci_sim(), 'hasil': hasil, 'info': info}, fh)
        os.replace(berkas + '.tmp', berkas)

    if sisa:
        import multiprocessing as mp
        t0 = time.time()
        with mp.Pool(n_proses, initializer=_init_proses, initargs=(konteks,)) as pool:
            for i, (t, r) in enumerate(pool.imap_unordered(_satu_dunia, sisa, chunksize=2), 1):
                hasil[t] = r
                if i % 100 == 0 or i == len(sisa):
                    simpan_cache()
                    lalu = time.time() - t0
                    print('  %d/%d dunia, %.0f dtk, sisa ~%.0f dtk' % (i, len(sisa), lalu, lalu / i * (len(sisa) - i)),
                          flush=True)
    simpan_cache()
    return hasil, info


def _kunci_sim():
    return {'kelompok': KELOMPOK, 'grid_y': GRID_Y, 'grid_bp': GRID_BP, 'seeds': SEEDS,
            'hari': HARI, 'h0': H0, 'cum': CUM, 'versi': jalan.VERSI_MODEL}


def efek_twin(hasil, info):
    """Selisih skenario - baseline (log) per jendela, rata-rata antar seed."""
    B = 10
    div, bi = {}, {}
    for kel, inf in info.items():
        kodes = inf['kodes']
        for sd in SEEDS:
            base = hasil.get((kel, sd, ('base',)))
            if base is None:
                continue
            lc_b, li_b = np.log(base['close']), np.log(base['ihsg'])
            for kunci in [('bi', bp) for bp in GRID_BP] + [('div', k, y) for k in kodes for y in GRID_Y]:
                s = hasil.get((kel, sd, kunci))
                if s is None:
                    continue
                d = np.log(s['close']) - lc_b
                di = np.log(s['ihsg']) - li_b
                if kunci[0] == 'div':
                    j = kodes.index(kunci[1])
                    E = B + H0 + CUM
                    for w, (a0, a1) in JENDELA_DIV.items():
                        div.setdefault((kunci[1], kunci[2], w), []).append(d[E + a1, j] - d[E + a0, j])
                else:
                    E = B + H0
                    for w, (a0, a1) in JENDELA_BI.items():
                        bi.setdefault(('IHSG', kunci[1], w), []).append(di[E + a1] - di[E + a0])
                        for j, k in enumerate(kodes):
                            tot = d[E + a1, j] - d[E + a0, j]
                            abn = tot - inf['beta'][k] * (di[E + a1] - di[E + a0])
                            bi.setdefault((k, kunci[1], w), []).append(abn)
    return div, bi


def tebak_dividen(div, k, y, w):
    xs = [0.0] + list(GRID_Y)
    ys = [0.0] + [float(np.mean(div[(k, g, w)])) if (k, g, w) in div else np.nan for g in GRID_Y]
    if not np.all(np.isfinite(ys)):
        return np.nan
    if y <= xs[-1]:
        return float(np.interp(y, xs, ys))
    return float(ys[-1] + (ys[-1] - ys[-2]) / (xs[-1] - xs[-2]) * (y - xs[-1]))


def tebak_bi(bi, k, bp, w):
    if bp == 0:
        return 0.0
    xs = list(GRID_BP)
    ys = [float(np.mean(bi[(k, g, w)])) if (k, g, w) in bi else np.nan for g in xs]
    if not np.all(np.isfinite(ys)):
        return np.nan
    return float(np.interp(bp, xs, ys))


# ================================================================ evaluasi
def _ols(X, y):
    X = np.column_stack([np.ones(len(y))] + [np.asarray(x, dtype=float) for x in X])
    b, *_ = np.linalg.lstsq(X, np.asarray(y, dtype=float), rcond=None)
    return b


def _pakai(b, X):
    return b[0] + sum(bi * np.asarray(x, dtype=float) for bi, x in zip(b[1:], X))


def _skor(y, pred, pembanding):
    sse = float(((y - pred) ** 2).sum())
    out = {'rmse': float(np.sqrt(sse / len(y))) * 100}
    for nama, p in pembanding.items():
        ref = float(((y - p) ** 2).sum())
        out['r2_vs_' + nama] = 1 - sse / ref if ref > 0 else np.nan
    sd = np.std(pred)
    out['korelasi'] = float(np.corrcoef(pred, y)[0, 1]) if sd > 1e-12 and np.std(y) > 0 else np.nan
    return out


def _bootstrap(y, a, b, kelompok, n=2000, seed=7):
    """Selang 90% untuk 1 - SSE(a)/SSE(b) (positif = a lebih baik dari b),
    resampling per kelompok (bulan / event) supaya event yang berdekatan
    tidak dihitung sebagai bukti independen."""
    rng = np.random.default_rng(seed)
    g = pd.factorize(kelompok)[0]
    idx = [np.flatnonzero(g == i) for i in range(g.max() + 1)]
    ea, eb = (y - a) ** 2, (y - b) ** 2
    nilai = []
    for _ in range(n):
        pilih = np.concatenate([idx[i] for i in rng.integers(0, len(idx), len(idx))])
        sb = eb[pilih].sum()
        if sb > 0:
            nilai.append(1 - ea[pilih].sum() / sb)
    return float(np.percentile(nilai, 5)), float(np.percentile(nilai, 95))


def _twin_rata2_saham(div, y, w):
    """Respons twin rata-rata LINTAS SAHAM di imbal hasil y: bagian twin yang
    cuma fungsi imbal hasil (bentuk kurva = asumsi skenario.py). Sisanya
    (twin - ini) = bagian yang khas per saham, hasil dinamika agen."""
    xs = [0.0] + list(GRID_Y)
    ys = [0.0] + [float(np.mean([np.mean(v) for (k, g, ww), v in div.items() if g == gy and ww == w]))
                  for gy in GRID_Y]
    if y <= xs[-1]:
        return float(np.interp(y, xs, ys))
    return float(ys[-1] + (ys[-1] - ys[-2]) / (xs[-1] - xs[-2]) * (y - xs[-1]))


def evaluasi_dividen(ev, div):
    keluar = {}
    for w in JENDELA_DIV:
        d = ev.dropna(subset=[w]).copy()
        d['twin'] = [tebak_dividen(div, r.kode, r.imbal, w) for r in d.itertuples()]
        d = d.dropna(subset=['twin'])
        d['twin_khas'] = d['twin'] - [_twin_rata2_saham(div, y, w) for y in d['imbal']]
        d['imbal_cap'] = d['imbal'].clip(upper=0.10)       # sama dengan batas skala di event dividen twin
        d['mekanis'] = np.log1p(-d['imbal']) if w in ('ex', 'ex2') else 0.0
        kal = d[(d['semesta'] == 'A') & (d['periode'] == 'P1')]
        b_h = _ols([kal['imbal']], kal[w])
        b_hc = _ols([kal['imbal_cap']], kal[w])
        b_t = _ols([kal['twin']], kal[w])
        b_ht = _ols([kal['imbal'], kal['twin']], kal[w])
        b_hk = _ols([kal['imbal_cap'], kal['twin_khas']], kal[w])
        d['historis'] = _pakai(b_h, [d['imbal']])
        d['historis_cap'] = _pakai(b_hc, [d['imbal_cap']])
        d['twin_kal'] = _pakai(b_t, [d['twin']])
        d['historis+twin'] = _pakai(b_ht, [d['imbal'], d['twin']])
        d['cap+khas_twin'] = _pakai(b_hk, [d['imbal_cap'], d['twin_khas']])
        sel = {}
        for (s, p), g in d.groupby(['semesta', 'periode']):
            y = g[w].to_numpy()
            pemb = {'nol': np.zeros(len(g)), 'historis': g['historis'].to_numpy()}
            sel['%s x %s' % (s, p)] = {
                'n': int(len(g)),
                'aktual_rata2': float(y.mean()) * 100,
                'rasio_turun': float(np.median(y / np.log1p(-g['imbal'].to_numpy()))) if w in ('ex', 'ex2') else None,
                'model': {m: _skor(y, g[m].to_numpy(), pemb)
                          for m in ('mekanis', 'historis', 'historis_cap', 'twin', 'twin_kal', 'historis+twin',
                                    'cap+khas_twin')},
            }
            if s == 'B' and p == 'P2':
                bulan = g['tanggal'].dt.to_period('M').astype(str).to_numpy()
                sel['%s x %s' % (s, p)]['ci90'] = {
                    'twin_kal vs historis': _bootstrap(y, g['twin_kal'].to_numpy(), g['historis'].to_numpy(), bulan),
                    'twin_kal vs historis_cap': _bootstrap(y, g['twin_kal'].to_numpy(), g['historis_cap'].to_numpy(),
                                                           bulan),
                    'historis+twin vs historis': _bootstrap(y, g['historis+twin'].to_numpy(),
                                                            g['historis'].to_numpy(), bulan),
                    'cap+khas_twin vs historis_cap': _bootstrap(y, g['cap+khas_twin'].to_numpy(),
                                                                g['historis_cap'].to_numpy(), bulan),
                    'twin vs mekanis': _bootstrap(y, g['twin'].to_numpy(), g['mekanis'].to_numpy(), bulan),
                }
                sel['%s x %s' % (s, p)]['korelasi_khas_vs_sisa'] = float(np.corrcoef(
                    g['twin_khas'], y - g['historis_cap'])[0, 1])
        keluar[w] = {'koef': {'historis': b_h.tolist(), 'historis_cap': b_hc.tolist(), 'twin_kal': b_t.tolist(),
                              'historis+twin': b_ht.tolist(), 'cap+khas_twin': b_hk.tolist()},
                     'sd_khas_twin': float(d['twin_khas'].std()) * 100,
                     'sel': sel,
                     'twin_vs_imbal': _twin_per_imbal(div, w)}
    return keluar


def _twin_per_imbal(div, w):
    """Rata-rata tebakan twin per imbal hasil grid (lintas saham), untuk
    melihat bentuk respons twin di samping data."""
    out = {}
    for g in GRID_Y:
        v = [np.mean(x) for (k, y, ww), x in div.items() if y == g and ww == w]
        if v:
            out['%.0f%%' % (g * 100)] = {'rata2': float(np.mean(v)) * 100, 'sd_lintas_saham': float(np.std(v)) * 100}
    return out


def evaluasi_bi(pasar, saham, bi, info):
    keluar = {'pasar': {}, 'saham': {}}
    for w in JENDELA_BI:
        d = pasar.dropna(subset=[w]).copy()
        d['twin'] = [tebak_bi(bi, 'IHSG', bp, w) for bp in d['bp']]
        kal = d[d['periode'] == 'P1']
        b_h = _ols([kal['bp']], kal[w])
        d['historis'] = _pakai(b_h, [d['bp']])
        sel = {}
        for p, g in d.groupby('periode'):
            for nama, gg in (('semua', g), ('berubah', g[g['bp'] != 0])):
                y = gg[w].to_numpy()
                pemb = {'nol': np.zeros(len(gg)), 'historis': gg['historis'].to_numpy()}
                sel['%s %s' % (p, nama)] = {
                    'n': int(len(gg)),
                    'naik_rata2': float(gg.loc[gg['bp'] > 0, w].mean()) * 100,
                    'turun_rata2': float(gg.loc[gg['bp'] < 0, w].mean()) * 100,
                    'tahan_rata2': float(gg.loc[gg['bp'] == 0, w].mean()) * 100 if nama == 'semua' else None,
                    'twin_naik25': tebak_bi(bi, 'IHSG', 25, w) * 100,
                    'model': {m: _skor(y, gg[m].to_numpy(), pemb) for m in ('historis', 'twin')},
                }
        keluar['pasar'][w] = {'koef_historis_per_25bp': float(b_h[1]) * 25 * 100, 'sel': sel}

        d = saham.dropna(subset=[w]).copy()
        d['twin'] = [tebak_bi(bi, r.kode, r.bp, w) for r in d.itertuples()]
        d = d.dropna(subset=['twin'])
        sektor = {k: s for inf in info.values() for k, s in inf['sektor'].items()}
        d['sektor'] = d['kode'].map(sektor).fillna('-')
        kal = d[(d['semesta'] == 'A') & (d['periode'] == 'P1')]
        x = kal['bp'] / 25.0
        sens = (kal[w] * x).groupby(kal['sektor']).sum() / (x * x).groupby(kal['sektor']).sum()
        d['sektor_hist'] = d['sektor'].map(sens).fillna(0.0) * d['bp'] / 25.0
        b_t = _ols([kal['twin']], kal[w])
        d['twin_kal'] = _pakai(b_t, [d['twin']])
        sel = {}
        for (s, p), g in d.groupby(['semesta', 'periode']):
            y = g[w].to_numpy()
            pemb = {'nol': np.zeros(len(g)), 'sektor_hist': g['sektor_hist'].to_numpy()}
            ic = []
            for _, e in g.groupby('tanggal'):
                if len(e) >= 5 and e['twin'].std() > 0 and e[w].std() > 0:
                    ic.append(e[['twin', w]].rank().corr().iloc[0, 1])
            sel['%s x %s' % (s, p)] = {
                'n': int(len(g)), 'n_event': int(g['tanggal'].nunique()),
                'ic_rata2': float(np.mean(ic)) if ic else np.nan,
                'ic_positif': '%d/%d' % (sum(v > 0 for v in ic), len(ic)),
                'model': {m: _skor(y, g[m].to_numpy(), pemb) for m in ('sektor_hist', 'twin', 'twin_kal')},
            }
        keluar['saham'][w] = {'sel': sel}
    return keluar


# ================================================================== cetak
def _cetak_model(sel, urutan):
    for nama in urutan:
        if nama not in sel:
            continue
        v = sel[nama]
        if nama == urutan[0]:
            print('    %s (UJI)  n=%d' % (nama, v['n']))
            for m, x in v['model'].items():
                print('      %-14s rmse %5.2f   R2/nol %+.3f   R2/historis %+.3f   korelasi %s' % (
                    m, x['rmse'], x['r2_vs_nol'], x['r2_vs_historis'],
                    '%+.3f' % x['korelasi'] if np.isfinite(x['korelasi']) else '  -'))
        else:
            print('    %-8s n=%-4d R2/nol: %s' % (nama, v['n'], '  '.join(
                '%s %+.3f' % (m, x['r2_vs_nol']) for m, x in v['model'].items())))
        if v.get('rasio_turun') is not None:
            print('      rasio turun / dividen (median): %.2f' % v['rasio_turun'])
        for k, (lo, hi) in (v.get('ci90') or {}).items():
            print('      CI90 %-30s %+.3f .. %+.3f' % (k, lo, hi))
        if v.get('korelasi_khas_vs_sisa') is not None:
            print('      korelasi bagian khas-saham twin vs sisa historis_cap: %+.3f' % v['korelasi_khas_vs_sisa'])


def cetak(hasil):
    print('\n' + '=' * 100)
    print('DIVIDEN (return abnormal, %; R2 luar sampel vs tebakan 0 dan vs model historis imbal hasil)')
    print('=' * 100)
    for w, v in hasil['dividen'].items():
        print('\n  Jendela %s   koef historis a+b*imbal: %s' % (w, ['%.4f' % x for x in v['koef']['historis']]))
        print('    rata2 aktual: ' + ', '.join('%s %+.2f%% (n %d)' % (k, s['aktual_rata2'], s['n']) for k, s in v['sel'].items()))
        print('    twin per imbal hasil: ' + ', '.join('%s %+.2f%% (sd %.2f)' % (k, x['rata2'], x['sd_lintas_saham'])
                                                     for k, x in v['twin_vs_imbal'].items()))
        print('    sd bagian khas-saham twin: %.2f%%' % v['sd_khas_twin'])
        _cetak_model(v['sel'], ['B x P2', 'A x P2', 'B x P1', 'A x P1'])
    print('\n' + '=' * 100)
    print('BI RATE -- IHSG (log return %)')
    print('=' * 100)
    for w, v in hasil['bi']['pasar'].items():
        print('\n  Jendela %s   historis per +25 bp: %+.2f%%' % (w, v['koef_historis_per_25bp']))
        for nama, s in v['sel'].items():
            print('    %-12s n=%-3d naik %+.2f turun %+.2f%s | twin +25bp %+.2f | ' % (
                nama, s['n'], s['naik_rata2'], s['turun_rata2'],
                '' if s['tahan_rata2'] is None else ' tahan %+.2f' % s['tahan_rata2'], s['twin_naik25'])
                + ' '.join('[%s] rmse %.2f R2/nol %+.3f R2/hist %+.3f' % (m, x['rmse'], x['r2_vs_nol'], x['r2_vs_historis'])
                           for m, x in s['model'].items()))
    print('\n' + '=' * 100)
    print('BI RATE -- LINTAS SAHAM (return abnormal, hanya keputusan yang mengubah bunga)')
    print('=' * 100)
    for w, v in hasil['bi']['saham'].items():
        print('\n  Jendela %s' % w)
        for nama in ['B x P2', 'A x P2', 'B x P1', 'A x P1']:
            s = v['sel'].get(nama)
            if not s:
                continue
            print('    %-8s n=%-4d event %-3d IC twin %+.3f (%s) | ' % (nama, s['n'], s['n_event'], s['ic_rata2'], s['ic_positif'])
                  + ' '.join('[%s] R2/nol %+.3f R2/sekt %+.3f' % (m, x['r2_vs_nol'], x['r2_vs_sektor_hist'])
                             for m, x in s['model'].items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--proses', type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument('--evaluasi', action='store_true', help='lewati simulasi, pakai cache')
    a = ap.parse_args()
    t0 = time.time()
    if a.evaluasi:
        with open(_berkas_sim(), 'rb') as fh:
            simpan = pickle.load(fh)
        hasil_sim, info = simpan['hasil'], simpan['info']
    else:
        hasil_sim, info = simulasi(a.proses)
    div, bi = efek_twin(hasil_sim, info)

    mentah, yahoo, ih = muat_pasar()
    ev_div = event_dividen(mentah, yahoo, ih)
    pasar, saham = event_bi(yahoo, ih)
    print('\nEvent dividen: %d (%s)' % (len(ev_div), ev_div.groupby(['semesta', 'periode']).size().to_dict()))
    print('Keputusan BI: %d (%d berubah); baris saham x perubahan: %d' % (len(pasar), int((pasar['bp'] != 0).sum()), len(saham)))
    rasio = (ev_div['ex'] / np.log1p(-ev_div['imbal'])).median()
    print('Cek pemetaan ex-date: median (return abnormal hari ex / log(1-imbal)) = %.2f' % rasio)

    hasil = {'dibuat': time.strftime('%Y-%m-%d %H:%M'), 'kunci_sim': {k: (list(v) if isinstance(v, tuple) else v)
                                                                     for k, v in _kunci_sim().items()},
             'dividen': evaluasi_dividen(ev_div, div), 'bi': evaluasi_bi(pasar, saham, bi, info)}
    cetak(hasil)
    with open(os.path.join(RC, 'twin_uji_mundur_hasil.json'), 'w', encoding='utf-8') as fh:
        json.dump(hasil, fh, ensure_ascii=False, indent=1, default=float)
    ev_div.to_pickle(os.path.join(RC, 'twin_uji_mundur_event_dividen.pkl'))
    print('\nSelesai %.0f dtk. Hasil: research_cache/twin_uji_mundur_hasil.json' % (time.time() - t0))


if __name__ == '__main__':
    for v in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
        os.environ.setdefault(v, '1')
    main()
