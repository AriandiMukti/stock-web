"""
Populasi agen twin dan cara tiap persona mengambil keputusan.

APA YANG DISINTESIS DI SINI (datanya memang tidak ada)
Data broker berhenti di tingkat BROKER: "XL net beli 12 ribu lot". Di balik
satu kode itu ada ribuan nasabah yang tidak terlihat. Maka satu agen twin
adalah satu GUGUS investor dengan watak yang sama, bukan satu orang --
modalnya, ambang untung/ruginya, kepekaannya pada berita dan keramaian
diacak dari rentang di PERSONA di bawah. Yang dikalibrasi dari data adalah
BESAR-nya: porsi kepemilikan awal (KSEI), porsi aktivitas tiap kelompok
(nilai bruto JSON), dan ukuran ordernya. Yang TIDAK dikalibrasi dari data
adalah watak di dalam rentang itu -- itulah sebabnya validasi.py menguji
apakah perilaku yang muncul (ritel melawan arah harga, asing searah, ekor
gemuk, gejolak yang mengumpul) cocok dengan pasar asli, bukan menganggapnya
benar.

SATU RUMUS KEPUTUSAN UNTUK SEMUA PERSONA BIASA
Ritel, institusi, dan asing memakai fungsi yang sama dengan bobot berbeda:

    x = w_mom*tren + w_gap*celah_nilai + w_sent*sentimen_saham
      + w_herd*kerumunan + w_makro*sinyal_makro_kelompoknya
      - w_tp*[untung >= tp] - w_cl*[rugi >= cl] - w_panik*[hampir ARB]
      + derau

    x >  ambang -> beli,   x < -ambang -> jual (kalau punya barang)

Bedanya cuma bobot: ritel_tren mengejar tren (w_mom > 0), ritel_kontra
menampung yang jatuh (w_mom < 0), ritel_ikut mengikuti kerumunan dan
paling cepat panik, institusi berjangkar pada nilai wajar, asing pada
nilai wajar + selera risiko global + tren IHSG. Bandar, pedagang cepat
(penyedia likuiditas), dan penjual pasokan punya logika sendiri.

SINKRON ANTARA BASELINE DAN SKENARIO
Semua angka acak per tick diambil dengan UKURAN TETAP (N agen) apa pun
keadaannya. Dengan begitu dua dunia dengan seed sama memakai urutan angka
acak yang identik, dan selisih keduanya murni akibat skenario.
"""
import numpy as np

from . import aturan

TIPE = ('ritel_tren', 'ritel_kontra', 'ritel_ikut', 'institusi', 'asing',
        'bandar', 'cepat', 'penjual')
T = {n: i for i, n in enumerate(TIPE)}
GRUP = ('ritel', 'institusi', 'asing', 'bandar', 'cepat', 'penjual')
G = {n: i for i, n in enumerate(GRUP)}
GRUP_DARI_TIPE = np.array([0, 0, 0, 1, 2, 3, 4, 5], dtype=np.int64)
TIPE_UMUM = (T['ritel_tren'], T['ritel_kontra'], T['ritel_ikut'], T['institusi'], T['asing'])

LABEL_TIPE = {
    'ritel_tren': 'Ritel pengejar tren (FOMO)',
    'ritel_kontra': 'Ritel penampung (beli saat turun)',
    'ritel_ikut': 'Ritel ikut-ikutan / mudah panik',
    'institusi': 'Institusi lokal',
    'asing': 'Asing',
    'bandar': 'Bandar',
    'cepat': 'Pedagang cepat (penyedia likuiditas)',
    'penjual': 'Pemegang pasokan baru',
}

# Rentang watak per persona -- tiap agen mendapat nilai acak seragam di
# dalamnya. tp/cl 9 = tidak pernah (institusi & asing tidak memakai
# take-profit/cut-loss persen tetap).
PERSONA = {
    # Derau besar dan aktivitas sering: satu agen ritel adalah GUGUS ribuan
    # nasabah yang dalam sehari membeli DAN menjual. Data JSON broker: arus
    # ritel harian hanya 4-28% searah (|netto|/bruto) -- jauh dari "semua
    # ritel bergerak bersama". Wataknya ada di KECONDONGAN, bukan di arah
    # bulat. Besar derau disetel ulang oleh kalibrasi mikro.
    'ritel_tren': dict(
        aktif=(0.12, 0.25), w_mom=(0.9, 1.7), w_gap=(0.0, 0.0), w_sent=(0.4, 0.9),
        w_herd=(0.1, 0.4), w_makro=(0.2, 0.4), ambang=(0.5, 0.65), derau=(1.0, 1.4),
        tp=(0.08, 0.25), w_tp=(0.6, 1.0), cl=(0.05, 0.10), w_cl=(1.3, 2.0),
        w_panik=(0.3, 0.8), agresif=(0.15, 0.35), buzz=(0.8, 1.4), kas=(0.25, 0.45),
        w_disp=(0.2, 0.5), w_prog=(0.0, 0.0)),
    'ritel_kontra': dict(
        aktif=(0.12, 0.25), w_mom=(-1.8, -1.0), w_gap=(0.0, 0.3), w_sent=(0.1, 0.3),
        w_herd=(-0.4, -0.1), w_makro=(0.0, 0.15), ambang=(0.45, 0.6), derau=(1.0, 1.4),
        tp=(0.03, 0.08), w_tp=(0.8, 1.3), cl=(0.20, 0.35), w_cl=(0.8, 1.2),
        w_panik=(0.0, 0.2), agresif=(0.03, 0.12), buzz=(0.3, 0.8), kas=(0.3, 0.5),
        w_disp=(0.5, 0.9), w_prog=(0.0, 0.0)),
    'ritel_ikut': dict(
        aktif=(0.10, 0.22), w_mom=(0.0, 0.4), w_gap=(0.0, 0.0), w_sent=(0.6, 1.0),
        w_herd=(0.3, 0.6), w_makro=(0.3, 0.6), ambang=(0.55, 0.7), derau=(1.1, 1.5),
        tp=(0.05, 0.15), w_tp=(0.5, 1.0), cl=(0.07, 0.15), w_cl=(1.5, 2.5),
        w_panik=(1.0, 2.0), agresif=(0.10, 0.25), buzz=(0.8, 1.4), kas=(0.2, 0.4),
        w_disp=(0.3, 0.6), w_prog=(0.0, 0.0)),
    # Institusi lokal: berjangkar nilai tapi dengan tafsir yang lebih
    # beragam, sedikit melawan arah (data: arus lokal vs return 5 hari
    # sebelumnya -0,07 s/d -0,13), pasif.
    'institusi': dict(
        aktif=(0.30, 0.50), w_mom=(-0.15, 0.15), w_gap=(0.4, 0.9), w_sent=(0.0, 0.15),
        w_herd=(0.0, 0.0), w_makro=(0.3, 0.7), ambang=(0.3, 0.45), derau=(0.8, 1.1),
        tp=(9, 9), w_tp=(0, 0), cl=(9, 9), w_cl=(0, 0),
        w_panik=(0, 0), agresif=(0.1, 0.2), buzz=(0.0, 0.1), kas=(0.08, 0.15),
        w_disp=(0.0, 0.0), w_prog=(0.2, 0.5)),
    # Asing: pemain informasi -- paling dekat ke nilai wajar, mengeksekusi
    # pelan beberapa hari (arusnya searah return hari itu DAN 5 hari
    # sebelumnya di data asli: +0,5 dan +0,2..+0,35).
    'asing': dict(
        aktif=(0.30, 0.50), w_mom=(0.0, 0.3), w_gap=(1.5, 2.5), w_sent=(0.0, 0.1),
        w_herd=(0.0, 0.0), w_makro=(0.8, 1.4), ambang=(0.3, 0.45), derau=(0.7, 1.0),
        tp=(9, 9), w_tp=(0, 0), cl=(9, 9), w_cl=(0, 0),
        w_panik=(0, 0), agresif=(0.35, 0.55), buzz=(0.0, 0.1), kas=(0.08, 0.15),
        w_disp=(0.0, 0.0), w_prog=(0.6, 1.1)),
}
PARAM = ('aktif', 'w_mom', 'w_gap', 'w_sent', 'w_herd', 'w_makro', 'ambang', 'derau',
         'tp', 'w_tp', 'cl', 'w_cl', 'w_panik', 'agresif', 'buzz', 'kas', 'w_disp', 'w_prog')

# Komposisi bawaan jumlah agen (porsi dari n_agen). Porsi tiga watak ritel
# digeser oleh data (lihat bangun_populasi).
KOMPOSISI = {'ritel': 0.75, 'institusi': 0.10, 'asing': 0.08, 'cepat': 0.07}
RITEL_DASAR = {'ritel_tren': 0.22, 'ritel_kontra': 0.48, 'ritel_ikut': 0.30}

# Bandar otomatis hanya di saham berkapitalisasi di bawah ini (Rp). Di
# big cap, broker lokal yang "kompak" di data ternyata Bahana/DX dkk. --
# institusi yang mengeksekusi dana pensiun, bukan bandar.
MCAP_BANDAR = 30e12


class Populasi:
    """Wadah array per agen. Sengaja bukan objek per agen: 5.000 agen x
    ratusan tick harus dihitung sekaligus dengan numpy."""

    def __init__(self, n, n_saham):
        self.n = n
        self.tipe = np.zeros(n, dtype=np.int64)
        self.grup = np.zeros(n, dtype=np.int64)
        self.kas = np.zeros(n)
        self.pos = np.zeros((n, n_saham), dtype=np.int64)
        self.biaya = np.zeros((n, n_saham))       # total rupiah modal posisi
        self.perhatian = np.zeros((n, n_saham))   # bobot perhatian dasar (baris dinormalisasi)
        self.skala = np.ones(n)                   # pengali ukuran order individual
        self.nu = np.zeros((n, n_saham))          # beda tafsir nilai wajar per agen-saham
        self.aktif_slot = np.ones(n, dtype=bool)  # slot cadangan (bandar/penjual skenario) = False
        for p in PARAM:
            setattr(self, p, np.zeros(n))


def _isi_parameter(pop, idx, nama, rng):
    rentang = PERSONA[nama]
    for p in PARAM:
        lo, hi = rentang[p]
        getattr(pop, p)[idx] = lo + (hi - lo) * rng.random(len(idx)) if hi > lo else lo


def _bagi_lot(total, bobot):
    """Bagi `total` lot (int) ke agen menurut bobot, integer, sum tepat."""
    bobot = np.asarray(bobot, dtype=float)
    if total <= 0 or bobot.sum() <= 0:
        return np.zeros(len(bobot), dtype=np.int64)
    raw = bobot / bobot.sum() * total
    dasar = np.floor(raw).astype(np.int64)
    kurang = int(total - dasar.sum())
    if kurang > 0:
        urut = np.argsort(-(raw - dasar), kind='stable')[:kurang]
        dasar[urut] += 1
    return dasar


def porsi_aktivitas(ps):
    """Porsi nilai bruto ritel/asing/lokal satu saham; bawaan menurut
    ukuran kalau JSON tidak ada."""
    b = ps.get('bruto')
    if b and b.get('porsi'):
        return dict(b['porsi'])
    mcap = (ps.get('pemilik') or {}).get('mcap') or 0
    if mcap >= 100e12:
        return {'ritel': 0.30, 'asing': 0.55, 'lokal': 0.15}
    if mcap >= 20e12:
        return {'ritel': 0.45, 'asing': 0.30, 'lokal': 0.25}
    return {'ritel': 0.60, 'asing': 0.15, 'lokal': 0.25}


def porsi_pemilik(ps):
    pm = ps.get('pemilik')
    if pm:
        return dict(pm['porsi_pemilik']), float(pm['beredar_lot'])
    # tanpa KSEI: float = 150 hari volume rata-rata, komposisi dari aktivitas
    akt = porsi_aktivitas(ps)
    return ({'ritel': akt['ritel'], 'asing': akt['asing'], 'institusi': akt['lokal']},
            150.0 * ps['adv_lot'])


def bangun_populasi(prof, kodes, cfg, rng, n_cadangan=0):
    """
    Bangun populasi + rencana bandar. Return (pop, info).

    cfg: n_agen, komposisi (opsional, dict porsi), bandar ('otomatis' /
    'tidak' / 'semua'), dan kal (pengali hasil kalibrasi mikro).
    """
    S = len(kodes)
    saham = [prof['saham'][k] for k in kodes]
    n_agen = int(cfg.get('n_agen', 2000))
    komp = dict(KOMPOSISI)
    komp.update(cfg.get('komposisi') or {})
    tot = sum(komp.values())
    komp = {k: v / tot for k, v in komp.items()}

    # -- watak ritel digeser data: korelasi arus ritel dengan return 5 hari
    #    sebelumnya. Negatif (ritel menampung) -> lebih banyak ritel_kontra.
    kor = [((prof.get('perilaku') or {}).get(k) or {}).get('korelasi', {}).get('ritel', {}).get('tren_5h_lalu')
           for k in kodes]
    kor = [c for c in kor if c is not None]
    geser = float(np.clip(np.mean(kor), -0.4, 0.4)) if kor else 0.0
    ritel_porsi = {'ritel_tren': RITEL_DASAR['ritel_tren'] + 0.5 * geser,
                   'ritel_kontra': RITEL_DASAR['ritel_kontra'] - 0.5 * geser,
                   'ritel_ikut': RITEL_DASAR['ritel_ikut']}

    jumlah = {
        'ritel_tren': int(round(n_agen * komp['ritel'] * ritel_porsi['ritel_tren'])),
        'ritel_kontra': int(round(n_agen * komp['ritel'] * ritel_porsi['ritel_kontra'])),
        'ritel_ikut': int(round(n_agen * komp['ritel'] * ritel_porsi['ritel_ikut'])),
        'institusi': max(S, int(round(n_agen * komp['institusi']))),
        'asing': max(S, int(round(n_agen * komp['asing']))),
        'cepat': max(2 * S, int(round(n_agen * komp['cepat']))),
    }

    # -- bandar otomatis
    mode_bandar = cfg.get('bandar', 'otomatis')
    saham_bandar = []
    for j, ps in enumerate(saham):
        mcap = (ps.get('pemilik') or {}).get('mcap') or 0
        if mode_bandar == 'semua' or (mode_bandar == 'otomatis' and 0 < mcap < MCAP_BANDAR):
            saham_bandar.append(j)
    jumlah['bandar'] = len(saham_bandar)

    n = sum(jumlah.values()) + n_cadangan
    pop = Populasi(n, S)
    urutan = ['ritel_tren', 'ritel_kontra', 'ritel_ikut', 'institusi', 'asing', 'cepat', 'bandar']
    awal = 0
    indeks = {}
    for nama in urutan:
        idx = np.arange(awal, awal + jumlah[nama])
        awal += jumlah[nama]
        indeks[nama] = idx
        pop.tipe[idx] = T[nama]
        if nama in PERSONA:
            _isi_parameter(pop, idx, nama, rng)
    cad = np.arange(awal, n)
    pop.tipe[cad] = T['penjual']
    pop.aktif_slot[cad] = False
    pop.grup[:] = GRUP_DARI_TIPE[pop.tipe]
    pop.skala[:] = np.exp(0.5 * rng.standard_normal(n))

    # -- porsi aktivitas & pemilik per saham
    akt = [porsi_aktivitas(ps) for ps in saham]
    pemilik = [porsi_pemilik(ps) for ps in saham]
    adv_nilai = np.array([ps['adv_nilai'] for ps in saham])

    # -- perhatian. Ritel: 1-3 saham pilihan (peluang ~ nilai transaksi
    #    ritel di saham itu) + sedikit perhatian ke semua saham supaya
    #    saham yang tiba-tiba ramai bisa "ditemukan".
    w_ritel = np.array([a['ritel'] for a in akt]) * adv_nilai
    w_ritel = (w_ritel / w_ritel.sum()) ** 0.7
    w_ritel /= w_ritel.sum()
    for nama in ('ritel_tren', 'ritel_kontra', 'ritel_ikut'):
        for a in indeks[nama]:
            k = 1 + int(rng.random() < 0.5) + int(rng.random() < 0.25)
            pilih = rng.choice(S, size=min(k, S), replace=False, p=w_ritel)
            pop.perhatian[a, :] = 0.03
            pop.perhatian[a, pilih] = 1.0
    for nama, kunci in (('institusi', 'lokal'), ('asing', 'asing')):
        w = np.array([a[kunci] for a in akt]) * adv_nilai
        # pangkat kecil = perhatian lebih rata: saham kecil tetap disentuh
        # cukup sering supaya arusnya tidak menggumpal jadi satu-dua order
        w = (w / w.sum()) ** 0.35
        idx = indeks[nama]
        pop.perhatian[idx, :] = w[None, :] * np.exp(0.3 * rng.standard_normal((len(idx), S)))
    # pedagang cepat: tiap saham dijaga >= 2 agen, sisanya bergilir
    cakupan = {}
    for i, a in enumerate(indeks['cepat']):
        j = i % S
        cakupan.setdefault(j, []).append(a)
        pop.perhatian[a, j] = 1.0
    for i, a in enumerate(indeks['bandar']):
        pop.perhatian[a, saham_bandar[i]] = 1.0
    jumlah_baris = pop.perhatian.sum(axis=1, keepdims=True)
    pop.perhatian = np.divide(pop.perhatian, jumlah_baris, out=np.zeros_like(pop.perhatian),
                              where=jumlah_baris > 0)

    # beda tafsir nilai wajar: institusi/asing sempit, ritel_kontra lebar
    pop.nu[:] = 0.0
    for nama, sd in (('institusi', 0.05), ('asing', 0.02), ('ritel_kontra', 0.06)):
        idx = indeks[nama]
        pop.nu[idx, :] = sd * rng.standard_normal((len(idx), S))

    # -- kepemilikan awal: float KSEI dibagi ke kelompok, lalu ke agen yang
    #    memperhatikan saham itu, sebanding perhatian x skala.
    harga = np.array([ps['harga'] for ps in saham])
    adv_lot = np.array([ps['adv_lot'] for ps in saham])
    ritel_idx = np.concatenate([indeks['ritel_tren'], indeks['ritel_kontra'], indeks['ritel_ikut']])
    for j in range(S):
        porsi, float_lot = pemilik[j]
        float_lot = float(float_lot)
        # pedagang cepat: persediaan 3 hari volume, diambil dari jatah ritel
        cepat_lot = int(min(3.0 * adv_lot[j], 0.05 * float_lot))
        ritel_lot = int(max(porsi['ritel'] * float_lot - cepat_lot, 0))
        for idx, total in ((ritel_idx, ritel_lot),
                           (indeks['institusi'], int(porsi['institusi'] * float_lot)),
                           (indeks['asing'], int(porsi['asing'] * float_lot))):
            bobot = pop.perhatian[idx, j] * pop.skala[idx]
            pop.pos[idx, j] += _bagi_lot(total, bobot)
        jaga = cakupan.get(j, [])
        if jaga:
            pop.pos[jaga, j] += _bagi_lot(cepat_lot, np.ones(len(jaga)))
    pop.biaya[:] = pop.pos * harga[None, :] * aturan.LOT

    # -- kas: porsi kas dari kekayaan (persona.kas = kas / total kekayaan)
    nilai_saham = (pop.pos * harga[None, :] * aturan.LOT).sum(axis=1)
    umum = np.isin(pop.tipe, TIPE_UMUM)
    rasio = np.clip(pop.kas, 0.0, 0.9)          # pop.kas sementara berisi parameter 'kas'
    pop.kas = np.where(umum, nilai_saham * rasio / (1.0 - rasio), 0.0)
    # agen umum yang tidak kebagian saham (perhatiannya ke saham kecil) tetap
    # diberi kas minimum supaya bisa ikut membeli
    if umum.any():
        median_kas = float(np.median(pop.kas[umum & (pop.kas > 0)])) if (umum & (pop.kas > 0)).any() else 1e9
        pop.kas[umum & (pop.kas <= 0)] = 0.25 * median_kas
    cepat = indeks['cepat']
    pop.kas[cepat] = (pop.pos[cepat] * harga[None, :] * aturan.LOT).sum(axis=1) * 1.2 + 1e8

    # -- ukuran order dasar per kelompok-saham. Target: bruto (beli+jual)
    #    tiap kelompok = porsi_aktivitas x 2 x ADV, dikurangi ~15% yang
    #    akan diisi pedagang cepat. Kalibrasi mikro mengoreksi sisanya.
    K = int(cfg.get('tick', 10))
    nilai_order = np.zeros((len(GRUP), S))
    peluang_jalan = 0.6 * 0.6 * 1.4             # P(|x|>ambang) x isi x pengali ukuran
    for g, kunci, tipe_g in (('ritel', 'ritel', ('ritel_tren', 'ritel_kontra', 'ritel_ikut')),
                             ('institusi', 'lokal', ('institusi',)),
                             ('asing', 'asing', ('asing',))):
        idx = np.concatenate([indeks[t] for t in tipe_g])
        for j in range(S):
            porsi = akt[j][kunci]
            if g == 'institusi' and j in saham_bandar:
                porsi = porsi * 0.7               # sebagian "lokal" adalah bandar
            target = porsi * 2.0 * adv_nilai[j] * 0.85
            order_per_hari = (K * pop.aktif[idx] * pop.perhatian[idx, j] * pop.skala[idx]).sum() * peluang_jalan
            nilai_order[G[g], j] = target / max(order_per_hari, 1e-9)

    info = {
        'indeks': {k: v.tolist() for k, v in indeks.items()},
        'cadangan': cad.tolist(),
        'jumlah': jumlah,
        'saham_bandar': saham_bandar,
        'cakupan_cepat': {int(j): [int(a) for a in v] for j, v in cakupan.items()},
        'nilai_order': nilai_order,
        'ritel_porsi': ritel_porsi,
        'akt': akt,
    }
    return pop, info
