"""
Kenapa Jatuh Dalam dulu "lolos luar sampel" tapi kalah di semesta luas.

Aturannya sama persis (jatuh >40% dari puncak 60 hari + rentang 20 hari
>=25%), cara ujinya juga meniru uji lama: close H -> close H+20, tanpa jeda,
2016-2025, dibanding rata-rata semua hari. Yang diganti cuma SEMESTANYA.

Hasil 23 Sep 2026:
    20 emiten folder Test      +14,58pp  (replikasi angka lama: cocok)
    semua emiten likuid         -0,27pp vs semua hari, -1,56pp vs pasar hari yang sama,
                                majemuk -2,99%, median -2,86%

20 emiten itu dipilih tahun 2026 karena besar HARI INI -- kejatuhan lama
mereka, menurut definisinya, diikuti pemulihan. Bias hindsight.

PEMAKAIAN: python -m website.riset_pola_naik.cek_jatuh_dalam
"""
import numpy as np
import pandas as pd

from . import uji

# Folder New BDM\Test (sama dengan rl_trading.TEST21, semesta luar sampel lama).
TEST21 = ['ADRO', 'ANTM', 'BBCA', 'BBRI', 'BREN', 'BRMS', 'BRPT', 'BUMI', 'CDIA', 'CUAN', 'HRUM',
          'INDY', 'INKP', 'INTP', 'ISAT', 'PSAB', 'PTBA', 'PTRO', 'TINS', 'TPIA']


def main():
    p = uji.muat()
    g = p.groupby('ticker', sort=False)['close']
    p['fwd20_t0'] = g.shift(-20) / p['close'] - 1
    p['bad_fwd'] = p.groupby('ticker', sort=False)['bad_back60'].shift(-20)
    p['ok'] = (p['hist'] >= 260) & p['fwd20_t0'].notna() & (p['bad_back60'] == 0) & (p['bad_fwd'] == 0)
    tahun = (p['date'] >= '2016-01-01') & (p['date'] <= '2025-12-31')
    jd = (p['dd60'] <= -0.40) & (p['range20'] >= 0.25)
    pasar = p[p['ok']].groupby('date')['fwd20_t0'].mean().rename('mkt_ar')
    p = p.merge(pasar, left_on='date', right_index=True, how='left')

    def baris(nama, semesta):
        b = p[semesta & p['ok']]
        s = p[semesta & jd & p['ok']]
        return {
            'semesta': nama, 'hari': len(b), 'hari sinyal': len(s),
            'bulan sinyal': s['date'].dt.to_period('M').nunique(),
            'rata2 semua hari %': round(b['fwd20_t0'].mean() * 100, 2),
            'rata2 sinyal %': round(s['fwd20_t0'].mean() * 100, 2),
            'vs semua hari pp (cara lama)': round((s['fwd20_t0'].mean() - b['fwd20_t0'].mean()) * 100, 2),
            'vs pasar hari sama pp': round((s['fwd20_t0'] - s['mkt_ar']).mean() * 100, 2),
            'majemuk sinyal %': round((np.exp(np.log1p(s['fwd20_t0']).mean()) - 1) * 100, 2),
            'median sinyal %': round(s['fwd20_t0'].median() * 100, 2),
            'porsi di 2020 %': round((s['date'].dt.year == 2020).mean() * 100, 1),
        }

    out = [baris('TEST21 (semesta luar sampel lama)', p['ticker'].isin(TEST21) & tahun),
           baris('TEST21 tanpa 2020', p['ticker'].isin(TEST21) & tahun & (p['date'].dt.year != 2020)),
           baris('Semua emiten, likuid (>=Rp1 M/hari)', tahun & (p['medval20'] >= 1e9) & (p['close'] >= 100)),
           baris('Semua emiten, likuiditas apa pun', tahun)]
    print(pd.DataFrame(out).set_index('semesta').T.to_string())


if __name__ == '__main__':
    main()
