"""
Mean reversion & kointegrasi: harga yang "kejauhan" balik ke rata-ratanya?

DESAIN (didaftar SEBELUM hasil dilihat, 18 Okt 2026)
Semesta: emiten layak uji.muat() (median nilai >= Rp1M, harga >= 100,
diperdagangkan >= 90%, tanpa loncatan data). Sel = belahan emiten (md5) x
periode (2013-19 / 2020-26). Masuk di CLOSE t+1 (konvensi panel; sekaligus
membuang efek bid-ask bounce hari sinyal). Biaya pulang-pergi 0,4% per kaki.

BAGIAN 1 -- tunggal (reversal jangka pendek, Jegadeesh 1990 / Lehmann 1990)
  S1 = -ret 5 hari                              (pecundang minggu ini)
  S2 = -(ret 5 hari - rata2 sektornya)          (reversal disesuaikan sektor,
                                                 Da-Liu-Schaumburg 2014)
  S3 = -(close/MA20 - 1) / vol20                (z-skor "kejauhan dari MA20")
  Target: selisih log vs semua emiten layak hari itu
     f5  = close t+1 -> t+6,   f20 = close t+1 -> t+21
  Kuintil skor dengan batas 2013-2019; Q5 = paling "oversold".
  LOLOS kalau Q5-Q1 > 0 di 4 sel, t > 2 tiap periode (t dari rata2 bulanan),
  DAN tetap positif di tertil likuiditas TERATAS (bukan cuma saham sepi yang
  mantul karena spread). Layak dibeli cuma kalau Q5 sendiri > +0,4%.

BAGIAN 2 -- pasangan (kointegrasi Engle-Granger, kerangka Gatev-Goetzmann-
  Rouwenhorst 2006)
  Tiap ~21 hari bursa: pembentukan 250 hari, pasangan SESEKTOR dan SEBELAHAN
  emiten. log P_i = a + b log P_j + e; uji ADF (1 lag) pada e, dua arah,
  ambil t paling negatif. Pilih 20 pasangan t terendah yang < -3,37 (kritis
  5% MacKinnon 2 variabel). Perdagangan 126 hari berikutnya: z = (e - rata2
  pembentukan)/sd pembentukan; buka saat |z| >= 2 (masuk close besoknya),
  beli kaki murah / jual kaki mahal, tutup saat z menyeberang 0 (close
  besoknya) atau akhir jendela. Boleh buka lagi.
  BEI praktis tak bisa short -> yang dinilai UTAMA = kaki BELI saja, selisih
  log vs pasar (rata2 emiten layak) selama dipegang.
  LOLOS kalau kaki beli > 0 di 4 sel, t > 2 tiap periode, DAN bersih biaya
  0,4% masih positif tiap periode. Long-short dilaporkan sebagai teori.
  Kontrol: 20 pasangan ACAK sesektor (tanpa syarat kointegrasi), aturan sama.
  Kalau kointegrasi tak mengalahkan acak, yang tersisa cuma reversal sektor.

HASIL (18 Okt 2026, 760 emiten layak, 491 rb emiten-hari): DUA-DUANYA GAGAL.
  Tunggal: arahnya TERBALIK -- yang paling "oversold" malah lanjut kalah.
    S1 (-ret5) -> f20 Q5-Q1: -1,02 (P1, t -3,2), -1,39 (P2, t -4,2); Q5
    sendiri -0,6/-1,2% vs pasar. f5 P2 -0,79 (t -7,0). S2 (disesuaikan
    sektor) dan S3 (z-skor MA20) sama: negatif di keempat sel, t -2..-5.
    Di tertil likuiditas teratas efeknya mengecil ke ~0 (t -0,2..-2,2):
    lanjutan turun paling kuat di saham sepi. Catatan: masuk close t+1 sengaja
    membuang reversal H+1 versi bid-ask bounce (lead_lag pun cuma -0,05).
    Ini sejalan dengan momentum yang lolos & "jebol support" yang negatif --
    bukan temuan baru, cuma konfirmasi: di BEI jangan beli yang lagi jatuh.
  Pasangan: kointegrasi = acak. Kaki beli vs pasar +0,63/+0,53% (t 1,0/0,8),
    pasangan ACAK sesektor +0,62/+0,35% -- tak beda. Bersih biaya ~+0,2/+0,1%,
    belahan 0 P1 -1,14%. Long-short (teori, BEI tak bisa short) -0,17/-0,97%.
    Tertil |z| buka tak monoton. Hubungan "kointegrasi" 250 hari tidak
    bertahan di 126 hari berikutnya; dari ribuan pasangan per bulan, t < -3,37
    sebagian besar cuma kebetulan (multiple testing).

ULANGAN 2 -- pasangan + saringan korelasi (didaftar SEBELUM hasil, 18 Okt 2026)
  Alasan: pasangan pilihan di atas ternyata TIDAK bergerak bareng -- median
  korelasi return harian masa pembentukan 0,15, sama dengan pasangan acak
  (77% di bawah 0,3). Uji kointegrasi lolos karena kebetulan, bukan karena
  dua saham itu "kembar".
  Perubahan SATU saja: sebelum uji kointegrasi, pasangan wajib korelasi
  return log harian 250 hari pembentukan >= 0,5. Sisanya sama persis
  (t < -3,37, 20 terbaik, |z| >= 2, 126 hari, masuk close t+1).
  Kontrol: 20 pasangan ACAK dari yang korelasi >= 0,5 (tanpa syarat
  kointegrasi) -- memisahkan "kointegrasi" dari sekadar "saham kembar".
  LOLOS kalau kaki beli vs pasar > 0 di 4 sel, t > 2 tiap periode, bersih
  biaya 0,4% positif tiap periode, DAN mengalahkan kontrol di kedua periode.
  Ambang 0,4 / 0,6 dilaporkan sebagai kepekaan saja, TIDAK dipakai memutus.

HASIL ULANGAN 2 (18 Okt 2026): GAGAL.
  Kor >= 0,5 + koint: cuma 1,6 pasangan/pembentukan (419 transaksi, korelasi
  rata2 0,60). Kaki beli vs pasar +4,55 (P1, t 2,7) / +1,72 (P2, t 0,8);
  positif di 4 sel, tapi P2 t < 2 dan KALAH dari kontrol acak-kembar di P2
  (+2,52, t 3,2) -> dua syarat gugur.
  Kontrol acak-kembar kelihatan bagus (+2,5% vs pasar di 2 periode), tapi
  memegang KEDUA kaki pasangan itu 126 hari tanpa sinyal apa pun sudah dapat
  +2,9 / +1,0 per ~62 hari (CAGR +10,1 / +2,1% vs pasar -6,4 / -10,9%): saham
  kembar = big cap likuid yang memang mengalahkan rata2 emiten (efek ukuran),
  bukan efek "balik ke rata2". Bagian timing-nya (long-short, kaki murah vs
  kaki mahal) +0,47/+2,03 di 0,5, tapi +0,23/+0,71 (t < 1) di 0,4 dan
  +0,27/+2,63 di 0,6 -- tak kokoh terhadap ambang.

PEMAKAIAN: python -m website.riset_pola_naik.balik_rata {tunggal|pasangan [kor_min]}
"""
import sys
import time

import numpy as np
import pandas as pd

from . import uji as U
from .lead_lag import peta

BATAS = '2020-01-01'
BIAYA = 0.004
FORM, DAGANG, LANGKAH, TOP, ZBUKA = 250, 126, 21, 20, 2.0
KRITIS = -3.37


# ----------------------------------------------------------------- bagian 1
def _siapkan_tunggal(p):
    p = p.sort_values(['ticker', 'date']).copy()
    g = p.groupby('ticker', sort=False)['close']
    p['r1'] = g.pct_change()
    p['r5'] = g.pct_change(5)
    p['f5'] = g.shift(-6) / g.shift(-1) - 1
    p['f20'] = g.shift(-21) / g.shift(-1) - 1
    loncat = (p['r1'].abs() > 0.45).astype(float)
    lg = loncat.groupby(p['ticker'])
    for f, h in (('f5', 6), ('f20', 21)):
        maju = sum(lg.shift(-k).fillna(1) for k in range(1, h + 1))
        p.loc[maju > 0, f] = np.nan
    p.loc[lg.transform(lambda s: s.rolling(6, min_periods=1).max()) > 0, 'r5'] = np.nan

    p = p[p['elig']].copy()
    for f in ('f5', 'f20'):
        lr = np.log1p(p[f])
        p['x' + f] = lr - lr.groupby(p['date']).transform('mean')
    p['sektor'] = p['ticker'].map(peta('sector'))
    gs = p.groupby(['date', 'sektor'])['r5']
    p['r5s'] = np.where(gs.transform('count') >= 5, p['r5'] - gs.transform('mean'), np.nan)
    p['S1'] = -p['r5']
    p['S2'] = -p['r5s']
    p['S3'] = -p['ma20'] / p['vol20'].replace(0, np.nan)
    p['likuid'] = p.groupby('date')['medval20'].rank(pct=True).gt(2 / 3)
    return p


def _t_bulanan(sub, target):
    m = sub.groupby(['month', 'q'])[target].mean().unstack()
    if 1 not in m or 5 not in m:
        return np.nan, np.nan
    d = (m[5] - m[1]).dropna()
    if len(d) < 6:
        return np.nan, np.nan
    return d.mean(), d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))


def _laporan_tunggal(p, s, target):
    k = p[p[s].notna() & p[target].notna()].copy()
    batas = np.quantile(k.loc[k['date'] < BATAS, s], [0.2, 0.4, 0.6, 0.8])
    k['q'] = np.digitize(k[s], batas) + 1
    print('\n%s -> %s (selisih log vs pasar, %%)' % (s, target))
    print('sel                 Q1      Q2      Q3      Q4      Q5   Q5-Q1      t       n')
    for per in (1, 2):
        for half, nama in ((0, 'belahan 0'), (1, 'belahan 1'), (None, 'gabung'), ('lik', 'likuid atas')):
            sub = k[k['period'] == per]
            if half == 'lik':
                sub = sub[sub['likuid']]
            elif half is not None:
                sub = sub[sub['half'] == half]
            q = sub.groupby('q')[target].mean() * 100
            d, t = _t_bulanan(sub, target)
            print('P%d %-13s %s  %+6.3f  %5.1f  %7d'
                  % (per, nama, ' '.join('%+7.3f' % q.get(i, np.nan) for i in range(1, 6)),
                     d * 100, t, len(sub)))


def cmd_tunggal():
    p = _siapkan_tunggal(U.muat())
    print('emiten-hari layak: %d, emiten: %d' % (len(p), p['ticker'].nunique()))
    for s in ('S1', 'S2', 'S3'):
        for target in ('xf5', 'xf20'):
            _laporan_tunggal(p, s, target)


# ----------------------------------------------------------------- bagian 2
def _adf_t(E):
    """t-stat ADF(1 lag, tanpa konstanta) per kolom matriks residu E (T x P)."""
    dE = np.diff(E, axis=0)
    y, x1, x2 = dE[1:], E[1:-1], dE[:-1]
    s11, s22, s12 = (x1 * x1).sum(0), (x2 * x2).sum(0), (x1 * x2).sum(0)
    s1y, s2y = (x1 * y).sum(0), (x2 * y).sum(0)
    det = s11 * s22 - s12 ** 2
    g = (s22 * s1y - s12 * s2y) / det
    ph = (s11 * s2y - s12 * s1y) / det
    u = y - g * x1 - ph * x2
    s2 = (u * u).sum(0) / (len(y) - 2)
    se = np.sqrt(s2 * s22 / det)
    return g / se


def _pasangan_grup(L, kor_min=None):
    """L: T x N log harga. -> (i, j, a, b, mu, sd, t, kor) semua pasangan."""
    T, N = L.shape
    I, J = np.triu_indices(N, 1)
    K = np.corrcoef(np.diff(L, axis=0), rowvar=False)[I, J]
    if kor_min is not None:
        I, J = I[K >= kor_min], J[K >= kor_min]
        K = K[K >= kor_min]
        if not len(I):
            return pd.DataFrame(columns=['i', 'j', 'a', 'b', 'mu', 'sd', 't', 'kor'])
    K = np.concatenate([K, K])
    I, J = np.concatenate([I, J]), np.concatenate([J, I])      # dua arah regresi
    Lm = L - L.mean(0)
    b = (Lm[:, I] * Lm[:, J]).sum(0) / (Lm[:, J] ** 2).sum(0)
    a = L[:, I].mean(0) - b * L[:, J].mean(0)
    E = L[:, I] - a - b * L[:, J]
    t = _adf_t(E)
    ok = b > 0
    df = pd.DataFrame({'i': I, 'j': J, 'a': a, 'b': b, 'mu': E.mean(0), 'sd': E.std(0), 't': t, 'kor': K})[ok]
    df['kunci'] = np.minimum(df['i'], df['j']) * 10 ** 6 + np.maximum(df['i'], df['j'])
    df = df.sort_values('t').drop_duplicates('kunci')
    return df


def _bentuk(C, elig, sektor, half, bad, kor_min=None):
    """Daftar (t0, pasangan) per pembentukan, untuk 'koint' dan 'acak'."""
    rng = np.random.default_rng(7)
    out = []
    dates = C.index
    logC = np.log(C.to_numpy())
    badv = bad.to_numpy()
    eligv = elig.to_numpy()
    tick = np.array(C.columns)
    sek = np.array([sektor.get(x) for x in tick], dtype=object)
    hv = np.array([half[x] for x in tick])
    t0s = [t for t in range(FORM, len(dates) - 2, LANGKAH) if dates[t] >= pd.Timestamp('2013-06-01')]
    for t0 in t0s:
        w = logC[t0 - FORM + 1:t0 + 1]
        ok = eligv[t0] & ~np.isnan(w).any(0) & (badv[t0 - FORM + 1:t0 + 1].sum(0) == 0)
        for h in (0, 1):
            kandidat = []
            for s in set(sek[ok & (hv == h)]) - {None}:
                kol = np.where(ok & (hv == h) & (sek == s))[0]
                if len(kol) < 3:
                    continue
                df = _pasangan_grup(w[:, kol], kor_min)
                if not len(df):
                    continue
                df['i'] = kol[df['i'].to_numpy(int)]
                df['j'] = kol[df['j'].to_numpy(int)]
                kandidat.append(df)
            if not kandidat:
                continue
            semua = pd.concat(kandidat)
            if not len(semua):
                continue
            koint = semua[semua['t'] < KRITIS].nsmallest(TOP, 't')
            acak = semua.sample(min(TOP, len(semua)), random_state=int(rng.integers(1 << 30)))
            out.append((t0, h, koint, acak))
    return out


def _dagang(C, bad, M, bentukan, jenis):
    logC = np.log(C.to_numpy())
    badc = np.vstack([np.zeros((1, C.shape[1])), np.cumsum(bad.to_numpy(), 0)])
    n = len(C)
    tr = []
    for t0, h, koint, acak in bentukan:
        pasang = koint if jenis == 'koint' else acak
        akhir = min(t0 + DAGANG, n - 2)
        for r in pasang.itertuples():
            e = logC[t0 + 1:akhir + 1, r.i] - r.a - r.b * logC[t0 + 1:akhir + 1, r.j]
            z = (e - r.mu) / r.sd
            k = 0
            while k < len(z):
                if np.isnan(z[k]) or abs(z[k]) < ZBUKA:
                    k += 1
                    continue
                arah = np.sign(z[k])
                m = k + 1
                while m < len(z) and not (z[m] * arah <= 0):
                    m += 1
                ts = t0 + 1 + k                     # hari sinyal
                tx = min(t0 + 1 + m, akhir)         # hari sinyal tutup (atau akhir jendela)
                masuk, keluar = ts + 1, tx + 1 if tx < akhir else akhir
                if keluar <= masuk:
                    break
                beli, jual = (r.j, r.i) if arah > 0 else (r.i, r.j)
                lb = logC[keluar, beli] - logC[masuk, beli]
                lj = logC[keluar, jual] - logC[masuk, jual]
                rusak = (badc[keluar + 1, [beli, jual]] - badc[masuk + 1, [beli, jual]]).sum() > 0
                if not (np.isnan(lb) or np.isnan(lj) or rusak):
                    tr.append((C.index[masuk], h, C.columns[beli], C.columns[jual], masuk, keluar,
                               lb, lj, lb - (M[keluar] - M[masuk]), r.t, abs(z[k])))
                k = m + 1
    df = pd.DataFrame(tr, columns=['date', 'half', 'beli', 'jual', 'im', 'ik', 'lb', 'lj', 'xb', 'tstat', 'z'])
    df = df.drop_duplicates(['beli', 'jual', 'date'])
    df['ls'] = df['lb'] - df['lj']
    df['hari'] = df['ik'] - df['im']
    df['period'] = np.where(df['date'] < BATAS, 1, 2)
    df['month'] = df['date'].dt.to_period('M')
    return df


def _t_bln(x, month):
    m = x.groupby(month).mean()
    return m.mean() / (m.std(ddof=1) / np.sqrt(len(m))) if len(m) > 5 else np.nan


def _portofolio(df, C, M):
    """Harian, bobot sama tiap kaki beli yang sedang dipegang, biaya 0,2% per sisi."""
    r = np.exp(np.diff(np.log(C.to_numpy()), axis=0))  - 1      # r[d] = hari d -> d+1
    n = len(C)
    jumlah = np.zeros(n - 1); cnt = np.zeros(n - 1); ongkos = np.zeros(n - 1)
    kol = {c: k for k, c in enumerate(C.columns)}
    for x in df.itertuples():
        rr = r[x.im:x.ik, kol[x.beli]]
        rr = np.nan_to_num(rr)
        jumlah[x.im:x.ik] += rr
        cnt[x.im:x.ik] += 1
        ongkos[x.im] += BIAYA / 2
        ongkos[x.ik - 1] += BIAYA / 2
    aktif = cnt > 0
    harian = np.where(aktif, (jumlah - ongkos) / np.maximum(cnt, 1), 0.0)
    pasar = np.exp(np.diff(M)) - 1
    tgl = C.index[1:]
    out = {}
    for per, m in ((1, tgl < BATAS), (2, tgl >= BATAS)):
        th = m.sum() / 250
        st = np.prod(1 + harian[m]) ** (1 / th) - 1
        ps = np.prod(1 + pasar[m]) ** (1 / th) - 1
        out[per] = (st, ps, aktif[m].mean(), cnt[m & aktif].mean())
    return out


def cmd_pasangan(kor_min=None):
    t0 = time.time()
    p = U.muat()
    C = p.pivot(index='date', columns='ticker', values='close').sort_index()
    C = C.ffill(limit=5)
    elig = p.pivot(index='date', columns='ticker', values='elig').reindex_like(C).fillna(False).astype(bool)
    bad = (C.pct_change(fill_method=None).abs() > 0.45).astype(float)
    half = p.groupby('ticker')['half'].first().to_dict()
    sektor = peta('sector')
    # pasar = kumulatif rata2 log return harian emiten layak (tanpa loncatan)
    lr = np.log(C).diff()
    lr = lr.where(elig.shift(1, fill_value=False) & (bad == 0))
    M = np.concatenate([[0], np.nancumsum(lr.mean(1).to_numpy()[1:])])
    print('pivot %s, %.0f detik' % (C.shape, time.time() - t0), flush=True)
    bentukan = _bentuk(C, elig, sektor, half, bad, kor_min)
    print('pembentukan: %d, saringan korelasi %s, %.0f detik' % (len(bentukan), kor_min, time.time() - t0), flush=True)
    print('pasangan per pembentukan: koint %.1f, acak %.1f; korelasi rata2 koint %.2f'
          % (np.mean([len(b[2]) for b in bentukan]), np.mean([len(b[3]) for b in bentukan]),
             pd.concat([b[2] for b in bentukan])['kor'].mean()), flush=True)
    for jenis in ('koint', 'acak'):
        df = _dagang(C, bad, M, bentukan, jenis)
        print('\n== %s: %d transaksi, rata2 dipegang %.1f hari ==' % (jenis, len(df), df['hari'].mean()))
        print('sel             n   beli-vs-pasar  t    menang  bersih  | long-short  t   (log %, majemuk)')
        for per in (1, 2):
            for h in (0, 1, None):
                s = df[(df['period'] == per) & ((df['half'] == h) if h is not None else True)]
                print('P%d %-9s %6d   %+6.2f  %5.1f  %4.0f%%  %+6.2f  |  %+6.2f  %5.1f'
                      % (per, ('belahan %d' % h) if h is not None else 'gabung', len(s),
                         s['xb'].mean() * 100, _t_bln(s['xb'], s['month']),
                         (s['xb'] > 0).mean() * 100, (s['xb'].mean() - BIAYA) * 100,
                         s['ls'].mean() * 100, _t_bln(s['ls'], s['month'])))
        print('beli absolut (log, rata2): P1 %+.2f%%  P2 %+.2f%%'
              % (df.loc[df['period'] == 1, 'lb'].mean() * 100, df.loc[df['period'] == 2, 'lb'].mean() * 100))
        for per, (st, ps, akt, nn) in _portofolio(df, C, M).items():
            print('portofolio kaki beli P%d: CAGR %+.1f%% (pasar rata %+.1f%%), %.0f%% hari ada posisi, rata2 %.1f posisi'
                  % (per, st * 100, ps * 100, akt * 100, nn))
        if jenis == 'koint':
            df['qz'] = pd.qcut(df['z'], 3, labels=False)
            print('per tertil |z| saat buka (beli-vs-pasar %, P1 / P2):',
                  ' '.join('%+.2f/%+.2f' % (df[(df['qz'] == q) & (df['period'] == 1)]['xb'].mean() * 100,
                                            df[(df['qz'] == q) & (df['period'] == 2)]['xb'].mean() * 100)
                           for q in range(3)))
    print('\n%.0f detik' % (time.time() - t0))


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'tunggal'
    if perintah == 'pasangan':
        cmd_pasangan(float(sys.argv[2]) if len(sys.argv) > 2 else None)
    else:
        cmd_tunggal()
