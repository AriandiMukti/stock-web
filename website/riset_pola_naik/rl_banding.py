"""
RL Trading: apakah fitur tambahan yang SUDAH lolos uji di modul lain
(kabar semalam + tembus basis/52w high + support chart) membuat agen
rl_trading.py lebih baik di luar sampel?

DESAIN (didaftar SEBELUM hasil dilihat, 18 Okt 2026)
Dua lengan, semua sama kecuali fitur:
    dasar   20 fitur harga/volume/IHSG (versi lama, arus broker mati)
    plus    dasar + grup 'lintas' + grup 'sinyal' (29 fitur)
Grup 'insider' TIDAK ikut: datanya baru ada sejak April 2026, jadi nol di
~95% sejarah dan cuma hidup di fold terakhir -- tidak bisa diuji di sini.

Semesta 'semua' dipangkas ke 150 paling likuid (default modul), mulai 2012,
latih 5 tahun, uji 1 tahun -> fold uji 2017..2026. 5 seed (7, 108, 209, 310,
411), 4 rollout evaluasi per seed, hiperparameter PPO default. Seed sama ->
urutan episode latihan & sampel emiten sama di dua lengan; yang beda cuma
inisialisasi lapis pertama jaringan (dimensi masuknya beda).

Ukuran utama: return MAJEMUK seluruh fold per seed (rantai 10 tahun uji),
dibandingkan berpasangan per seed. Rata-rata aritmetik per fold cuma
pelengkap.
Vonis "plus menambah" HANYA kalau ketiganya terpenuhi:
    1. median selisih majemuk berpasangan > 0
    2. >= 4 dari 5 seed: plus > dasar (majemuk)
    3. plus > dasar di >= 6 dari 10 fold (rata-rata antar seed)
Selain itu: "tidak terbukti menambah".

Catatan jujur: pemangkasan ke 150 emiten likuid memakai peringkat seluruh
periode (kebocoran ringan tingkat semesta, sama di dua lengan), dan daftar
emiten adalah daftar hari ini (survivorship, sama di dua lengan). Keduanya
menggeser level, bukan selisih antar lengan.

PEMAKAIAN (dari <project>/):
    python -m website.riset_pola_naik.rl_banding siapkan      # unduh & cache data
    python -m website.riset_pola_naik.rl_banding jalan dasar
    python -m website.riset_pola_naik.rl_banding jalan plus   # boleh paralel
    python -m website.riset_pola_naik.rl_banding laporan
"""
import json
import os
import sys
import time

import numpy as np

from .. import rl_trading as R

KELUAR = os.path.join(R.CACHE_DIR, 'rl_banding')

DASAR = {
    'universe': 'semua', 'maks_emiten': 150, 'mulai_tahun': 2012,
    'latih_tahun': 5, 'uji_tahun': 1, 'n_seed': 5, 'n_eval': 4, 'seed': 7,
}
LENGAN = {
    'dasar': {},
    'plus': {'pakai_lintas': True, 'pakai_sinyal': True},
}


class Kanal:
    def __init__(self, berkas):
        self.t0 = time.time()
        self.f = open(berkas, 'a', encoding='utf-8')

    def log(self, pesan, level='info'):
        baris = '%7.0fs [%s] %s' % (time.time() - self.t0, level, pesan)
        print(baris, flush=True)
        self.f.write(baris + '\n')
        self.f.flush()

    def tahap(self, nama):
        self.log('== ' + nama)

    def maju(self, x):
        pass

    def berhenti(self):
        return False


def cfg_lengan(nama):
    c = dict(DASAR)
    c.update(LENGAN[nama])
    return c


def siapkan():
    os.makedirs(KELUAR, exist_ok=True)
    k = Kanal(os.path.join(KELUAR, 'siapkan.log'))
    R.bangun_panel(R._normalkan(cfg_lengan('plus')), k)


def jalan(nama):
    os.makedirs(KELUAR, exist_ok=True)
    k = Kanal(os.path.join(KELUAR, '%s.log' % nama))
    t0 = time.time()
    hasil = R.jalankan_rl(cfg_lengan(nama), k)
    simpan = {
        'lengan': nama, 'config': hasil['config'], 'ringkas': hasil['ringkas'],
        'vonis': hasil['vonis'], 'folds': hasil['folds'],
        'n_emiten': len(hasil['universe']), 'detik': round(time.time() - t0),
        'selesai': time.strftime('%Y-%m-%d %H:%M'),
    }
    with open(os.path.join(KELUAR, '%s.json' % nama), 'w', encoding='utf-8') as f:
        json.dump(simpan, f, indent=1, default=str)
    k.log('Tersimpan %s.json (%.0f menit).' % (nama, (time.time() - t0) / 60), 'ok')


def _muat(nama):
    with open(os.path.join(KELUAR, '%s.json' % nama), encoding='utf-8') as f:
        return json.load(f)


def _majemuk(rets_pct):
    return (np.prod(1 + np.asarray(rets_pct) / 100.0) - 1) * 100


def _beli_tahan_ulang(tahun):
    """Beli-tahan dihitung ulang dengan rl_trading.beli_tahan yang sudah
    diperbaiki (run 18 Okt masih memakai versi yang mencatat 0% kalau hari
    pertama fold adalah baris libur). Agen tidak terpengaruh."""
    berkas = os.path.join(KELUAR, 'beli_tahan.json')
    if os.path.exists(berkas):
        with open(berkas, encoding='utf-8') as f:
            return {int(k): v for k, v in json.load(f).items()}
    cfg = R._normalkan(cfg_lengan('dasar'))
    panel = R.bangun_panel(cfg, Kanal(os.path.join(KELUAR, 'laporan.log')))
    th = np.array([d.year for d in panel['indeks']])
    out = {}
    for y in tahun:
        a, b = int(np.searchsorted(th, y)), int(np.searchsorted(th, y + 1))
        out[y] = R.metrik(R.beli_tahan(panel, cfg, a, b), cfg['modal'])['return_pct']
    with open(berkas, 'w', encoding='utf-8') as f:
        json.dump(out, f)
    return out


def laporan():
    a, b = _muat('dasar'), _muat('plus')
    fa = {f['tahun']: f for f in a['folds']}
    fb = {f['tahun']: f for f in b['folds']}
    tahun = sorted(set(fa) & set(fb))
    bt = _beli_tahan_ulang(tahun)
    for y in tahun:
        fa[y]['beli_tahan'] = bt[y]
    S = min(len(fa[tahun[0]]['agen_per_seed']), len(fb[tahun[0]]['agen_per_seed']))

    print('Fold  |  dasar   plus   selisih  seed plus>dasar |  beli-tahan  acak')
    menang_fold = 0
    for y in tahun:
        ra, rb = np.array(fa[y]['agen_per_seed'][:S]), np.array(fb[y]['agen_per_seed'][:S])
        d = rb.mean() - ra.mean()
        menang_fold += d > 0
        print('%d  | %+6.1f  %+6.1f  %+6.1f      %d/%d          |  %+6.1f    %+6.1f'
              % (y, ra.mean(), rb.mean(), d, int((rb > ra).sum()), S,
                 fa[y]['beli_tahan'], fa[y]['acak']))

    ma = np.array([_majemuk([fa[y]['agen_per_seed'][s] for y in tahun]) for s in range(S)])
    mb = np.array([_majemuk([fb[y]['agen_per_seed'][s] for y in tahun]) for s in range(S)])
    th = len(tahun)
    cagr = lambda m: ((1 + m / 100) ** (1 / th) - 1) * 100
    bh = _majemuk([fa[y]['beli_tahan'] for y in tahun])
    acak = _majemuk([fa[y]['acak'] for y in tahun])
    selisih = mb - ma

    print()
    print('Majemuk %d fold (%d-%d), per seed:' % (th, tahun[0], tahun[-1]))
    for s in range(S):
        print('  seed %d: dasar %+7.1f%% (CAGR %+5.1f) | plus %+7.1f%% (CAGR %+5.1f) | selisih %+7.1f pp'
              % (s, ma[s], cagr(ma[s]), mb[s], cagr(mb[s]), selisih[s]))
    print('  median: dasar %+.1f%% (CAGR %+.1f) | plus %+.1f%% (CAGR %+.1f) | selisih %+.1f pp'
          % (np.median(ma), cagr(np.median(ma)), np.median(mb), cagr(np.median(mb)),
             np.median(selisih)))
    print('  beli-tahan %+.1f%% (CAGR %+.1f) | acak %+.1f%% (CAGR %+.1f)'
          % (bh, cagr(bh), acak, cagr(acak)))
    for nm, h in (('dasar', a), ('plus', b)):
        r = h['ringkas']
        print('  %-5s: %d transaksi/jalur, win %.1f%%, rata %.2f%%/trade, eksposur %.0f%%, '
              'DD maks rata2 %.1f%%, vonis modul "%s"'
              % (nm, r['n_trade'], r['win_rate'], r['rata_trade'], r['eksposur'],
                 r['maks_dd'], h['vonis']))

    k1 = np.median(selisih) > 0
    k2 = int((selisih > 0).sum()) >= 4
    k3 = menang_fold >= 6
    print()
    print('Kriteria: median selisih > 0: %s | seed plus>dasar %d/%d (>=4): %s | '
          'fold menang %d/%d (>=6): %s'
          % (k1, int((selisih > 0).sum()), S, k2, menang_fold, th, k3))
    print('VONIS: %s' % ('plus MENAMBAH' if (k1 and k2 and k3) else 'tidak terbukti menambah'))


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else 'laporan'
    if perintah == 'siapkan':
        siapkan()
    elif perintah == 'jalan':
        jalan(sys.argv[2])
    else:
        laporan()
