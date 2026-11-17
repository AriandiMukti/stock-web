"""
Uji klaim "volume mengonfirmasi harga":

  H1  Harga turun dalam W hari TAPI volumenya ikut turun -> "bukan
      penurunan asli", jadi ke depan mestinya lebih baik (atau kurang
      buruk) daripada turun dengan volume naik.
  H2  Harga naik TANPA kenaikan volume -> "naik palsu", jadi ke depan
      mestinya lebih buruk daripada naik dengan volume naik.

Cara:
  r_past = C[t] / C[t-W] - 1
  vr     = rata2 volume W hari terakhir / rata2 volume W hari sebelumnya
  turun  : r_past <= -BATAS[W]      naik : r_past >= +BATAS[W]
  vol turun: vr < 0.8   datar: 0.8-1.25   vol naik: vr > 1.25
  Hasil  : masuk CLOSE t+1 (lihat panel.py), keluar H hari kemudian,
           dikurangi rata-rata semua emiten layak di tanggal yang sama
           (excess) supaya arah pasar tidak ikut terhitung.
  Sampel : satu titik tiap W hari per emiten, supaya jendela tidak tumpang
           tindih dan satu kejadian tidak dihitung berkali-kali.
  Layak  : nilai transaksi rata2 20 hari >= Rp1 miliar, harga >= 50.

Validasi: periode (2013-2019 vs 2020-2026) DAN semesta (emiten dibelah
dua lewat hash kode). Uji beda pakai t-stat atas selisih BULANAN, bukan
per baris, karena baris di bulan yang sama saling berkorelasi.
"""
import sys
import zlib

import numpy as np
import pandas as pd

from panel import sumber_harga, LONCAT

BATAS = {10: 0.07, 20: 0.10}
HORIZON = (10, 20, 40)
VR_LO, VR_HI = 0.8, 1.25


def bangun(data):
    rows = []
    for t, df in data.items():
        df = df[['Close', 'Volume']].copy()
        df = df[df['Close'] > 0].sort_index()
        df = df[~df.index.duplicated(keep='last')]
        if len(df) < 200:
            continue
        C, V = df['Close'], df['Volume'].fillna(0)
        ret1 = C.pct_change().abs()
        rusak = (ret1 > LONCAT).astype(float)
        nilai20 = (C * V).rolling(20).mean()
        out = {'date': df.index, 'ticker': t, 'nilai20': nilai20.values,
               'close': C.values}
        for W in BATAS:
            vmean = V.rolling(W).mean()
            out['r%d' % W] = (C / C.shift(W) - 1).values
            out['vr%d' % W] = (vmean / vmean.shift(W)).values
            out['rusak%d' % W] = rusak.rolling(2 * W).max().values
        masuk = C.shift(-1)
        for H in HORIZON:
            f = C.shift(-1 - H) / masuk - 1
            rusak_f = rusak[::-1].rolling(H + 1).max()[::-1].shift(-1)
            out['f%d' % H] = f.where(rusak_f == 0).values
        p = pd.DataFrame(out)
        p['i'] = np.arange(len(p))
        rows.append(p)
    return pd.concat(rows, ignore_index=True)


def excess(panel):
    ok = (panel['nilai20'] >= 1e9) & (panel['close'] >= 50)
    p = panel[ok].copy()
    for H in HORIZON:
        p['x%d' % H] = p['f%d' % H] - p.groupby('date')['f%d' % H].transform('mean')
    return p


def label(p, W):
    q = p[(p['i'] % W == 0) & (p['rusak%d' % W] == 0)].copy()
    r, vr = q['r%d' % W], q['vr%d' % W]
    q['arah'] = np.select([r <= -BATAS[W], r >= BATAS[W]], ['turun', 'naik'], 'lain')
    q['vol'] = np.select([vr < VR_LO, vr > VR_HI], ['vol_turun', 'vol_naik'], 'vol_datar')
    q['periode'] = np.where(q['date'].dt.year <= 2019, 'IS 2013-19', 'OOS 2020-26')
    q['semesta'] = np.where(q['ticker'].map(lambda s: zlib.crc32(s.encode()) % 2), 'B', 'A')
    q['bulan'] = q['date'].dt.to_period('M')
    return q[q['arah'] != 'lain']


def beda_bulanan(q, arah, H):
    """t-stat selisih (vol_turun - vol_naik) dihitung per bulan."""
    s = q[q['arah'] == arah]
    m = s.groupby(['bulan', 'vol'])['x%d' % H].mean().unstack()
    if 'vol_turun' not in m or 'vol_naik' not in m:
        return np.nan, np.nan, 0
    d = (m['vol_turun'] - m['vol_naik']).dropna()
    if len(d) < 6:
        return np.nan, np.nan, len(d)
    return d.mean(), d.mean() / (d.std(ddof=1) / np.sqrt(len(d))), len(d)


def ringkas(q, H):
    g = q.groupby(['arah', 'vol'])['x%d' % H]
    return pd.DataFrame({'n': g.count(), 'rata2%': g.mean() * 100,
                         'median%': g.median() * 100,
                         'menang%': g.apply(lambda s: (s > 0).mean() * 100)}).round(2)


def main():
    path, data = sumber_harga()
    print('sumber:', path, len(data), 'emiten')
    p = excess(bangun(data))
    p = p[p['date'].dt.year >= 2013]
    for W in BATAS:
        q = label(p, W)
        print('\n' + '=' * 78)
        print('W = %d hari, batas gerak +/-%d%%' % (W, BATAS[W] * 100))
        for H in HORIZON:
            q2 = q.dropna(subset=['x%d' % H])
            print('\n--- horizon %d hari (excess vs rata2 pasar) ---' % H)
            print(ringkas(q2, H).to_string())
            print('selisih vol_turun - vol_naik, rata2 bulanan (pp) [t, bulan]:')
            for arah, harapan in (('turun', '>0'), ('naik', '<0')):
                bag = []
                for kol, nilai in (('periode', 'IS 2013-19'), ('periode', 'OOS 2020-26'),
                                   ('semesta', 'A'), ('semesta', 'B')):
                    d, tt, nb = beda_bulanan(q2[q2[kol] == nilai], arah, H)
                    bag.append('%s %+.2f [t=%+.1f, %d]' % (nilai, d * 100, tt, nb))
                print('  %-5s (klaim %s): %s' % (arah, harapan, ' | '.join(bag)))


if __name__ == '__main__':
    sys.exit(main())
