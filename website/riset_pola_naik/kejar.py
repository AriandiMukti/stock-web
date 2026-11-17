"""
"Masih layak dikejar?" -- apakah besarnya lonjakan HARI SINYAL mengubah hasil.

Kekhawatiran wajar: breakout yang hari itu sudah naik 15-25% (mendekati
ARA) mungkin sudah "habis". Diuji dengan ember yang didaftar SEBELUM hasil
dilihat, di sel yang sama dengan uji.py (pilih di A 2013-2019, uji di B
2020-2026):
    kenaikan hari sinyal : <5%  |  5-15%  |  >=15%
    kelipatan volume     : 2-4x |  4-8x   |  >=8x
    jarak ke MA50        : <10% |  10-25% |  >=25%   (sudah seberapa jauh lari)

HASIL (23 Sep 2026) -- tidak ada jawaban tegas, cuma dua indikasi:
- Puncak 52 minggu yang hari itu sudah naik >=15% (hampir ARA): vs pasar
  -0,8% per 60 hari di UJI 2020-2026 (n=243), sementara yang naik <5% dan
  5-15% +3,3% dan +4,8%. Di PILIH 2013-2019 kasusnya cuma 22 -- tidak bisa
  diuji di periode lain. Indikasi, bukan temuan.
- Tembus basis dengan volume >=8x lebih lemah di KEDUA sel (-0,8% dan +1,1%
  vs +1,8..+6,9% untuk 2-8x) -- tapi sampelnya kecil (43 dan 108).
- Volume yang lebih besar TIDAK berarti lebih baik; jarak ke MA50 tidak
  konsisten antar sel.
Kolom 'naik' dan 'vol_x' ikut tercatat di jurnal maju Tembus Basis, jadi
kedua indikasi ini bisa diperiksa ke depan tanpa mengubah apa pun.

PEMAKAIAN: python -m website.riset_pola_naik.kejar
"""
import warnings

import numpy as np
import pandas as pd

from . import uji

warnings.filterwarnings('ignore')

EMBER = {
    'naik hari sinyal': ('ret1', [(-1, 0.05, '<5%'), (0.05, 0.15, '5-15%'), (0.15, 9, '>=15%')]),
    'kelipatan volume': ('vspike', [(2, 4, '2-4x'), (4, 8, '4-8x'), (8, 1e9, '>=8x')]),
    'jarak ke MA50': ('ma50', [(-9, 0.10, '<10%'), (0.10, 0.25, '10-25%'), (0.25, 99, '>=25%')]),
}


def main():
    p = uji.muat()
    base = (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2)
    MASUK = {'puncak 52mg + vol': (p['hi250'] == 1) & (p['vspike'] > 2), 'tembus basis + vol': base}
    SEL = {'PILIH A 2013-19': (p['half'] == 0) & (p['period'] == 1),
           'UJI B 2020-26': (p['half'] == 1) & (p['period'] == 2)}
    rows = []
    for nm, m in MASUK.items():
        for ns, s in SEL.items():
            ev = uji.jeda(p[m.fillna(False) & p['elig'] & s])
            for ne, (kol, batas) in EMBER.items():
                for lo, hi, lab in batas:
                    sub = ev[(ev[kol] >= lo) & (ev[kol] < hi)]
                    st = uji.statistik(sub)
                    rows.append({'masuk': nm, 'sel': ns, 'ukuran': ne, 'ember': lab, 'n': st['n'],
                                 'lift P(+10%/20h)': round(st.get('p10', np.nan) - st.get('p10_base', np.nan), 1),
                                 'up-first': round(st.get('fpup', np.nan), 1),
                                 'exc20%': round(st.get('exc20', np.nan), 2),
                                 'exc60%': round(st.get('exc60', np.nan), 2), 't60': round(st.get('t60', np.nan), 1)})
    df = pd.DataFrame(rows).set_index(['masuk', 'ukuran', 'ember', 'sel']).sort_index(level=[0, 1])
    print(df.to_string())


if __name__ == '__main__':
    main()
