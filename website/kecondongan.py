"""
Skor Kecondongan: peringkat harian semua emiten layak dari dua ukuran yang
masing-masing sudah lolos luar sampel -- DEKAT PUNCAK 52 MINGGU dan TENANG
(volatilitas 20 hari rendah). Riset lengkapnya: riset_pola_naik/skor.py.

KENAPA ADA
==========
Tiga cara mencari pola chart di app ini (Penemu Pola, ~40 pola di
riset_pola_naik/uji.py, analog & klaster bentuk di riset_pola_naik/analog.py)
sampai ke kesimpulan yang sama: informasi arah dari harga itu kecil, dan
yang tersisa tertangkap dua ukuran sederhana. Daripada menambang pola
keempat, dua ukuran itu digabung jadi satu peringkat harian.

RUMUS -- SAMA PERSIS DENGAN RISET, JANGAN DISETEL
=================================================
  persentil_puncak = peringkat persentil dari_puncak (close / close tertinggi
                     250 hari - 1; makin dekat 0 makin tinggi)
  persentil_tenang = peringkat persentil TERBALIK vol20 (simpangan baku
                     return log 20 hari; makin kecil makin tinggi)
  skor  = rata-rata keduanya, di antara emiten LAYAK hari itu
  desil = 1..10 dari skor
"Layak" = tembus_basis.fitur(): riwayat >= 260 hari, harga >= Rp100, median
nilai 20 hari >= Rp1 M, bertransaksi >= 90% hari, tanpa loncatan >45% dalam
60 hari -- saringan yang sama dengan pengujian. Harganya juga sama dengan
Tembus Basis: Summary 2026 disambung riwayat Yahoo (tembus_basis._panel).

CARA MEMBACA -- BUKTI DI BAWAH
==============================
- DESIL 1 = HINDARI. Ini sisi yang paling kokoh: "jauh dari puncak dan
  liar" kalah dari pasar di keempat sel uji dan di semua lapis likuiditas
  (-2,6% s.d. -13,5% per 60 hari), negatif 12 dari 14 tahun. Emiten
  delisting tidak ada di data Yahoo; diperiksa dengan arsip bulanan KSEI
  2018-2026 yang memuatnya, desil 1 jadi sedikit LEBIH buruk (-4,2% ->
  -4,9% per 3 bulan) -- temuannya bertahan (riset_pola_naik/delisting.py).
- DESIL 10 = CONDONG NAIK, tapi lebih lemah: +5,0% per 60 hari di sel
  validasi, ~0 di sel pencarian 2013-2019. Sebagai daftar beli 10 slot
  hasilnya setara beli-semua dengan kejatuhan lebih dangkal.
- Kecondongan KELOMPOK, bukan ramalan per emiten.
- IC dua komponennya di sel validasi sudah terlihat (pilot analog.py)
  sebelum rumus ini ditulis, jadi validasinya bukan uji buta. Rumusnya
  tanpa bobot atau ambang yang disetel; jurnal maju di bawah yang buta.

JURNAL MAJU
===========
kecondongan_jurnal.csv mencatat SEMUA emiten layak tiap hari bursa dengan
ukuran MENTAHNYA (dari_puncak, vol20), bukan skornya: peringkat dihitung
ulang saat evaluasi dari semua emiten hari itu, jadi emiten yang tercatat
belakangan (unduhan yang baru separuh waktu pemindaian pertama) tetap dinilai
terhadap semesta hari itu yang lengkap. kecondongan_hari.csv mencatat hari
mana saja jurnalnya jalan. Keduanya append-only dan SENGAJA tidak bernama
*_cache. Mulai 23 Sep 2026.

PECAHAN R2 DESIL 1 (29 Okt 2026, riset_pola_naik/jatuh_sendiri.py)
=================================================================
Desil 1 tidak seragam. Yang memisahkan emiten desil 1 yang lanjut ambruk
dari yang tidak adalah R2 250 hari terhadap pasar -- seberapa besar gerak
harian emiten itu dijelaskan gerak pasar:
    R2 < 0,05  "jalan sendiri"  vs pasar 60h -9,8 s.d. -14,3% di keempat sel
                                (t -3,3 s.d. -8,5), negatif 13/14 tahun,
                                39% jatuh lagi >= 20%; porto 10 slot -26%/thn
    R2 >= 0,15 "ikut pasar"     vs pasar -0,9 s.d. +3,4% (tidak signifikan) --
                                cuma ikut turun bersama pasar
Bertahan setelah likuiditas, porsi hari diam, dan volatilitas dikendalikan,
dan menang lawan volatilitas sisa (bukan puzzle IVOL). Ambang 0,05/0,15
dipilih dari SEBARAN R2 semua emiten-hari layak (p20 0,037, median 0,122),
tapi arah R2 sudah terlihat di keempat sel sebelum ambang dipilih -- jadi
statusnya kalibrasi, dan kecondongan_r2.csv yang mengujinya: R2 tiap baris
jurnal utama (append-only, idempoten). Baris sebelum 29 Okt 2026 diisi
belakangan dengan R2 PADA tanggalnya (harga s.d. hari itu, rumus tetap);
kolom `dicatat` membedakannya. Riset berhenti di sinyal Jul 2026, jadi
hasil baris-baris itu belum pernah terlihat.
R2 TIDAK berguna sebagai saringan Tembus Basis (menu_per_saham.py exante)
-- yang berbahaya dari emiten jalan sendiri adalah jatuhnya, bukan tembusnya.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import logging
import os
import pickle
import time

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

HERE = os.path.dirname(__file__)
CACHE_FILE = str(_runtime_file('', 'kecondongan_cache.pkl'))
JURNAL_FILE = str(_runtime_file('', 'kecondongan_jurnal.csv'))
HARI_FILE = str(_runtime_file('', 'kecondongan_hari.csv'))

VOL_W = 20
N_DAFTAR = 30
KOLOM_JURNAL = ['tanggal', 'stock', 'close', 'dari_puncak', 'vol20', 'nilai']
KOLOM_HARI = ['tanggal', 'dicatat', 'n_segar', 'n_layak', 'n_baris']
MIN_TANGGAL = 60          # tanggal matang minimal sebelum hasil jurnal ditampilkan

# Pecahan R2 -- lihat docstring. Rumus = riset_pola_naik/menu_per_saham.ciri_berjalan
# + pasar_lengkap; ambang = jatuh_sendiri.AMBANG. Ubah bersama riset, jangan terpisah.
R2_FILE = str(_runtime_file('', 'kecondongan_r2.csv'))
KOLOM_R2 = ['tanggal', 'stock', 'r2', 'beta', 'dicatat']
R2_W = 250                # jendela, hari bursa
R2_MIN = 200              # hari berdata minimal di jendela itu
R2_SENDIRI = 0.05         # R2 < ini = "jalan sendiri"
R2_PASAR = 0.15           # R2 >= ini = "ikut pasar"
R2_LABEL = {'sendiri': 'jalan sendiri', 'tengah': 'tengah', 'pasar': 'ikut pasar'}

# Angka riset (riset_pola_naik/skor.py, 23 Sep 2026). Halaman menampilkan
# yang tertulis di sini -- ubah bersama docstring riset, jangan terpisah.
BUKTI = {
    'ic': [
        {'sel': 'Pencarian (emiten A, 2013-2019)', 'puncak': 0.101, 't_puncak': 4.2,
         'tenang': 0.043, 't_tenang': 2.0, 'skor': 0.094, 't_skor': 3.9, 'skor20': 0.072},
        {'sel': 'Validasi (emiten B, 2020-2026)', 'puncak': 0.115, 't_puncak': 5.3,
         'tenang': 0.129, 't_tenang': 6.7, 'skor': 0.155, 't_skor': 6.9, 'skor20': 0.124},
        {'sel': 'Silang (emiten B, 2013-2019)', 'puncak': 0.062, 't_puncak': 3.4,
         'tenang': 0.066, 't_tenang': 3.5, 'skor': 0.080, 't_skor': 4.2, 'skor20': 0.061},
        {'sel': 'Silang (emiten A, 2020-2026)', 'puncak': 0.105, 't_puncak': 5.2,
         'tenang': 0.120, 't_tenang': 6.3, 'skor': 0.146, 't_skor': 6.6, 'skor20': 0.110},
    ],
    'sel_desil': [
        {'sel': 'Pencarian (A 2013-19)', 'd1': -4.1, 'd10': 0.5, 't10': 0.3},
        {'sel': 'Validasi (B 2020-26)', 'd1': -8.2, 'd10': 5.0, 't10': 4.2},
        {'sel': 'Silang (B 2013-19)', 'd1': -5.8, 'd10': 2.9, 't10': 3.0},
        {'sel': 'Silang (A 2020-26)', 'd1': -8.6, 'd10': 4.2, 't10': 4.4},
    ],
    # Sel validasi, satu pengamatan per emiten per 20 bar.
    'desil_validasi': [
        {'desil': 1, 'n': 807, 'vs20': -2.9, 'vs60': -8.2, 'naik10': 40.5, 'turun10': 58.6},
        {'desil': 2, 'n': 833, 'vs20': -1.4, 'vs60': -3.5, 'naik10': 42.0, 'turun10': 54.6},
        {'desil': 5, 'n': 783, 'vs20': 0.5, 'vs60': -0.1, 'naik10': 42.8, 'turun10': 49.3},
        {'desil': 8, 'n': 827, 'vs20': 1.0, 'vs60': 2.7, 'naik10': 39.6, 'turun10': 41.0},
        {'desil': 9, 'n': 765, 'vs20': 1.1, 'vs60': 3.6, 'naik10': 39.3, 'turun10': 34.8},
        {'desil': 10, 'n': 840, 'vs20': 1.7, 'vs60': 5.0, 'naik10': 35.5, 'turun10': 24.8},
    ],
    'desil_catatan': ('"+10% dulu" = menyentuh +10% sebelum -10% dalam 60 hari; pembandingnya ~41%. '
                      'Desil 10 lebih JARANG menyentuh +10% dulu -- ia tenang -- tapi jauh lebih jarang '
                      'menyentuh -10% dulu (24,8% lawan 58,6% di desil 1). Untungnya dari tidak jatuh, '
                      'bukan dari lonjakan.'),
    'tahun': [2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026],
    'tahun_d10': [1.5, 0.4, 5.4, -2.4, 3.8, 0.8, 4.0, -4.8, 6.3, 7.5, 3.4, 2.0, 3.7, 17.3],
    'tahun_d1': [-3.6, -6.9, -8.2, 7.7, -0.9, -4.3, -19.0, 5.2, -10.9, -14.4, -6.7, -8.0, -7.1, -11.8],
    'tahun_catatan': ('vs pasar 60 hari per tahun sinyal, semua emiten. Desil 10 positif 12/14 tahun, desil 1 '
                      'negatif 12/14. 2026 baru sampai sinyal Juni.'),
    'likuiditas': [
        {'lapis': 'Rp1-5 M/hari', 'd10': 4.8, 'n10': 1085, 'd1': -6.1, 'n1': 996},
        {'lapis': 'Rp5-20 M/hari', 'd10': 3.6, 'n10': 435, 'd1': -9.0, 'n1': 766},
        {'lapis': '> Rp20 M/hari', 'd10': 2.2, 'n10': 877, 'd1': -6.7, 'n1': 493},
    ],
    'likuiditas_catatan': ('Gabungan keempat sel. Desil 1 negatif di SEMUA sel dan SEMUA lapis (-2,6% s.d. '
                           '-13,5%); desil 10 paling lemah di emiten paling likuid.'),
    'portofolio': [
        {'strategi': 'Skor desil 10', 'cagr': 6.9, 'cagr_val': 8.5, 'dd': -38.3},
        {'strategi': 'Skor desil 10, ukuran posisi ~1/volatilitas', 'cagr': 5.8, 'cagr_val': 12.1, 'dd': -42.9},
        {'strategi': 'Puncak 52 mgg + volume (Tembus Basis, sudah lolos)', 'cagr': 18.6, 'cagr_val': 18.3, 'dd': -44.9},
        {'strategi': 'Puncak 52 mgg + volume DAN skor desil 10', 'cagr': 8.6, 'cagr_val': 12.5, 'dd': -25.9},
        {'strategi': 'Beli semua emiten layak (tanpa ongkos)', 'cagr': 3.7, 'cagr_val': 8.3, 'dd': -64.7, 'pembanding': True},
        {'strategi': 'IHSG', 'cagr': 3.0, 'cagr_val': 0.5, 'dd': -41.5, 'pembanding': True},
    ],
    'portofolio_catatan': ('10 slot, beli di close hari setelah masuk desil, tahan 60 hari, ongkos pulang-pergi '
                           '0,9%. Sebagai daftar beli skor ini biasa saja -- 2020-2026 setara beli-semua, cuma '
                           'kejatuhannya lebih dangkal. Sebagai saringan sinyal puncak 52 minggu ia memangkas '
                           'kejatuhan terdalam dari -45% ke -23% dengan ongkos CAGR.'),
    'batas': [
        'Data Yahoo cuma berisi emiten yang MASIH tercatat. Diperiksa dengan arsip bulanan KSEI 2018-2026 '
        '(yang memuat emiten delisting): memasukkan mereka membuat desil 1 sedikit lebih buruk (-4,2% jadi '
        '-4,9% per 3 bulan, versi bulanan) dan desil 10 tidak berubah (+2,9% jadi +3,0%). Arah biasnya '
        'seperti dugaan, besarnya kecil -- lihat riset_pola_naik/delisting.py.',
        'IC kedua komponen di sel validasi sudah terlihat sebelum rumus ini ditulis. Rumusnya tanpa bobot '
        'atau ambang yang disetel, tapi uji yang benar-benar buta adalah jurnal maju di halaman ini.',
        'Kecondongan kelompok, bukan ramalan per emiten: di desil 10 pun sebagian besar emiten tetap '
        'bisa turun.',
    ],
    # riset_pola_naik/jatuh_sendiri.py, 29 Okt 2026. Desil 1, satu kejadian per emiten per
    # 20 bar, vs pasar hari yang sama 60 hari (t galat per bulan) | hasil absolut | porsi
    # naik | porsi jatuh lagi >= 20%.
    'r2': {
        'ambang': [R2_SENDIRI, R2_PASAR],
        'sel': [
            {'kel': 'sendiri', 'label': 'R² < 0,05 — jalan sendiri', 'baris': [
                {'sel': 'Pencarian (A 2013-19)', 'vs60': -12.4, 't': -4.9, 'abs60': -16.7, 'naik': 30, 'jatuh20': 39, 'n': 141},
                {'sel': 'Validasi (B 2020-26)', 'vs60': -9.8, 't': -5.6, 'abs60': -12.5, 'naik': 32, 'jatuh20': 39, 'n': 707},
                {'sel': 'Silang (B 2013-19)', 'vs60': -14.3, 't': -3.3, 'abs60': -19.6, 'naik': 29, 'jatuh20': 36, 'n': 222},
                {'sel': 'Silang (A 2020-26)', 'vs60': -13.8, 't': -8.5, 'abs60': -16.2, 'naik': 27, 'jatuh20': 43, 'n': 637},
            ]},
            {'kel': 'tengah', 'label': 'R² 0,05–0,15', 'baris': [
                {'sel': 'Pencarian (A 2013-19)', 'vs60': -3.2, 't': -1.9, 'abs60': -7.4, 'naik': 36, 'jatuh20': 32, 'n': 277},
                {'sel': 'Validasi (B 2020-26)', 'vs60': -6.7, 't': -3.9, 'abs60': -10.1, 'naik': 32, 'jatuh20': 36, 'n': 385},
                {'sel': 'Silang (B 2013-19)', 'vs60': -4.6, 't': -2.8, 'abs60': -8.2, 'naik': 36, 'jatuh20': 26, 'n': 206},
                {'sel': 'Silang (A 2020-26)', 'vs60': -5.0, 't': -2.4, 'abs60': -7.2, 'naik': 34, 'jatuh20': 33, 'n': 314},
            ]},
            {'kel': 'pasar', 'label': 'R² ≥ 0,15 — ikut pasar', 'baris': [
                {'sel': 'Pencarian (A 2013-19)', 'vs60': 0.6, 't': 0.4, 'abs60': -1.1, 'naik': 49, 'jatuh20': 21, 'n': 318},
                {'sel': 'Validasi (B 2020-26)', 'vs60': -0.9, 't': -0.5, 'abs60': 0.7, 'naik': 46, 'jatuh20': 21, 'n': 299},
                {'sel': 'Silang (B 2013-19)', 'vs60': 3.4, 't': 1.8, 'abs60': 2.7, 'naik': 50, 'jatuh20': 15, 'n': 190},
                {'sel': 'Silang (A 2020-26)', 'vs60': 2.4, 't': 1.1, 'abs60': 6.2, 'naik': 50, 'jatuh20': 17, 'n': 276},
            ]},
        ],
        'tahun_negatif': {'sendiri': '13/14', 'tengah': '12/14', 'pasar': '6/14'},
        'porto': [
            {'strategi': 'Desil 1 + R² < 0,05', 'cagr': -26.4, 'dd': -98.7},
            {'strategi': 'Desil 1 + R² ≥ 0,15', 'cagr': 3.2, 'dd': -63.8},
            {'strategi': 'Beli semua emiten likuid (tanpa ongkos)', 'cagr': 4.8, 'dd': -56.8, 'pembanding': True},
        ],
        'porto_catatan': ('10 slot, masuk close hari setelah sinyal, tahan 60 hari, ongkos pulang-pergi 0,9%, '
                          '2013 - Jun 2026. Bukan anjuran membeli desil 1 yang ikut pasar -- hasilnya di bawah '
                          'beli-semua. Gunanya memilah mana yang memang perlu dihindari.'),
        'kokoh': [
            'Bukan efek beta: diulang dengan alfa (return dikurangi beta 250 hari x pasar di jendela yang sama), '
            'selisih R² atas-bawah tetap +12 s.d. +26% per 60 hari di keempat sel.',
            'Bukan likuiditas atau saham yang jarang bergerak: regresi dengan likuiditas, porsi hari diam, dan '
            'volatilitas 20 hari -- R² tetap +13 s.d. +30 (t 2,6-5,2); tanpa emiten yang sering diam pun tetap.',
            'Bukan puzzle volatilitas sisa (IVOL): diadu langsung, R² menang (t 2,5-5,6), volatilitas sisa '
            'tidak signifikan.',
            'Jendela 120 hari memberi arah yang sama (t 2,3-5,1).',
            'Di SEMUA emiten (bukan cuma desil 1) R² rendah juga kalah, tapi kira-kira sepertiganya. '
            'Efeknya terkumpul di emiten yang sedang jatuh.',
            'R² rendah BUKAN saringan Tembus Basis: tembus di emiten jalan sendiri tetap jalan.',
        ],
        'batas': ('Arah R² sudah terlihat di keempat sel sebelum ambang dipilih -- uji buta-nya jurnal maju '
                  'di halaman ini. Emiten delisting tidak ada di data Yahoo; mereka paling mungkin di '
                  'kelompok jalan sendiri, jadi angkanya kalau keliru justru terlalu ringan.'),
    },
}

# Harapan dari sel validasi, untuk dibandingkan dengan jurnal maju.
HARAPAN = {20: {'d10': 1.7, 'd1': -2.9, 'ic': 0.124}, 60: {'d10': 5.0, 'd1': -8.2, 'ic': 0.155}}
# Desil 1 per kelompok R2, sel validasi (jatuh_sendiri.py): vs pasar hari yang sama, dan
# alfa setelah beta 250 hari. Beta median: jalan sendiri 0,56, tengah 1,34, ikut pasar 1,71.
HARAPAN_R2 = {20: {'sendiri': {'vs': -5.3, 'alfa': -5.6}, 'tengah': {'vs': -2.1, 'alfa': -1.1},
                   'pasar': {'vs': 0.2, 'alfa': 0.7}},
              60: {'sendiri': {'vs': -9.8, 'alfa': -10.6}, 'tengah': {'vs': -6.7, 'alfa': -4.5},
                   'pasar': {'vs': -0.9, 'alfa': 0.2}}}


def _num(v, d=None):
    from .tembus_basis import _num as tb_num
    return tb_num(v, d)


def vol20(close):
    lr = np.log(close.astype(float)).diff()
    return lr.rolling(VOL_W, min_periods=VOL_W).std()


def ukur_pasar(panel):
    """R2 dan beta 250 hari tiap emiten terhadap pasar: {emiten: DataFrame(r2, beta)}.

    Pasar = rata-rata return log harian emiten yang KEMARIN likuid (riwayat >= 260
    bar, harga >= Rp100, median nilai 20 hari >= Rp1 M, bebas loncatan 60 hari --
    TANPA syarat bertransaksi 90%, sama dengan riset menu_per_saham.pasar_lengkap).
    Hari dengan loncatan >45% dibuang. R2 = kov^2 / (var emiten x var pasar),
    beta = kov / var pasar, dari 250 baris terakhir emiten itu, minimal 200 hari
    berdata. Beta dipakai jurnal: kelompok "ikut pasar" ber-beta ~1,7, jadi di
    pasar yang ambruk ia kalah dari pasar hanya karena beta -- alfa yang adil.
    """
    from .tembus_basis import C as TB_C
    lr, ok = {}, {}
    for s, f in panel['fit'].items():
        x = np.log(f['close'].astype(float)).diff()
        x[f['naik'].abs() > TB_C['LONCAT']] = np.nan
        lr[s] = x
        ok[s] = ((f['hist'] >= TB_C['MIN_RIWAYAT']) & (f['close'] >= TB_C['MIN_HARGA'])
                 & (f['nilai20'] >= TB_C['MIN_NILAI']) & (f['loncat60'] == 0)).shift(1, fill_value=False)
    L = pd.DataFrame(lr)
    K = pd.DataFrame(ok).reindex(L.index).astype('boolean').fillna(False).astype(bool)
    pasar = L.where(K).mean(axis=1)
    out = {}
    for s, x in lr.items():
        m = pasar.reindex(x.index)
        kov = x.rolling(R2_W, min_periods=R2_MIN).cov(m)
        vm = m.rolling(R2_W, min_periods=R2_MIN).var()
        r2 = kov * kov / (x.rolling(R2_W, min_periods=R2_MIN).var() * vm)
        out[s] = pd.DataFrame({'r2': r2.clip(0, 1), 'beta': kov / vm})
    return out


def _nilai(ukur, stock, tanggal, kol):
    d = (ukur or {}).get(stock)
    if d is None:
        return np.nan
    v = d[kol].get(tanggal, np.nan)
    return float(v) if v is not None else np.nan


def kelompok_r2(v):
    if v is None or not np.isfinite(v):
        return None
    return 'sendiri' if v < R2_SENDIRI else ('pasar' if v >= R2_PASAR else 'tengah')


def peringkat(df):
    """Satu hari, emiten layak saja: kolom dari_puncak & vol20 ->
    r_puncak, r_tenang, skor, desil. Rumus = riset_pola_naik/skor.muat()."""
    d = df.copy()
    d['r_puncak'] = d['dari_puncak'].rank(pct=True)
    d['r_tenang'] = d['vol20'].rank(pct=True, ascending=False)
    d['skor'] = (d['r_puncak'] + d['r_tenang']) / 2
    d['desil'] = np.ceil(d['skor'].rank(pct=True) * 10).clip(1, 10)
    return d


def _potret(panel, tanggal, vols, ukur=None):
    """Emiten layak pada `tanggal` dengan ukuran mentahnya (+ R2 kalau ada)."""
    baris = []
    for stock, f in panel['fit'].items():
        if tanggal is None or tanggal not in f.index:
            continue
        r = f.loc[tanggal]
        if not bool(r['layak']):
            continue
        v = vols[stock].loc[tanggal]
        if not np.isfinite(r['dari_puncak']) or not np.isfinite(v):
            continue
        baris.append({'stock': stock, 'close': float(r['close']), 'dari_puncak': float(r['dari_puncak']),
                      'vol20': float(v), 'nilai': float(r['nilai20']),
                      'r2': _nilai(ukur, stock, tanggal, 'r2')})
    return pd.DataFrame(baris, columns=['stock', 'close', 'dari_puncak', 'vol20', 'nilai', 'r2'])


# ---------------------------------------------------------------------------
# JURNAL MAJU
# ---------------------------------------------------------------------------
def _muat_jurnal():
    """(jurnal, hari). Berkas yang ada tapi tak terbaca -> melempar, BUKAN
    kosong: penulis tidak boleh mengira jurnal kosong lalu mulai dari nol."""
    j = (pd.read_csv(JURNAL_FILE, dtype={'tanggal': str, 'stock': str})
         if os.path.exists(JURNAL_FILE) else pd.DataFrame(columns=KOLOM_JURNAL))
    h = (pd.read_csv(HARI_FILE, dtype={'tanggal': str})
         if os.path.exists(HARI_FILE) else pd.DataFrame(columns=KOLOM_HARI))
    if len(j):
        j = j.drop_duplicates(['tanggal', 'stock'], keep='first')
    if len(h):
        h = h.drop_duplicates('tanggal', keep='last')
    return j, h


def catat(potret, hari_pasar, n_segar):
    """Idempoten per (tanggal, emiten), sama seperti tembus_basis.catat."""
    tanggal = hari_pasar.strftime('%Y-%m-%d')
    try:
        lama, _ = _muat_jurnal()
    except Exception as exc:
        logger.exception('Jurnal Kecondongan tidak terbaca -- tidak menulis apa pun')
        return {'tanggal': tanggal, 'tercatat': 0, 'pesan': 'jurnal tidak terbaca: %s' % exc}
    sudah = set(lama.loc[lama['tanggal'] == tanggal, 'stock']) if len(lama) else set()
    baru = potret[~potret['stock'].isin(sudah)]
    if len(baru):
        out = pd.DataFrame({
            'tanggal': tanggal, 'stock': baru['stock'],
            'close': baru['close'].round(2), 'dari_puncak': baru['dari_puncak'].round(5),
            'vol20': baru['vol20'].round(6), 'nilai': baru['nilai'].round(0),
        }, columns=KOLOM_JURNAL)
        out.to_csv(JURNAL_FILE, mode='a', index=False, header=not os.path.exists(JURNAL_FILE))
    pd.DataFrame([{'tanggal': tanggal, 'dicatat': time.strftime('%Y-%m-%d %H:%M'), 'n_segar': n_segar,
                   'n_layak': len(potret), 'n_baris': len(sudah) + len(baru)}],
                 columns=KOLOM_HARI).to_csv(HARI_FILE, mode='a', index=False,
                                             header=not os.path.exists(HARI_FILE))
    return {'tanggal': tanggal, 'tercatat': int(len(baru)), 'sudah_ada': len(sudah), 'n_layak': len(potret)}


def _muat_r2():
    """Jurnal R2. Berkas ada tapi tak terbaca -> melempar, sama dengan _muat_jurnal."""
    r = (pd.read_csv(R2_FILE, dtype={'tanggal': str, 'stock': str, 'dicatat': str})
         if os.path.exists(R2_FILE) else pd.DataFrame(columns=KOLOM_R2))
    if len(r):
        r = r.drop_duplicates(['tanggal', 'stock'], keep='first')
        for kol in ('r2', 'beta'):
            r[kol] = pd.to_numeric(r[kol], errors='coerce')
    return r


def catat_r2(ukur):
    """R2 & beta untuk tiap baris jurnal utama yang belum punya -- idempoten per (tanggal, emiten).

    Mengikuti jurnal utama, bukan cuma hari ini, jadi hari yang terlewat (atau
    tanggal sebelum pecahan R2 dipasang) ikut terisi dengan nilai PADA tanggal itu.
    `dicatat` menandai kapan barisnya ditulis; evaluasi memisahkan yang diisi
    belakangan. Yang tidak terhitung (riwayat < 200 hari) dicatat kosong.
    """
    j, _ = _muat_jurnal()
    lama = _muat_r2()
    if j.empty:
        return {'tercatat': 0}
    sudah = set(zip(lama['tanggal'], lama['stock'])) if len(lama) else set()
    sekarang = time.strftime('%Y-%m-%d %H:%M')
    baru = []
    for tgl, s in zip(j['tanggal'], j['stock']):
        if (tgl, s) in sudah:
            continue
        r2 = _nilai(ukur, s, pd.Timestamp(tgl), 'r2')
        beta = _nilai(ukur, s, pd.Timestamp(tgl), 'beta')
        baru.append({'tanggal': tgl, 'stock': s, 'r2': round(r2, 5) if np.isfinite(r2) else None,
                     'beta': round(beta, 4) if np.isfinite(beta) else None, 'dicatat': sekarang})
    if baru:
        pd.DataFrame(baru, columns=KOLOM_R2).to_csv(R2_FILE, mode='a', index=False,
                                                     header=not os.path.exists(R2_FILE))
    return {'tercatat': len(baru), 'sudah_ada': len(sudah)}


def evaluasi(panel, hari_pasar):
    """Hasil jurnal yang sudah matang: desil 10 & 1 terhadap pasar hari yang
    sama, dan IC harian -- peringkat dihitung ulang dari ukuran mentah."""
    from .tembus_basis import C as TB_C
    try:
        j, h = _muat_jurnal()
    except Exception as exc:
        return {'available': False, 'message': 'Jurnal tidak terbaca: %s' % exc}

    kal = panel['kal']
    pos = {d: i for i, d in enumerate(kal)}
    hari_akhir = pos.get(hari_pasar, len(kal) - 1)
    cakupan = {'n_hari': int(len(h)), 'n_baris': int(len(j)),
               'mulai': str(h['tanggal'].min()) if len(h) else None}
    if cakupan['mulai']:
        mulai = pd.Timestamp(cakupan['mulai'])
        tercatat = set(h['tanggal'].astype(str))
        cakupan['terlewat'] = [d.strftime('%Y-%m-%d') for d in kal
                               if mulai <= d <= hari_pasar and d.strftime('%Y-%m-%d') not in tercatat]
    else:
        cakupan['terlewat'] = []
    if j.empty:
        return {'available': True, 'cakupan': cakupan, 'horizon': [], 'pesan': 'Jurnal baru dimulai.'}

    tutup = pd.DataFrame({s: f['close'] for s, f in panel['fit'].items()}).reindex(kal)
    layak = pd.DataFrame({s: f['layak'] for s, f in panel['fit'].items()}).reindex(kal)
    layak = layak.astype('boolean').fillna(False).astype(bool)
    loncat_cs = (tutup.pct_change(fill_method=None).abs() > TB_C['LONCAT']).astype(float).cumsum()

    j = j.copy()
    j['tgl'] = pd.to_datetime(j['tanggal'])
    j['p'] = j['tgl'].map(pos)
    j = j.dropna(subset=['p'])
    j['p'] = j['p'].astype(int)
    for kol in ('dari_puncak', 'vol20'):
        j[kol] = pd.to_numeric(j[kol], errors='coerce')
    j = j.dropna(subset=['dari_puncak', 'vol20'])
    j = pd.concat([peringkat(g) for _, g in j.groupby('tanggal')]) if len(j) else j
    try:
        r2j = _muat_r2()
    except Exception:
        logger.exception('Jurnal R2 Kecondongan tidak terbaca -- pecahan R2 dilewati')
        r2j = pd.DataFrame(columns=KOLOM_R2)
    if len(r2j):
        j = j.merge(r2j[['tanggal', 'stock', 'r2', 'beta']], on=['tanggal', 'stock'], how='left')
        # dicatat di harinya atau besoknya = maju; lebih lambat = diisi belakangan
        telat = (pd.to_datetime(r2j['dicatat'], errors='coerce').dt.normalize()
                 - pd.to_datetime(r2j['tanggal'])).dt.days > 1
        cakupan['r2'] = {'n_baris': int(r2j['r2'].notna().sum()), 'n_belakangan': int(telat.sum()),
                         'maju_sejak': (str(r2j.loc[~telat, 'tanggal'].min()) if (~telat).any() else None)}
    else:
        j['r2'] = np.nan
        j['beta'] = np.nan
    j['r2_kel'] = [kelompok_r2(v) for v in j['r2']]

    hasil = []
    for hz in (20, 60):
        masuk = tutup.shift(-1)
        keluar = tutup.shift(-(hz + 1))
        lr = np.log(keluar / masuk).mask((loncat_cs.shift(-(hz + 1)) - loncat_cs) > 0)
        pasar = lr.where(layak).mean(axis=1)
        m = j[j['p'] + hz + 1 <= hari_akhir].copy()
        r = {'horizon': hz, 'harapan': HARAPAN[hz], 'n_tanggal': int(m['tanggal'].nunique()),
             'cukup': False, 'sisa_hari': None}
        if len(m):
            kol = {s: i for i, s in enumerate(lr.columns)}
            arr = lr.to_numpy()
            m['x'] = [arr[p, kol[s]] if s in kol else np.nan for p, s in zip(m['p'], m['stock'])]
            m['b'] = pasar.to_numpy()[m['p'].to_numpy()]
            m = m[np.isfinite(m['x']) & np.isfinite(m['b'])]
            m['exc'] = m['x'] - m['b']
            ic = m.groupby('tanggal').apply(
                lambda g: g['skor'].corr(g['x'], method='spearman') if len(g) >= 15 else np.nan).dropna()
            d10, d1 = m[m['desil'] == 10], m[m['desil'] == 1]
            r.update({
                'n_tanggal': int(m['tanggal'].nunique()),
                'n10': int(len(d10)), 'n1': int(len(d1)),
                'd10': _num((np.exp(d10['exc'].mean()) - 1) * 100, 2) if len(d10) else None,
                'd1': _num((np.exp(d1['exc'].mean()) - 1) * 100, 2) if len(d1) else None,
                'ic': _num(ic.mean(), 3) if len(ic) else None,
                'cukup': int(m['tanggal'].nunique()) >= MIN_TANGGAL,
            })
            # alfa = return dikurangi beta x pasar di jendela yang sama: kelompok "ikut pasar"
            # ber-beta ~1,7, jadi "vs pasar" polos menghukumnya tiap kali pasar ambruk.
            m['alfa'] = m['x'] - m['beta'] * m['b']
            pecah = []
            for kel in ('sendiri', 'tengah', 'pasar'):
                g = d1[d1['r2_kel'] == kel]
                ga = m.loc[g.index, 'alfa'].dropna()
                pecah.append({'kel': kel, 'label': R2_LABEL[kel], 'n': int(len(g)),
                              'n_tanggal': int(g['tanggal'].nunique()),
                              'exc': _num((np.exp(g['exc'].mean()) - 1) * 100, 2) if len(g) else None,
                              'alfa': _num((np.exp(ga.mean()) - 1) * 100, 2) if len(ga) else None,
                              'beta': _num(g['beta'].median(), 2) if g['beta'].notna().any() else None})
            r['d1_r2'] = pecah
        r['harapan_r2'] = HARAPAN_R2[hz]
        belum = j[j['p'] + hz + 1 > hari_akhir]
        if len(belum) and r['n_tanggal'] == 0:
            r['sisa_hari'] = int(belum['p'].min() + hz + 1 - hari_akhir)
        hasil.append(r)
    return {'available': True, 'cakupan': cakupan, 'horizon': hasil, 'min_tanggal': MIN_TANGGAL}


# ---------------------------------------------------------------------------
# PEMINDAIAN
# ---------------------------------------------------------------------------
def _bangun():
    from .tembus_basis import _panel
    panel = _panel()
    if not panel or not panel['fit']:
        return {'available': False, 'message': 'Tidak ada berkas Summary yang bisa dibaca.'}
    kal = panel['kal']
    hari_pasar = max(f.index[-1] for f in panel['fit'].values())
    sebelum = kal[kal < hari_pasar]
    kemarin = sebelum[-1] if len(sebelum) else None
    vols = {s: vol20(f['close']) for s, f in panel['fit'].items()}
    n_segar = sum(1 for f in panel['fit'].values() if f.index[-1] == hari_pasar)
    try:
        ukur = ukur_pasar(panel)
    except Exception:
        logger.exception('Gagal menghitung R2 Kecondongan -- halaman jalan tanpa pecahan R2')
        ukur = {}

    hari = peringkat(_potret(panel, hari_pasar, vols, ukur))
    kem = peringkat(_potret(panel, kemarin, vols)) if kemarin is not None else pd.DataFrame()
    desil_kemarin = dict(zip(kem['stock'], kem['desil'])) if len(kem) else {}

    try:
        dicatat = catat(hari, hari_pasar, n_segar)
    except Exception as exc:
        logger.exception('Gagal mencatat jurnal Kecondongan')
        dicatat = {'tercatat': 0, 'pesan': 'gagal: %s' % exc}
    # SESUDAH jurnal utama: catat_r2 mengikuti baris-barisnya, termasuk hari ini.
    try:
        dicatat_r2 = catat_r2(ukur) if ukur else {'tercatat': 0, 'pesan': 'R2 tidak terhitung'}
    except Exception as exc:
        logger.exception('Gagal mencatat jurnal R2 Kecondongan')
        dicatat_r2 = {'tercatat': 0, 'pesan': 'gagal: %s' % exc}
    try:
        jurnal = evaluasi(panel, hari_pasar)
    except Exception as exc:
        logger.exception('Gagal mengevaluasi jurnal Kecondongan')
        jurnal = {'available': False, 'message': 'Gagal mengevaluasi: %s' % exc}

    def _baris(r):
        dk = desil_kemarin.get(r['stock'])
        return {'stock': r['stock'], 'skor': _num(r['skor'] * 100, 1), 'desil': int(r['desil']),
                'desil_kemarin': int(dk) if dk is not None and np.isfinite(dk) else None,
                'r_puncak': _num(r['r_puncak'] * 100, 0), 'r_tenang': _num(r['r_tenang'] * 100, 0),
                'dari_puncak': _num(r['dari_puncak'] * 100, 1), 'vol20': _num(r['vol20'] * 100, 2),
                'close': _num(r['close'], 0), 'nilai_b': _num(r['nilai'] / 1e9, 2),
                'r2': _num(r['r2'], 3), 'r2_kel': kelompok_r2(r['r2'])}

    semua = [_baris(r) for _, r in hari.sort_values('skor', ascending=False).iterrows()]
    atas = [b for b in semua if b['desil'] == 10][:N_DAFTAR]
    # Desil 1: yang jalan sendiri dulu -- itu yang di riset benar-benar terus jatuh.
    urut_kel = {'sendiri': 0, 'tengah': 1, None: 1, 'pasar': 2}
    bawah = sorted([b for b in semua if b['desil'] == 1],
                   key=lambda b: (urut_kel.get(b['r2_kel'], 1), b['skor']))[:N_DAFTAR]
    masuk10 = sorted(b['stock'] for b in semua if b['desil'] == 10 and b['desil_kemarin'] not in (10, None))
    masuk1 = sorted(b['stock'] for b in semua if b['desil'] == 1 and b['desil_kemarin'] not in (1, None))
    d1 = [b for b in semua if b['desil'] == 1]
    r2_hari, beta_hari = {}, {}
    for s in ukur:
        v = _nilai(ukur, s, hari_pasar, 'r2')
        if np.isfinite(v):
            r2_hari[s] = round(v, 4)
            beta_hari[s] = round(_nilai(ukur, s, hari_pasar, 'beta'), 3)
    return {
        'available': True,
        'as_of': hari_pasar.strftime('%Y-%m-%d'),
        'kemarin': kemarin.strftime('%Y-%m-%d') if kemarin is not None else None,
        'n_emiten': len(panel['fit']), 'n_segar': n_segar, 'n_layak': len(hari),
        'n_desil': {'10': sum(1 for b in semua if b['desil'] == 10), '1': len(d1)},
        'n_d1_r2': {k: sum(1 for b in d1 if b['r2_kel'] == k) for k in ('sendiri', 'tengah', 'pasar')},
        'atas': atas, 'bawah': bawah, 'semua': semua,
        'masuk10': masuk10, 'masuk1': masuk1,
        # R2 & beta SEMUA emiten di panel (bukan cuma yang layak) -- dibaca Jatuh Dalam lewat r2_cache().
        'r2_semua': r2_hari, 'beta_semua': beta_hari,
        'r2_info': {'as_of': hari_pasar.strftime('%Y-%m-%d'), 'n': len(r2_hari),
                    'ambang': [R2_SENDIRI, R2_PASAR], 'catat': dicatat_r2},
        'catat': dicatat, 'jurnal': jurnal, 'bukti': BUKTI,
        'dibangun': time.strftime('%Y-%m-%d %H:%M'), 'from_cache': False,
    }


def _sumber_terbaru():
    from .tembus_basis import _sumber_terbaru as tb_sumber
    return tb_sumber()


def scan(force=False):
    """Peringkat hari bursa terakhir + jurnal maju, di-cache terhadap Summary
    terbaru. Pembangunan ulang SELALU mencatat jurnal dulu (idempoten)."""
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                simpan = pickle.load(fh)
            if simpan.get('ts', 0) >= _sumber_terbaru():
                hasil = dict(simpan['result'])
                hasil['from_cache'] = True
                hasil['bukti'] = BUKTI
                return hasil
        except Exception:
            pass
    hasil = _bangun()
    if hasil.get('available'):
        try:
            with open(CACHE_FILE, 'wb') as fh:
                pickle.dump({'ts': time.time(), 'result': hasil}, fh)
        except Exception:
            logger.exception('Gagal menyimpan cache Kecondongan')
    return hasil


def r2_cache():
    """(as_of, {emiten: R2}, {emiten: beta}) dari cache SAJA -- untuk Jatuh Dalam,
    yang tidak membangun panel harga sendiri. (None, {}, {}) kalau belum ada."""
    try:
        with open(CACHE_FILE, 'rb') as fh:
            hasil = pickle.load(fh)['result']
    except Exception:
        return None, {}, {}
    return ((hasil.get('r2_info') or {}).get('as_of'), hasil.get('r2_semua') or {},
            hasil.get('beta_semua') or {})


def untuk(ticker):
    """Baris satu emiten dari cache SAJA (Halaman Saham) -- tidak memindai."""
    try:
        with open(CACHE_FILE, 'rb') as fh:
            hasil = pickle.load(fh)['result']
    except Exception:
        return None
    for b in hasil.get('semua') or []:
        if b['stock'] == ticker:
            return dict(b, as_of=hasil.get('as_of'), n_layak=hasil.get('n_layak'))
    return {'stock': ticker, 'desil': None, 'as_of': hasil.get('as_of'), 'n_layak': hasil.get('n_layak')}


def cek():
    h = scan(force=True)
    if not h.get('available'):
        print(h.get('message'))
        return
    print('posisi %s | layak %d dari %d segar | jurnal: %s'
          % (h['as_of'], h['n_layak'], h['n_segar'], h['catat']))
    print('desil 10 teratas:', ', '.join('%s %.0f' % (b['stock'], b['skor']) for b in h['atas'][:12]))
    print('desil 1 terbawah:', ', '.join('%s %.0f' % (b['stock'], b['skor']) for b in h['bawah'][:12]))
    print('masuk desil 10 hari ini:', ', '.join(h['masuk10']) or '-')
    print('masuk desil 1 hari ini:', ', '.join(h['masuk1']) or '-')
    print('desil 1 per R2: %s | R2 terhitung %d emiten | jurnal R2: %s'
          % (h['n_d1_r2'], h['r2_info']['n'], h['r2_info']['catat']))
    for r in h['jurnal'].get('horizon', []):
        print('  jurnal H+%d: %d tanggal matang, d10 %s, d1 %s, IC %s | d1 per R2 %s'
              % (r['horizon'], r['n_tanggal'], r.get('d10'), r.get('d1'), r.get('ic'),
                 [(x['kel'], x['n'], x['exc']) for x in r.get('d1_r2') or []]))


if __name__ == '__main__':
    cek()
