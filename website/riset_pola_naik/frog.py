"""
Frog in the pan: apakah sinyal Tembus Basis yang didahului naik MULUS lebih
baik daripada yang didahului naik MELONCAT? (18 Okt 2026)

TEORI
Da, Gurun & Warachka (2014), "Frog in the Pan: Continuous Information and
Momentum". Investor kurang bereaksi pada informasi yang datang sedikit-
sedikit (seperti katak di panci yang dipanaskan pelan), dan bereaksi
berlebihan pada lonjakan yang mencolok. Momentum yang terbentuk dari
banyak gerak kecil searah karena itu lebih awet daripada momentum yang
terbentuk dari segelintir hari besar.

Di app ini momentum (dekat puncak, tembus basis, puncak 52 minggu) adalah
satu-satunya keluarga temuan yang lolos luar sampel. Ini menguji apakah
KUALITAS momentum menambah sesuatu -- bukan mencari arah baru.

UKURAN -- DIKUNCI SEBELUM HASIL DILIHAT
  ID = tanda(PRET) x (%hari turun - %hari naik)
       dihitung dari 60 return harian close-ke-close SEBELUM hari sinyal
       (hari sinyal sendiri dikeluarkan: ia selalu hari volume >2x dan
       sering lonjakan besar, yang akan mendominasi ukurannya).
       PRET = return kumulatif jendela yang sama. Hari tanpa perubahan
       tidak dihitung naik maupun turun (sama dengan makalah aslinya).
  ID rendah (negatif) = gerak MULUS searah PRET. ID tinggi = MELONCAT.
  Rumusnya persis makalah aslinya; yang diubah cuma jendelanya (12 bulan
  di makalah -> 60 hari, mengikuti horizon tahan di app ini). Jendela
  250 hari dilaporkan sebagai pemeriksaan sekunder, BUKAN penentu.

KELOMPOK
  Batas tersil ID dihitung dari sinyal sel PILIH (emiten A 2013-19) dan
  DIPAKAI APA ADANYA di sel UJI (emiten B 2020-26) -- tidak dihitung ulang.
  mulus = tersil bawah, tengah, loncat = tersil atas.

SINYAL, KELUAR, ONGKOS
  Sinyal menu Tembus Basis (tembus basis + vol ATAU puncak 52 mgg + vol),
  satu per emiten per 20 bar, masuk close besoknya. Dua aturan masuk juga
  dilaporkan terpisah. Keluar TS10 (penentu, karena itu aturan keluar yang
  dipakai) dan H60 (pembanding). Portofolio 10 slot sama rata, ongkos
  0,9% pulang-pergi, median 10 urutan acak -- semua dari keluar.py.

KRITERIA LOLOS (ditulis sebelum hasil)
  1. Per transaksi, keluar TS10, sinyal menu: selisih vs-pasar mulus
     dikurangi loncat > 0 dengan t klaster-bulan >= 2 di sel UJI, DAN
     bertanda sama di sel PILIH.
  2. Portofolio "buang tersil loncat" tidak menurunkan CAGR median
     dibanding semua sinyal, keluar TS10, di sel UJI DAN PILIH.
  Dua-duanya harus terpenuhi. Kalau cuma (1): "ada di transaksi, tidak
  terpakai di portofolio". Kalau tidak ada: gagal.
  Hanya "buang loncat" yang diuji sebagai portofolio, bukan "cuma mulus":
  temuan lama bilang memilih-milih sinyal membunuh edge (pemenang besar
  jarang), jadi pertanyaan praktisnya adalah apa yang aman DIBUANG.

PEMAKAIAN: python -m website.riset_pola_naik.frog   (~1 menit)

HASIL (18 Okt 2026) -- GAGAL
============================
Jendela 60 hari (penentu), sinyal menu, keluar TS10:
  Kriteria 1  mulus - loncat vs pasar:  PILIH +1,17%/tx (t 0,8)
                                        UJI   +0,13%/tx (t 0,1)   -> gagal
  Kriteria 2  portofolio buang loncat:  PILIH 11,7 -> 9,9 CAGR    -> gagal
                                        UJI   30,8 -> 36,0
Arahnya juga tidak konsisten antar aturan masuk:
  - puncak 52 mgg: mulus > loncat di kedua sel (PILIH +1,3 t 0,6; UJI +2,9
    t 1,4; jendela 250 UJI +4,4 t 2,3) -- tapi tidak satu pun t >= 2 di
    jendela penentu, dan membuang loncat MERUSAK portofolio PILIH
    (12,4 -> 5,5) karena slot jadi sering kosong.
  - tembus basis: terbalik, LONCAT yang lebih baik (SEMUA 13-26: mulus -
    loncat -1,95%/tx, t -2,5 di TS10; -2,84, t -2,6 di H60).
Jendela 250 (sekunder) sama: tidak ada yang lolos untuk sinyal menu.

Membaca ini: kualitas momentum tidak menambah informasi di atas sinyal
tembus/puncak yang sudah ada. Petunjuk "puncak 52 mgg + mulus" tidak
dikejar -- itu memilih satu sub-sel setelah melihat hasil, dan sebagai
saringan ia tetap membuang modal yang menganggur.
Catatan samping: CAGR "semua" TS10 di UJI 30,8 di sini vs 27,5 di
gabungan.py untuk sinyal yang hampir sama (beda cuma sinyal tanpa ID
dibuang) -- simulasi portofolio 10 slot sensitif terhadap sinyal mana
yang kebagian slot; selisih CAGR beberapa poin bukan bukti apa-apa.
"""
import time
import warnings

import numpy as np
import pandas as pd

from . import uji
from .keluar import siapkan, transaksi, ringkas_tx, portofolio

warnings.filterwarnings('ignore')

N_SEED = 10
JENDELA = (60, 250)       # 60 = penentu, 250 = pemeriksaan sekunder


def hitung_id(ev, per, w):
    """ID frog-in-the-pan dari w return harian sebelum hari sinyal."""
    out = np.full(len(ev), np.nan)
    pret = np.full(len(ev), np.nan)
    for k, (t, h) in enumerate(zip(ev['ticker'], ev['hist'])):
        a = per[t]
        i = int(h) - a['h0']                       # baris hari sinyal
        if i - w - 1 < 0:
            continue
        c = a['close'][i - w - 1:i]                # w+1 close -> w return, berakhir kemarin
        if a['bad'][i - w:i].any():
            continue
        r = np.diff(c) / c[:-1]
        pr = c[-1] / c[0] - 1
        if pr == 0:
            continue
        out[k] = np.sign(pr) * ((r < 0).mean() - (r > 0).mean())
        pret[k] = pr
    return out, pret


def t_selisih(tx_a, tx_b):
    """Selisih rata-rata 'lebih' (a - b) dengan galat baku klaster-bulan
    (regresi pada dummy kelompok, sandwich per bulan)."""
    y = np.concatenate([tx_a['lebih'].to_numpy(), tx_b['lebih'].to_numpy()])
    d = np.concatenate([np.ones(len(tx_a)), np.zeros(len(tx_b))])
    g = np.concatenate([tx_a['bulan'].astype(str).to_numpy(), tx_b['bulan'].astype(str).to_numpy()])
    X = np.column_stack([np.ones_like(d), d])
    roti = np.linalg.inv(X.T @ X)
    beta = roti @ X.T @ y
    e = y - X @ beta
    s = pd.DataFrame(X * e[:, None]).groupby(g).sum().to_numpy()
    v = roti @ (s.T @ s) @ roti
    return (np.exp(beta[1]) - 1) * 100, beta[1] / np.sqrt(v[1, 1])


def main():
    t0 = time.time()
    p = uji.muat()
    per, pasar = siapkan(p)
    kal = pd.DatetimeIndex(sorted(p['date'].unique()))
    harga = {t: dict(zip(pd.DatetimeIndex(a['date']), a['close'])) for t, a in per.items()}
    print('siap %.0f detik' % (time.time() - t0), flush=True)

    basis = (p['brk30'] == 1) & (p['prevrange30'] < 0.20) & (p['vspike'] > 2)
    puncak = (p['hi250'] == 1) & (p['vspike'] > 2)
    MASUK = {'menu (basis ATAU puncak)': basis | puncak, 'puncak 52mg + vol': puncak, 'tembus basis + vol': basis}
    SEL = {'PILIH A 13-19': (p['half'] == 0) & (p['period'] == 1),
           'UJI B 20-26': (p['half'] == 1) & (p['period'] == 2),
           'SEMUA 13-26': p['date'] <= '2026-06-01'}

    pd.set_option('display.width', 250)
    for w in JENDELA:
        tx_rows, beda_rows, porto_rows, batas_rows = [], [], [], []
        for nm, m in MASUK.items():
            evs = {ns: uji.jeda(p[m.fillna(False) & p['elig'] & s]).copy() for ns, s in SEL.items()}
            for ev in evs.values():
                ev['ID'], ev['PRET'] = hitung_id(ev, per, w)
            pilih = evs['PILIH A 13-19']['ID'].dropna()
            b1, b2 = np.quantile(pilih, [1 / 3, 2 / 3])          # DIKUNCI dari PILIH
            batas_rows.append({'masuk': nm, 'batas mulus <': round(b1, 3), 'batas loncat >': round(b2, 3),
                               'ID median PILIH': round(float(pilih.median()), 3),
                               'PRET>0 %': round((evs['PILIH A 13-19']['PRET'] > 0).mean() * 100, 1)})
            for ns, ev in evs.items():
                ev = ev[ev['ID'].notna()]
                grup = {'mulus': ev[ev['ID'] < b1], 'tengah': ev[(ev['ID'] >= b1) & (ev['ID'] <= b2)],
                        'loncat': ev[ev['ID'] > b2], 'semua': ev, 'buang loncat': ev[ev['ID'] <= b2]}
                for ak in ('TS10', 'H60'):
                    txs = {gn: transaksi(ge, per, pasar, ak) for gn, ge in grup.items()}
                    for gn in ('mulus', 'tengah', 'loncat', 'semua'):
                        r = {'masuk': nm, 'sel': ns, 'keluar': ak, 'kelompok': gn}
                        r.update(ringkas_tx(txs[gn]))
                        tx_rows.append(r)
                    if len(txs['mulus']) >= 30 and len(txs['loncat']) >= 30:
                        sel, t = t_selisih(txs['mulus'], txs['loncat'])
                        beda_rows.append({'masuk': nm, 'sel': ns, 'keluar': ak,
                                          'n mulus': len(txs['mulus']), 'n loncat': len(txs['loncat']),
                                          'mulus - loncat vs pasar %/tx': round(sel, 2), 't klaster': round(t, 1)})
                    for gn in ('semua', 'buang loncat'):
                        hs = [portofolio(txs[gn], kal, harga, seed=sd) for sd in range(N_SEED)]
                        hs = [h for h in hs if h]
                        if not hs:
                            continue
                        porto_rows.append({'masuk': nm, 'sel': ns, 'keluar': ak, 'sinyal': gn,
                                           'transaksi': int(np.median([h['transaksi'] for h in hs])),
                                           'CAGR': round(float(np.median([h['CAGR%'] for h in hs])), 1),
                                           'CAGR min..max': '%.1f..%.1f' % (min(h['CAGR%'] for h in hs),
                                                                            max(h['CAGR%'] for h in hs)),
                                           'DD': round(float(np.median([h['maxDD%'] for h in hs])), 1)})
            print('.. jendela %d | %s  %.0f detik' % (w, nm, time.time() - t0), flush=True)

        judul = 'JENDELA %d HARI%s' % (w, ' (PENENTU)' if w == 60 else ' (SEKUNDER, bukan penentu)')
        print('\n' + '#' * 100 + '\n' + judul + '\n' + '#' * 100)
        print('\nBatas tersil (dari PILIH, dipakai apa adanya di sel lain)')
        print(pd.DataFrame(batas_rows).set_index('masuk').to_string())
        print('\nSELISIH mulus - loncat (kriteria 1)')
        print(pd.DataFrame(beda_rows).set_index(['masuk', 'sel', 'keluar']).to_string())
        print('\nPORTOFOLIO median 10 urutan acak (kriteria 2)')
        print(pd.DataFrame(porto_rows).set_index(['masuk', 'sel', 'keluar', 'sinyal']).to_string())
        print('\nPER TRANSAKSI per kelompok')
        print(pd.DataFrame(tx_rows).set_index(['masuk', 'sel', 'keluar', 'kelompok']).to_string())


if __name__ == '__main__':
    main()
