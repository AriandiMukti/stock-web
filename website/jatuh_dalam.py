"""
Jatuh Dalam: emiten yang harganya sudah jauh di bawah puncak 120 harinya.

UJI ULANG 23 SEP 2026: GAGAL DI SEMESTA LUAS -- BACA INI DULU
=============================================================
Semua bukti "lolos luar sampel" di bawah berasal dari 20 emiten folder Test
(ADRO, BBCA, BREN, CUAN, ...). Emiten itu dipilih TAHUN 2026 karena besar
HARI INI -- jadi setiap kejatuhan lama mereka, menurut definisinya, diikuti
pemulihan. Kalau tidak pulih, mereka tidak akan jadi emiten besar. Itu bias
hindsight, dan "beli yang baru jatuh dalam" adalah pola yang paling
diuntungkannya.

Diuji ulang di ~750 emiten likuid (Yahoo 2013-2026, median nilai >= Rp1 M/
hari -- riset_pola_naik/cek_jatuh_dalam.py dan riset_pola_naik/uji.py):

    aturan yang sama (jatuh >40% dari puncak 60h + bergejolak), 2016-2025,
    gaya uji lama (close H -> H+20, tanpa dedup):
      20 emiten Test              +14,58pp vs semua hari   (replikasi cocok)
      semua emiten likuid          -0,27pp vs semua hari
                                   -1,56pp vs pasar hari yang sama
                                   majemuk -2,99%, median -2,86%

    cara uji tembus_basis.py (masuk H+1, jeda 20 hari, majemuk, pasar hari
    yang sama):
      sel validasi 2020-2026      -7,5% per 60 hari (t -5,6), naik 37,6%
      per tahun 2013-2026         negatif 9 dari 12 tahun
      portofolio 10 slot          -19,1%/tahun, drawdown -95,6%

Peluang naik >=10% memang lebih tinggi (26,2% vs 18,7%) -- emiten yang baru
jatuh dalam itu liar -- tapi peluang turun >=10% lebih tinggi lagi (36,2%).
Status di status_bukti.py diturunkan ke "gagal". Halaman ini dibiarkan
karena catatan di bawah tetap benar untuk sampel tempat ia diuji; yang
salah adalah anggapan bahwa itu berlaku umum.

PECAHAN R2 (29 OKT 2026) -- riset_pola_naik/jatuh_sendiri.py
============================================================
Di semesta luas yang sama, "jatuh dalam" ternyata dua kelompok yang berlawanan.
Pemisahnya R2 250 hari terhadap pasar (seberapa besar gerak harian emiten
dijelaskan pasar), dihitung kecondongan.ukur_pasar dan dibaca dari cache-nya:
    R2 < 0,05  "jalan sendiri"  vs pasar 60h -12 s.d. -24% di keempat sel
                                (t -3,1 s.d. -7,7); porto 10 slot -21%/thn
    R2 >= 0,15 "ikut pasar"     vs pasar +2,1 s.d. +8,7%, alfa setelah beta
                                +4,1 s.d. +6,8%, naik 58-67%; porto +7,3%/thn
                                (2013-19 +7,6%, 2020-26 +6,8%), DD -45,5%
"Ikut pasar" positif di keempat sel, tapi ambangnya dipilih sesudah arah R2
terlihat -- KALIBRASI, bukan teruji. Definisi riset sedikit beda dari halaman
ini (close terhadap puncak close 60 hari, rentang 20 hari terhadap close,
emiten >= Rp1 M/hari); jurnal_jatuh_dalam.csv menguji versi halaman: tiap
kandidat dicatat tiap hari dengan R2 & beta-nya, dinilai 20/60 hari bursa
kemudian (bergejolak, >= Rp1 M/hari, satu kejadian per emiten per 20 hari).

KENAPA INI ADA
Pertanyaan aslinya justru kebalikannya -- "cari saham yang naik banyak
SETELAH harganya melandai". Hipotesis itu diuji lebih dulu dan DITOLAK
datanya. Yang tersisa setelah pengujian adalah sisi "sudah jatuh"-nya,
bukan sisi "melandai"-nya.

HIPOTESIS YANG GAGAL: "melandai dulu, baru naik banyak"
Diuji adil: 5 definisi melandai (rentang 20 hari < 10/15/20/25/30%) x 3
horizon (20/40/60 hari) = 15 kombinasi, di dua sampel terpisah. Gagal di
kelima belasnya. Luar sampel (21 emiten, 2016-2025), melandai justru
MENURUNKAN peluang rally di semua setelan:

    horizon   peluang rally   return vs pasar
    H+20        -3,6pp           -0,65pp  (t=-7,9)
    H+40        -4,0pp           -0,92pp  (t=-7,0)
    H+60        -4,2pp           -1,50pp  (t=-8,6)

Di kalibrasi 2026 sama arahnya: hari yang melandai cuma 2,44% berpeluang
naik >=30% dalam 20 hari, sementara hari biasa 10,17%.

Kesan "pemenang selalu melandai dulu" datang dari melihat pemenangnya
saja. Dari 104 emiten 2026 yang naik >=30% dalam 20 hari setelah jatuh
>60% dari puncak, NOL yang sedang melandai (rentang 20 hari < 15%).
Median rentang mereka 67,7% -- masih liar, bukan adem. Yang gagal justru
rentangnya lebih sempit (median 56,8%).

YANG BERTAHAN: BARU SAJA JATUH DALAM
Diuji di dua sampel yang terpisah periode DAN semestanya.

  jatuh >40% dari puncak 60 hari
    luar sampel 21 emiten 2016-2025 : peluang rally +32,5pp, return H+20
                                      +8,18pp vs pasar (t=+11,8)
    kalibrasi 2026 semesta penuh    : peluang rally +10,6pp, return H+20
                                      +4,16pp vs pasar (t=+20,5)

  ditambah syarat masih bergejolak
    luar sampel : peluang rally +36,2pp, return +9,39pp (t=+11,7)
    kalibrasi   : peluang rally +11,1pp, return +4,16pp (t=+19,7)

KENAPA 60 HARI, BUKAN 120
Versi pertama halaman ini memakai puncak 120 hari -- angka yang DITEBAK,
bukan diuji. Waktu pencarian cirinya diulang terbalik (30 ukuran dihitung
mekanis, data yang memilih), `dari_puncak60` keluar di peringkat lebih
tinggi daripada `dari_puncak120`. Diuji langsung sebagai aturan screener,
jendela 60 hari menang di KEDUA sampel:

    return H+20 vs pasar    120 hari    60 hari
    luar sampel              +4,54pp    +9,54pp
    kalibrasi 2026           +2,71pp    +4,58pp

Menang di dua-duanya, jadi ini bukan hasil mencocokkan diri ke set luar
sampel. Masuk akalnya: "jatuh 40% dari puncak 60 hari" berarti jatuhnya
BARU dan tajam; "jatuh 40% dari puncak 120 hari" bisa berarti merosot
pelan setahun -- keadaan yang sama sekali berbeda, dan yang kedua jauh
lebih lemah.

Pembanding yang menunjukkan ini bukan sekadar efek rezim: "sudah naik
>20% dalam 20 hari" (ikut momentum) return-nya +3,3pp di 2016-2025 tapi
-5,1pp di 2026 -- berbalik tanda. Yang "jatuh dalam" tidak berbalik.

DETAIL YANG PALING MENENTUKAN: JANGAN YANG SUDAH ADEM
Melandai mengencerkan edge-nya, konsisten di ketiga horizon (luar sampel):

    H+60   jatuh<-40% + MASIH bergejolak : rally +27,5pp, return +5,4pp
           jatuh<-40% + sudah melandai   : rally +16,7pp, return +1,6pp

Bacaannya: yang masih bergerak liar sesudah jatuh berarti masih ada yang
bertransaksi di situ; yang sudah adem berarti peminatnya sudah pergi.

BUKAN CUMA EKOR YANG PANJANG -- SELURUH SEBARANNYA BERGESER
Kekhawatiran wajar: rata-rata bisa terangkat segelintir peledak seperti
DEFI (+448%). Ternyata bukan itu -- mediannya ikut bergerak, dan sisi
ruginya ikut mengecil:

    luar sampel 2016-2025, return 20 hari
      semua hari     rata2  +2,47%   median  +0,00%   rugi 49,1%
      jatuh <-40%    rata2  +5,32%   median  +2,68%   rugi 43,4%
      jatuh <-60%    rata2 +18,75%   median +14,88%   rugi 27,0%

    kalibrasi 2026
      semua hari     rata2  -0,68%   median  -0,41%   rugi 50,4%
      jatuh <-40%    rata2  +1,52%   median  +0,88%   rugi 45,9%
      jatuh <-60%    rata2  +5,68%   median  +2,99%   rugi 41,2%

KENAPA BAR BASI DIBUANG
Emiten yang disuspend berhenti mengirim data tapi berkas Summary-nya
tetap ada, dengan harga terakhir yang membeku. Tanpa saringan, mereka
justru MENDUDUKI PUNCAK daftar ini -- harga beku setelah jatuh dalam
terlihat seperti kandidat terbaik, padahal sahamnya tidak bisa dibeli
sama sekali. Nyata terjadi saat halaman ini pertama dibuat: HILL
(-93,5%), TRUE (-90,7%) dan INDX menempati tiga besar, padahal ketiganya
berhenti diperdagangkan sejak 29 Juni 2026. Emiten yang bar terakhirnya
bukan hari bursa terakhir dilewati, dan jumlahnya dilaporkan -- konvensi
yang sama dipakai pola_jurnal.py.

TAMBAHAN: TITIK MANIS -60% SAMPAI -70%
"dalam_sekali" (<=-60%) bukan kelompok seragam. Dipecah per 10 poin
kedalaman (bukan cuma dipotong di -40%/-60%), satu zona menonjol jelas dari
yang lebih dangkal MAUPUN yang lebih dalam -- jatuh 60-70% dari puncak:

    kalibrasi 2026, bergejolak, return H+20 vs baseline (tanpa dedup)
      -40~-30%   -0,89pp   crash>=30%  13,8%
      -50~-40%   +2,26pp              14,3%
      -60~-50%   +3,98pp              15,4%
      -70~-60%   +6,99pp   <- puncak   12,9%
      -80~-70%   +0,13pp              26,1%

    luar sampel 21 emiten 2016-2025 (Yahoo Finance, tanpa dedup)
      -70~-60%   n=74, return rata2 +36,1%, win 89,2%, crash>=30% 0%

Lewat -70%, kalibrasi 2026 menunjukkan hasilnya memburuk lagi DAN makin
liar (crash>=30% naik ke 26,1%, hampir menyamai rally-nya) -- bukan lagi
"murah dan siap mantul", lebih ke lempar koin taruhan besar. Sisi ini tidak
bisa diuji di luar sampel: 21 emiten besar itu tidak pernah jatuh sedalam
itu di datanya, jadi batas atasnya (kapan mulai memburuk lagi) baru
tervalidasi di SATU sampel.

Dua hal lain yang dicoba di zona ini dan HASILNYA:
- Hipotesis "bergejolak cuma menolong kalau sudah lewat -50%, sebelum itu
  tenang yang lebih baik" -- muncul di kalibrasi 2026 tapi TERBALIK ARAH
  di luar sampel (bergejolak menang di semua kedalaman). Dibuang, tidak
  dipakai jadi aturan -- contoh nyata pola yang cuma kebetulan di satu
  sampel.
- Status pemicu 'lewat' (6-20 hari) mengalahkan 'siap' (<=5 hari) di dalam
  zona ini, konsisten di dua sampel (+12,7% vs +5,3% kalibrasi; +45,4% vs
  +28,5% luar sampel). Sampel luar-sampelnya kecil (n=16-22), jadi belum
  dipakai mengubah urutan status -- dicatat sebagai petunjuk awal saja.

Angka di atas TIDAK di-dedup ke "hari pertama masuk zona" seperti tabel
BUKTI utama (lebih optimistis dari seharusnya, sama seperti batasan
overlap yang berlaku di semua modul lain), dan luar sampelnya ditarik
ULANG dari Yahoo Finance -- folder Test aslinya cuma berisi data broker,
tanpa OHLC. Dicek dulu terhadap angka resmi sebelum dipakai: replikasi
"jatuh>40%+bergejolak" dapat rata2 14,2% vs resmi 12,13% (BUKTI['sebaran'])
-- sepadan, bukan sumber yang identik persis.

BATASNYA, DAN INI HARUS DIBACA
- 80% setup ini TIDAK naik. Dari 529 kejadian "jatuh >60%" di 2026, cuma
  104 (20%) yang lanjut naik >=30% dalam 20 hari. APIC -15,0%, TPIA
  -14,7%, CUAN -10,1% berangkat dari setup yang sama persis.
- Pengamatannya tumpang tindih (hari bergeser satu-satu), jadi angka
  t di atas lebih optimistis daripada seharusnya.
- Semesta luar sampelnya cuma 21 emiten besar; emiten kecil tidak terwakili.
- BIAS SURVIVORSHIP masih tersisa. Emiten yang jatuh lalu disuspend
  permanen kehilangan return ke depannya, jadi hasil terburuk tidak ikut
  terhitung. Diukur: 13,1% pengamatan di zona jatuh <-40% tidak punya
  harga 20 hari kemudian (semua hari: 20,5%) -- jadi tidak terkonsentrasi
  di zona ini, tapi tetap ada. Emiten yang delisting sebelum periode data
  bahkan tidak muncul sama sekali dan tidak bisa diukur dari sini.
- Ini kecondongan populasi, bukan ramalan per emiten. Daftar di halaman
  ini daftar KANDIDAT PERIKSA, bukan daftar beli.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import logging
import os
import pickle
import time

import numpy as np
import pandas as pd

from .config import DAILY_PATH

logger = logging.getLogger(__name__)

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'jatuh_dalam_cache.pkl'))
# Jurnal maju pecahan R2 -- append-only, SENGAJA tidak bernama *_cache.
JURNAL_FILE = str(_runtime_file('', 'jatuh_dalam_jurnal.csv'))
KOLOM_JURNAL = ['tanggal', 'stock', 'close', 'dari_puncak', 'range20', 'bergejolak', 'likuid', 'value_b',
                'status', 'r2', 'beta', 'r2_asof', 'dicatat']
JURNAL_NILAI_MIN = 1.0    # Rp M/hari -- yang dinilai cuma >= ini, sama dengan semesta riset
JURNAL_JEDA = 20          # satu kejadian per emiten per 20 hari bursa, sama dengan riset
JURNAL_MIN_TANGGAL = 60   # tanggal sinyal matang minimal sebelum hasilnya ditampilkan
# Harapan dari sel validasi riset (emiten B 2020-26), vs pasar / alfa setelah beta.
HARAPAN_R2 = {20: {'sendiri': {'vs': -7.5, 'alfa': -7.8}, 'tengah': {'vs': -2.6, 'alfa': -1.3},
                   'pasar': {'vs': 1.2, 'alfa': 2.0}},
              60: {'sendiri': {'vs': -12.2, 'alfa': -13.2}, 'tengah': {'vs': -7.5, 'alfa': -4.5},
                   'pasar': {'vs': 2.1, 'alfa': 4.1}}}

C = {
    # 60, bukan 120. Versi pertama halaman ini memakai 120 hari karena
    # ditebak, bukan diuji. Waktu pencarian ciri diulang terbalik (30
    # ukuran, data yang memilih), `dari_puncak60` keluar di peringkat lebih
    # tinggi daripada `dari_puncak120` -- lalu diuji langsung sebagai
    # aturan screener dan menang di KEDUA sampel:
    #     luar sampel, return 20 hari vs pasar : 120h +4,54pp -> 60h +9,54pp
    #     kalibrasi 2026                       : 120h +2,71pp -> 60h +4,58pp
    # Menang di dua-duanya, jadi pilihannya bukan hasil mencocokkan diri
    # ke set luar sampel.
    #
    # Kenapa masuk akal: "jatuh 40% dari puncak 60 hari" berarti jatuhnya
    # BARU dan tajam. "Jatuh 40% dari puncak 120 hari" bisa berarti merosot
    # pelan setahun -- keadaan yang sama sekali beda.
    'PUNCAK_W': 60,       # jendela puncak acuan
    'RANGE_W': 20,        # jendela pengukur gejolak
    'DALAM': -40.0,       # ambang masuk zona
    'DALAM_SEKALI': -60.0,
    # Batas bawah "titik manis": -60% s/d -70% dari puncak. Dalam_sekali
    # (<=-60%) bukan kelompok seragam -- dipecah per 10 poin, zona -60~-70%
    # menonjol jelas dari yang lebih dangkal MAUPUN yang lebih dalam, di
    # DUA sampel terpisah (lihat TITIK MANIS di docstring atas + BUKTI
    # ['titik_manis'] di bawah). Lewat -70% hasilnya memburuk lagi dan
    # makin liar (crash>=30% ikut naik), jadi TIDAK diperlakukan sebagai
    # "makin dalam makin bagus" tanpa batas.
    'TITIK_MANIS': -70.0,
    'GEJOLAK_MIN': 25.0,  # rentang 20 hari >= ini = masih bergejolak
    'MIN_ADV': 200e6,     # Rp200 juta/hari, sama seperti pattern_miner
    'LIKUID_MIN': 2e9,    # Rp2 M/hari -- lihat SLIPPAGE di bawah
    'PEMICU_BARU': 5,     # pemicu dianggap masih "baru" sampai sekian hari
    'PEMICU_MAX': 20,     # lebih lama dari ini dianggap sudah lewat
}

# Ambang pembalikan pemicu. HARUS SAMA dengan PHASE_REVERSAL_PCT di
# utilities.py -- penanda segitiga di chart dan status di halaman ini
# memakai aturan yang sama persis, jadi kalau salah satu diubah yang lain
# ikut. Sengaja tidak diimpor dari utilities.py: modul itu mendaftarkan
# Blueprint dan mengimpor jatuh_dalam secara lazy di dalam route, jadi
# impor balik di tingkat modul bikin lingkaran yang rapuh.
PEMICU_PCT = 10.0

# Perkiraan slippage: order contoh Rp50 juta, dibatasi 15% ADV, dampak
# pasar linear terhadap (order/ADV) dengan koefisien 0,8 dan batas atas
# 15%. Konstanta ini disalin dari CFG milik saham_kering_idx.py -- model
# yang sama yang dipakai backtest Kering Screener.
#
# KENAPA INI DITAMPILKAN: diukur pada 457 sinyal Kering, slippage rata-rata
# 9,59% di emiten <Rp500 juta/hari tapi cuma 0,27% di >=Rp10 M/hari. Edge
# aturan di halaman ini sekitar 4-6%, jadi di emiten tipis ongkosnya
# MEMAKAN HABIS edge-nya sebelum apa pun terjadi. Slippage bukan risiko
# yang mungkin terjadi -- ia pasti dibayar, menang atau kalah.
ORDER_CONTOH = 50e6
SLIP_K = 0.8
SLIP_CAP = 0.15


def _slippage_pct(adv):
    """Perkiraan slippage sekali jalan untuk order ORDER_CONTOH."""
    if not adv or adv <= 0 or not np.isfinite(adv):
        return SLIP_CAP * 100
    order = min(ORDER_CONTOH, 0.15 * adv)
    return min(SLIP_K * order / adv, SLIP_CAP) * 100

# Angka hasil pengujian, ditaruh di sini supaya halaman menampilkan yang
# SAMA PERSIS dengan yang tertulis di docstring -- bukan angka yang
# diketik ulang di template dan bisa menyimpang diam-diam.
BUKTI = {
    # riset_pola_naik/jatuh_sendiri.py, 29 Okt 2026 -- lihat docstring. Definisi
    # riset: dd60 close <= -40% & rentang 20h >= 25%, emiten layak uji.py; satu
    # kejadian per emiten per 20 bar; vs pasar hari yang sama, 60 hari (t galat
    # per bulan) | absolut | naik | jatuh lagi >= 20%.
    'r2': {
        'sel': [
            {'kel': 'pasar', 'label': 'R² ≥ 0,15 — ikut pasar', 'baris': [
                {'sel': 'Pencarian (A 2013-19)', 'vs60': 8.7, 't': 4.4, 'abs60': 11.5, 'naik': 67, 'jatuh20': 8, 'n': 72},
                {'sel': 'Validasi (B 2020-26)', 'vs60': 2.1, 't': 1.1, 'abs60': 4.7, 'naik': 58, 'jatuh20': 19, 'n': 246},
                {'sel': 'Silang (B 2013-19)', 'vs60': 5.5, 't': 1.1, 'abs60': 7.1, 'naik': 64, 'jatuh20': 10, 'n': 50},
                {'sel': 'Silang (A 2020-26)', 'vs60': 4.7, 't': 1.8, 'abs60': 7.2, 'naik': 60, 'jatuh20': 20, 'n': 242},
            ]},
            {'kel': 'tengah', 'label': 'R² 0,05–0,15', 'baris': [
                {'sel': 'Pencarian (A 2013-19)', 'vs60': -4.1, 't': -0.9, 'abs60': -7.1, 'naik': 46, 'jatuh20': 38, 'n': 50},
                {'sel': 'Validasi (B 2020-26)', 'vs60': -7.5, 't': -3.6, 'abs60': -12.9, 'naik': 33, 'jatuh20': 39, 'n': 252},
                {'sel': 'Silang (B 2013-19)', 'vs60': -8.1, 't': -1.1, 'abs60': -11.0, 'naik': 50, 'jatuh20': 17, 'n': 30},
                {'sel': 'Silang (A 2020-26)', 'vs60': -2.7, 't': -0.9, 'abs60': -8.0, 'naik': 38, 'jatuh20': 33, 'n': 170},
            ]},
            {'kel': 'sendiri', 'label': 'R² < 0,05 — jalan sendiri', 'baris': [
                {'sel': 'Pencarian (A 2013-19)', 'vs60': -17.3, 't': -3.1, 'abs60': -24.7, 'naik': 24, 'jatuh20': 41, 'n': 34},
                {'sel': 'Validasi (B 2020-26)', 'vs60': -12.2, 't': -6.1, 'abs60': -15.4, 'naik': 34, 'jatuh20': 43, 'n': 344},
                {'sel': 'Silang (B 2013-19)', 'vs60': -23.6, 't': -3.4, 'abs60': -32.3, 'naik': 29, 'jatuh20': 46, 'n': 70},
                {'sel': 'Silang (A 2020-26)', 'vs60': -16.5, 't': -7.7, 'abs60': -20.2, 'naik': 26, 'jatuh20': 50, 'n': 370},
            ]},
        ],
        'alfa_pasar': ('Alfa setelah beta (return dikurangi beta 250 hari x pasar di jendela yang sama), kelompok '
                       'ikut pasar: +6,5 / +4,1 / +4,3 / +6,8% per 60 hari (t 3,5 / 2,1 / 0,8 / 4,3); positif '
                       '10 dari 12 tahun. Jalan sendiri: -13 s.d. -28%, negatif 12 dari 14 tahun.'),
        'porto': [
            {'strategi': 'Jatuh Dalam + R² ≥ 0,15', 'cagr': 7.3, 'cagr13': 7.6, 'cagr20': 6.8, 'dd': -45.5},
            {'strategi': 'Jatuh Dalam, semua', 'cagr': -18.3, 'cagr13': -14.3, 'cagr20': -24.5, 'dd': -95.5},
            {'strategi': 'Jatuh Dalam + R² < 0,05', 'cagr': -21.3, 'cagr13': -15.2, 'cagr20': -31.6, 'dd': -96.4},
            {'strategi': 'Beli semua emiten likuid (tanpa ongkos)', 'cagr': 4.8, 'cagr13': 4.1, 'cagr20': 5.7,
             'dd': -56.8, 'pembanding': True},
        ],
        'porto_catatan': ('10 slot, masuk close hari setelah sinyal, tahan 60 hari, ongkos pulang-pergi 0,9%. '
                          'Ikut pasar cuma 158 transaksi dalam 13 tahun -- portofolionya sering separuh kas. '
                          'Di atas beli-semua, tapi jauh di bawah Tembus Basis + trailing 10%.'),
        'batas': ('KALIBRASI, bukan teruji: arah R² sudah terlihat di keempat sel sebelum ambang 0,05/0,15 '
                  'dipilih (dari sebaran R², bukan dari hasil). Definisi riset sedikit beda dari daftar di '
                  'halaman ini. Jurnal maju di bawah yang menguji versi halaman. Emiten delisting tidak ada '
                  'di data -- paling mungkin di kelompok jalan sendiri.'),
    },
    # Uji ulang di semesta luas -- lihat bagian pertama docstring. Ditaruh
    # paling atas di halaman: semua tabel lain di bawahnya berasal dari
    # sampel yang ternyata bias hindsight.
    'uji_ulang': {
        'baris': [
            {'uji': '20 emiten folder Test, 2016-2025 (cara uji lama)',
             'hasil': '+14,58pp vs semua hari', 'baik': True},
            {'uji': 'Semua emiten likuid, 2016-2025 (cara uji lama)',
             'hasil': '-0,27pp vs semua hari; -1,56pp vs pasar hari yang sama', 'baik': False},
            {'uji': 'Semua emiten likuid, return majemuk',
             'hasil': '-2,99% per 20 hari (median -2,86%)', 'baik': False},
            {'uji': 'Validasi 2020-2026, separuh emiten yang tidak dipakai mencari',
             'hasil': '-7,5% per 60 hari vs pasar (t -5,6); negatif 9 dari 12 tahun', 'baik': False},
            {'uji': 'Portofolio 10 slot, tahan 60 hari, 2013-2026',
             'hasil': '-19,1% per tahun, drawdown -95,6%', 'baik': False},
        ],
        'catatan': ('Kenapa bisa beda sejauh itu: 20 emiten folder Test dipilih tahun 2026 karena besar '
                    'HARI INI, jadi setiap kejatuhan lama mereka -- menurut definisinya -- diikuti '
                    'pemulihan. Di semua emiten likuid, peluang naik >=10% memang lebih tinggi (26,2% vs '
                    '18,7%) karena emiten yang baru jatuh itu liar, tapi peluang turun >=10% lebih tinggi '
                    'lagi (36,2%). Tabel-tabel di bawah dibiarkan sebagai catatan: benar untuk sampel '
                    'tempat ia diuji, tidak berlaku umum.'),
    },
    'sampel_luar': '21 emiten, 2016-2025 (folder Test, periode & semesta terpisah)',
    'sampel_kalibrasi': '865 emiten, Jan-Sep 2026',
    'baris': [
        {'setup': 'Jatuh >40% dari puncak 60h', 'horizon': 'H+20',
         'luar_rally': 32.5, 'luar_return': 8.18, 'luar_t': 11.8,
         'kal_rally': 10.6, 'kal_return': 4.16, 'kal_t': 20.5},
        {'setup': 'Jatuh >40% dari puncak 60h + bergejolak', 'horizon': 'H+20',
         'luar_rally': 36.2, 'luar_return': 9.39, 'luar_t': 11.7,
         'kal_rally': 11.1, 'kal_return': 4.16, 'kal_t': 19.7},
        {'setup': 'Jatuh >40% dari puncak 120h (versi lama)', 'horizon': 'H+20',
         'luar_rally': 22.3, 'luar_return': 4.54, 'luar_t': 8.1,
         'kal_rally': 7.1, 'kal_return': 2.71, 'kal_t': 15.8},
    ],
    'gejolak': [
        {'varian': 'Jatuh >40% (60h) + MASIH bergejolak', 'rally': 36.2, 'return': 9.39},
        {'varian': 'Jatuh >40% (60h) + sudah melandai', 'rally': 17.6, 'return': 3.28},
    ],
    'gejolak_catatan': ('Angka luar sampel, H+20. Di kalibrasi 2026 selisihnya justru hilang '
                        '(+4,16pp vs +4,15pp) — begitu jendela puncaknya dipendekkan ke 60 hari, '
                        'syarat bergejolak jadi sebagian besar mubazir: yang baru jatuh 40% dalam '
                        '60 hari hampir pasti rentangnya lebar. Saringannya tetap dipasang karena '
                        'di luar sampel masih memisahkan, tapi jangan diandalkan sendirian.'),
    # Sebaran return 20 hari -- untuk menjawab "apakah cuma segelintir
    # peledak yang mengangkat rata-rata". Ternyata tidak: median ikut
    # bergerak dan sisi ruginya mengecil.
    'sebaran': [
        {'sampel': 'Luar sampel 2016-2025', 'kelompok': 'Semua hari',
         'rata2': 2.74, 'median': 0.00, 'rugi': 49.1},
        {'sampel': 'Luar sampel 2016-2025', 'kelompok': 'Jatuh >40% (60h)',
         'rata2': 10.92, 'median': 7.45, 'rugi': 37.3},
        {'sampel': 'Luar sampel 2016-2025', 'kelompok': '+ masih bergejolak',
         'rata2': 12.13, 'median': 9.69, 'rugi': 35.0},
        {'sampel': 'Kalibrasi 2026', 'kelompok': 'Semua hari',
         'rata2': -1.11, 'median': -0.41, 'rugi': 50.4},
        {'sampel': 'Kalibrasi 2026', 'kelompok': 'Jatuh >40% (60h)',
         'rata2': 3.05, 'median': 1.67, 'rugi': 45.2},
        {'sampel': 'Kalibrasi 2026', 'kelompok': '+ masih bergejolak',
         'rata2': 3.05, 'median': 1.64, 'rugi': 45.2},
    ],
    'survivorship': ('Bias survivorship masih tersisa: emiten yang jatuh lalu disuspend '
                     'permanen kehilangan return ke depannya, jadi hasil terburuk tidak '
                     'ikut terhitung. Diukur 13,1% pengamatan di zona jatuh >40% tidak '
                     'punya harga 20 hari kemudian (semua hari: 20,5%) — tidak '
                     'terkonsentrasi di zona ini, tapi ada. Emiten yang delisting sebelum '
                     'periode data bahkan tidak muncul sama sekali.'),
    # Menjawab keberatan yang wajar: "cirinya kan kamu yang menebak".
    # Betul -- karena itu pencariannya diulang TERBALIK: 30 ukuran
    # dihitung mekanis, tiap desilnya diuji (349 sel, dikoreksi FDR), lalu
    # data yang memilih. Hasilnya menunjuk keluarga ciri yang sama.
    'pemilihan_ciri': [
        {'ukuran': 'range60 (rentang 60 hari)', 'desil': 'tertinggi', 'kal_rally': 26.5,
         'luar_rally': 21.2, 'luar_return': 4.89, 'luar_t': 12.9, 'bertahan': True},
        {'ukuran': 'chg120 (perubahan 120 hari)', 'desil': 'terendah', 'kal_rally': 28.8,
         'luar_rally': 8.3, 'luar_return': 0.78, 'luar_t': 2.8, 'bertahan': True},
        {'ukuran': 'dari_puncak60', 'desil': 'terendah', 'kal_rally': 28.1,
         'luar_rally': 13.6, 'luar_return': 2.38, 'luar_t': 7.9, 'bertahan': True},
        {'ukuran': 'dari_puncak120', 'desil': 'terendah', 'kal_rally': 26.7,
         'luar_rally': 12.7, 'luar_return': 1.83, 'luar_t': 6.1, 'bertahan': True},
        {'ukuran': 'volat20 (volatilitas)', 'desil': 'tertinggi', 'kal_rally': 19.5,
         'luar_rally': 17.5, 'luar_return': 2.91, 'luar_t': 7.0, 'bertahan': True},
        {'ukuran': 'posisi60 (posisi di rentang)', 'desil': 'terendah', 'kal_rally': 19.2,
         'luar_rally': -0.4, 'luar_return': -0.18, 'luar_t': -0.8, 'bertahan': False},
    ],
    'pemilihan_catatan': ('30 ukuran x 10 desil = 349 sel diuji di kalibrasi 2026; 296 lolos '
                          'koreksi FDR. Data menunjuk dua keluarga ciri: "sudah jatuh dalam" '
                          'dan "rentang/volatilitas tinggi" — dua-duanya keluarga yang sama '
                          'dengan tebakan awal, jadi tebakan itu kebetulan benar, bukan '
                          'karena sudah diperiksa. posisi60 lolos FDR di kalibrasi tapi '
                          'GAGAL di luar sampel — bukti bahwa FDR saja memang tidak cukup.'),
    'volat_catatan': ('Satu hal yang TIDAK ketemu lewat tebakan: volatilitas menaikkan '
                      'PELUANG bergerak 30% di kedua sampel, tapi efeknya ke RETURN '
                      'rata-rata berbalik tanda antar rezim (+2,91pp di 2016-2025, '
                      '-4,63% di 2026 yang pasar turun). Jadi gejolak dipakai sebagai '
                      'saringan "akan bergerak", bukan klaim "akan untung".'),
    'tahun_konsisten': '8 dari 10 tahun (luar sampel, jatuh >40%)',
    'tingkat_gagal': ('Dari 529 kejadian "jatuh >60%" di 2026, hanya 104 (20%) '
                      'yang lanjut naik >=30% dalam 20 hari.'),
    'hipotesis_ditolak': ('"Melandai dulu baru naik banyak" diuji pada 15 kombinasi '
                          '(5 ambang datar x 3 horizon) di dua sampel dan gagal di '
                          'semuanya -- melandai justru menurunkan peluang rally '
                          '(H+60 luar sampel: -4,2pp peluang, -1,50pp return).'),

    # Inti halaman ini: MENUNGGU PEMICU lebih baik daripada langsung beli.
    # Diuji sebagai aturan utuh, bukan disimpulkan dari potongan-potongan.
    # Angka = return H+20 terhadap pasar di sampel masing-masing.
    'kombinasi': [
        {'aturan': 'Tanpa syarat (pembanding pasar)',
         'luar': 0.0, 'kal': 0.0, 'kal_likuid': 0.0, 'win': 50.0, 'sorot': False},
        {'aturan': 'Jatuh >40%, beli langsung',
         'luar': 7.96, 'kal': 3.17, 'kal_likuid': 3.56, 'win': 53.3, 'sorot': False},
        {'aturan': 'Pemicu saja, tanpa syarat jatuh',
         'luar': 1.85, 'kal': 0.74, 'kal_likuid': 1.58, 'win': 50.7, 'sorot': False},
        {'aturan': 'Jatuh >40% LALU tunggu pemicu',
         'luar': 9.94, 'kal': 5.21, 'kal_likuid': 5.85, 'win': 57.2, 'sorot': True},
    ],
    'kombinasi_catatan': ('Menunggu itu menguntungkan, bukan merugikan: walau masuk di harga '
                          'yang sudah naik 10%, hasilnya tetap lebih baik daripada beli di '
                          'titik terendah -- karena banyak yang jatuh terus jatuh, dan pemicu '
                          'menyaring yang benar-benar sudah berbalik. Pemicu SENDIRIAN lemah '
                          '(+1,58pp); ia cuma bekerja kalau emitennya memang sudah jatuh dalam '
                          'lebih dulu. Win rate 57-68% berarti 1 dari 3 tetap rugi.'),
    'slippage': [
        {'likuiditas': '< Rp500 juta/hari', 'slip': 9.59, 'net': -13.04},
        {'likuiditas': 'Rp0,5-2 M', 'slip': 3.36, 'net': -7.67},
        {'likuiditas': 'Rp2-10 M', 'slip': 0.92, 'net': -0.10},
        {'likuiditas': '>= Rp10 M', 'slip': 0.27, 'net': 5.97},
    ],
    'slippage_catatan': ('Diukur pada 457 sinyal Kering Screener, order Rp50 juta. Slippage '
                         'BUKAN risiko yang mungkin terjadi -- ia pasti dibayar, menang atau '
                         'kalah. Di emiten <Rp500 juta/hari ongkosnya ~10%, sementara edge '
                         'aturan ini cuma 4-6%: habis sebelum apa pun terjadi. Karena itu '
                         'saringan bawaan halaman ini Rp2 M/hari. Kalau order lo jauh lebih '
                         'kecil dari Rp50 juta, slippage-nya ikut mengecil dan ambang itu '
                         'boleh diturunkan.'),

    # TITIK MANIS -60% s/d -70%: dalam_sekali dipecah per 10 poin kedalaman
    # (bukan cuma dipotong di -60%), zona ini menonjol jelas di kalibrasi
    # MAUPUN luar sampel. Angka di sini TIDAK di-dedup ke "hari pertama
    # masuk zona" seperti tabel BUKTI utama -- exploratory, lebih optimistis
    # dari yang seharusnya, sama seperti keterbatasan overlap yang berlaku
    # di semua modul lain. Luar sampelnya ditarik ULANG dari Yahoo Finance
    # (folder Test aslinya cuma berisi data broker, tanpa OHLC) -- dicek
    # dulu terhadap angka resmi BUKTI['sebaran'] (jatuh>40%+bergejolak:
    # replikasi 14,2% vs resmi 12,13%, sepadan) sebelum dipakai.
    'titik_manis': [
        {'sampel': 'Kalibrasi 2026, -60~-70% + bergejolak', 'n': 1231,
         'return_h20': 5.66, 'vs_baseline': 6.99, 'win': 54.6, 'crash30': 12.9},
        {'sampel': 'Luar sampel 2016-2025, -60~-70% + bergejolak', 'n': 74,
         'return_h20': 36.13, 'vs_baseline': 32.82, 'win': 89.2, 'crash30': 0.0},
    ],
    'titik_manis_catatan': (
        'Lewat -70% (kalibrasi 2026), hasilnya memburuk lagi DAN makin liar -- '
        'crash>=30% naik ke 26,1%, hampir menyamai peluang rally-nya (bukan lagi '
        '"murah dan siap mantul", lebih ke lempar koin taruhan besar). Sisi ini '
        'tidak bisa diuji di luar sampel: 21 emiten besarnya tidak pernah jatuh '
        'sedalam itu di datanya. Dicoba juga hipotesis "bergejolak cuma penting '
        'kalau sudah lewat -50%" -- muncul di kalibrasi tapi TERBALIK ARAH di luar '
        'sampel, jadi dibuang, tidak dipakai jadi aturan. Dicoba juga: di dalam '
        'zona ini status \'lewat\' (pemicu 6-20 hari lalu) mengalahkan \'siap\' '
        '(<=5 hari) di dua sampel (+12,7% vs +5,3% kalibrasi; +45,4% vs +28,5% '
        'luar sampel) -- tapi sampelnya kecil (n=16-22 luar sampel), jadi belum '
        'dipakai mengubah urutan status, cuma dicatat sebagai petunjuk awal.'),
}


def _read(stock):
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
    try:
        df = pd.read_csv(path).fillna(0)
    except Exception:
        return None
    if df.empty or 'Date' not in df.columns:
        return None
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    return df if len(df) >= C['PUNCAK_W'] // 2 else None


def measure(stock, df=None):
    """Keadaan emiten ini pada bar TERAKHIR. None kalau tidak memenuhi syarat."""
    if df is None:
        df = _read(stock)
    if df is None or len(df) < 60:
        return None

    close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
    i = len(df) - 1
    harga = float(close.iloc[i])
    if harga <= 0:
        return None

    adv = float(close.iloc[-20:].mean() * vol.iloc[-20:].mean())
    if adv < C['MIN_ADV']:
        return None

    puncak = float(high.iloc[-C['PUNCAK_W']:].max())
    if puncak <= 0:
        return None
    dari_puncak = (harga / puncak - 1) * 100
    if dari_puncak > C['DALAM']:
        return None

    hi20 = float(high.iloc[-C['RANGE_W']:].max())
    lo20 = float(low.iloc[-C['RANGE_W']:].min())
    range20 = (hi20 - lo20) / lo20 * 100 if lo20 > 0 else 0.0

    # sudah berapa hari bursa beruntun berada di zona ini
    seri_puncak = high.rolling(C['PUNCAK_W'], min_periods=30).max()
    seri_dp = (close / seri_puncak - 1) * 100
    hari_zona = 0
    for v in reversed(seri_dp.tolist()):
        if pd.isna(v) or v > C['DALAM']:
            break
        hari_zona += 1

    def chg(n):
        if i - n < 0 or close.iloc[i - n] <= 0:
            return None
        return round((harga / float(close.iloc[i - n]) - 1) * 100, 2)

    # --- PEMICU: bagian yang membedakan "sudah jatuh" dari "siap masuk" ---
    #
    # Aturannya identik dengan penanda segitiga di chart (utilities.py
    # _fase_ayunan): sentuhan PERTAMA harga ke +/-PEMICU_PCT dari ekstrem
    # 20 hari, dihitung dari CLOSE (bukan High/Low), dan status "aktif"
    # direset begitu harga balik melewati ambangnya.
    c = close.tolist()
    pemicu_hari = keluar_hari = None
    naik_aktif = turun_aktif = False
    for j in range(19, len(c)):
        if c[j] <= 0:
            continue
        jendela = c[j - 19:j + 1]
        hi, lo = max(jendela), min(jendela)
        naik = (c[j] / lo - 1) * 100 if lo > 0 else 0.0
        turun = (c[j] / hi - 1) * 100 if hi > 0 else 0.0
        if naik >= PEMICU_PCT:
            if not naik_aktif:
                pemicu_hari = i - j
            naik_aktif = True
        else:
            naik_aktif = False
        if turun <= -PEMICU_PCT:
            if not turun_aktif:
                keluar_hari = i - j
            turun_aktif = True
        else:
            turun_aktif = False

    # Status = gabungan keadaan + pemicu, persis kombinasi yang diuji.
    # 'keluar' menang atas 'siap': kalau sinyal keluar datang SETELAH
    # pemicu masuk, pembalikannya sudah batal.
    if keluar_hari is not None and (pemicu_hari is None or keluar_hari < pemicu_hari):
        status = 'keluar'
    elif pemicu_hari is None or pemicu_hari > C['PEMICU_MAX']:
        status = 'menunggu'
    elif pemicu_hari <= C['PEMICU_BARU']:
        status = 'siap'
    else:
        status = 'lewat'

    # Tanggal kalender buat penanda "Signal" di chart (?focus=) -- frontend
    # nggak punya kalender bursa sendiri, jadi tanggalnya dihitung di sini,
    # bukan dari pemicu_hari/hari_zona (jumlah hari BURSA) di JS.
    pemicu_date = (df['Date'].iloc[i - pemicu_hari].strftime('%Y-%m-%d')
                   if pemicu_hari is not None else None)
    zona_masuk_idx = i - hari_zona + 1 if hari_zona > 0 else i
    zona_masuk_date = (df['Date'].iloc[zona_masuk_idx].strftime('%Y-%m-%d')
                       if 0 <= zona_masuk_idx < len(df) else None)

    return {
        'stock': stock,
        'date': df['Date'].iloc[i].strftime('%Y-%m-%d'),
        'close': harga,
        'dari_puncak': round(dari_puncak, 1),
        'puncak_60h': round(puncak, 1),
        'range20': round(range20, 1),
        'bergejolak': bool(range20 >= C['GEJOLAK_MIN']),
        'tier': 'dalam_sekali' if dari_puncak <= C['DALAM_SEKALI'] else 'dalam',
        # Sub-penanda di dalam dalam_sekali -- lihat catatan TITIK_MANIS di C.
        'titik_manis': bool(C['TITIK_MANIS'] < dari_puncak <= C['DALAM_SEKALI']),
        'hari_zona': int(hari_zona),
        'pemicu_hari': int(pemicu_hari) if pemicu_hari is not None else None,
        'keluar_hari': int(keluar_hari) if keluar_hari is not None else None,
        'pemicu_date': pemicu_date,
        'zona_masuk_date': zona_masuk_date,
        'status': status,
        'slippage_pct': round(_slippage_pct(adv), 2),
        'likuid': bool(adv >= C['LIKUID_MIN']),
        'value_b': round(adv / 1e9, 2),
        'chg20': chg(20),
        'chg60': chg(60),
    }


def _muat_jurnal():
    """Berkas yang ada tapi tak terbaca -> melempar, BUKAN kosong (sama dengan
    kecondongan._muat_jurnal): penulis tidak boleh mengira jurnalnya kosong."""
    j = (pd.read_csv(JURNAL_FILE, dtype={'tanggal': str, 'stock': str, 'status': str, 'r2_asof': str})
         if os.path.exists(JURNAL_FILE) else pd.DataFrame(columns=KOLOM_JURNAL))
    if len(j):
        j = j.drop_duplicates(['tanggal', 'stock'], keep='first')
    return j


def catat(rows, hari_pasar, r2_asof):
    """Kandidat hari ini + R2/beta-nya. Idempoten per (tanggal, emiten)."""
    tanggal = hari_pasar.strftime('%Y-%m-%d')
    try:
        lama = _muat_jurnal()
    except Exception as exc:
        logger.exception('Jurnal Jatuh Dalam tidak terbaca -- tidak menulis apa pun')
        return {'tanggal': tanggal, 'tercatat': 0, 'pesan': 'jurnal tidak terbaca: %s' % exc}
    sudah = set(lama.loc[lama['tanggal'] == tanggal, 'stock']) if len(lama) else set()
    sekarang = time.strftime('%Y-%m-%d %H:%M')
    baru = [{'tanggal': tanggal, 'stock': r['stock'], 'close': r['close'], 'dari_puncak': r['dari_puncak'],
             'range20': r['range20'], 'bergejolak': int(r['bergejolak']), 'likuid': int(r['likuid']),
             'value_b': r['value_b'], 'status': r['status'], 'r2': r.get('r2'), 'beta': r.get('beta'),
             'r2_asof': r2_asof, 'dicatat': sekarang}
            for r in rows if r['stock'] not in sudah]
    if baru:
        pd.DataFrame(baru, columns=KOLOM_JURNAL).to_csv(JURNAL_FILE, mode='a', index=False,
                                                        header=not os.path.exists(JURNAL_FILE))
    return {'tanggal': tanggal, 'tercatat': len(baru), 'sudah_ada': len(sudah)}


def _kalender(muatan):
    """Hari bursa = tanggal yang muncul di >= 25% berkas (sama dengan tembus_basis._kalender)."""
    hitung = {}
    for _, df in muatan:
        for d in df['Date']:
            hitung[d] = hitung.get(d, 0) + 1
    ambang = max(1, int(len(muatan) * 0.25))
    return pd.DatetimeIndex(sorted(d for d, n in hitung.items() if n >= ambang))


def evaluasi(muatan, hari_pasar):
    """Kandidat jurnal yang sudah matang, per kelompok R2: vs pasar hari yang sama
    dan alfa setelah beta. Yang dinilai: bergejolak, >= Rp1 M/hari, satu kejadian
    per emiten per 20 hari bursa -- sedekat mungkin dengan semesta riset."""
    from .kecondongan import kelompok_r2, R2_LABEL
    try:
        j = _muat_jurnal()
    except Exception as exc:
        return {'available': False, 'message': 'Jurnal tidak terbaca: %s' % exc}
    cakupan = {'n_baris': int(len(j)), 'n_hari': int(j['tanggal'].nunique()) if len(j) else 0,
               'mulai': str(j['tanggal'].min()) if len(j) else None}
    if j.empty:
        return {'available': True, 'cakupan': cakupan, 'horizon': [], 'pesan': 'Jurnal baru dimulai.'}

    kal = _kalender(muatan)
    pos = {d: i for i, d in enumerate(kal)}
    akhir = pos.get(hari_pasar, len(kal) - 1)
    tutup = pd.DataFrame({s: df.set_index('Date')['Close'] for s, df in muatan}).reindex(kal)
    tutup = tutup.where(tutup > 0)
    vol = pd.DataFrame({s: df.set_index('Date')['Volume'] for s, df in muatan}).reindex(kal)
    nilai20 = (tutup * vol).rolling(20, min_periods=20).median()
    likuid = (nilai20 >= 1e9) & (tutup >= 100)
    loncat_cs = (tutup.pct_change(fill_method=None).abs() > 0.45).astype(float).cumsum()

    j = j.copy()
    for kol in ('r2', 'beta', 'value_b', 'bergejolak'):
        j[kol] = pd.to_numeric(j[kol], errors='coerce')
    j['p'] = pd.to_datetime(j['tanggal']).map(pos)
    j = j.dropna(subset=['p'])
    j['p'] = j['p'].astype(int)
    j = j[(j['bergejolak'] == 1) & (j['value_b'] >= JURNAL_NILAI_MIN)].sort_values(['stock', 'p'])
    simpan, terakhir = [], {}
    for idx, s, p in zip(j.index, j['stock'], j['p']):
        if p - terakhir.get(s, -10 ** 9) >= JURNAL_JEDA:
            simpan.append(idx)
            terakhir[s] = p
    ev = j.loc[simpan].copy()
    ev['kel'] = [kelompok_r2(v) for v in ev['r2']]
    cakupan['n_kejadian'] = int(len(ev))

    hasil = []
    kol = {s: i for i, s in enumerate(tutup.columns)}
    for hz in (20, 60):
        lr = np.log(tutup.shift(-(hz + 1)) / tutup.shift(-1)).mask(
            (loncat_cs.shift(-(hz + 1)) - loncat_cs) > 0)
        pasar = lr.where(likuid).mean(axis=1).to_numpy()
        arr = lr.to_numpy()
        m = ev[ev['p'] + hz + 1 <= akhir].copy()
        r = {'horizon': hz, 'harapan': HARAPAN_R2[hz], 'n_tanggal': int(m['tanggal'].nunique()), 'kelompok': []}
        if len(m):
            m['x'] = [arr[p, kol[s]] if s in kol else np.nan for p, s in zip(m['p'], m['stock'])]
            m['b'] = pasar[m['p'].to_numpy()]
            m = m[np.isfinite(m['x']) & np.isfinite(m['b'])]
            m['exc'] = m['x'] - m['b']
            m['alfa'] = m['x'] - m['beta'] * m['b']
            for kel in ('pasar', 'tengah', 'sendiri'):
                g = m[m['kel'] == kel]
                ga = g['alfa'].dropna()
                r['kelompok'].append({'kel': kel, 'label': R2_LABEL[kel], 'n': int(len(g)),
                                      'exc': _num((np.exp(g['exc'].mean()) - 1) * 100) if len(g) else None,
                                      'alfa': _num((np.exp(ga.mean()) - 1) * 100) if len(ga) else None})
        r['cukup'] = r['n_tanggal'] >= JURNAL_MIN_TANGGAL
        hasil.append(r)
    return {'available': True, 'cakupan': cakupan, 'horizon': hasil, 'min_tanggal': JURNAL_MIN_TANGGAL}


def _num(v):
    return round(float(v), 2) if v is not None and np.isfinite(v) else None


def _bangun():
    # Dibaca dulu semuanya supaya hari bursa terakhir PASAR bisa
    # ditentukan -- tanpa itu tidak ada acuan untuk menilai bar mana yang
    # basi (lihat "KENAPA BAR BASI DIBUANG" di atas).
    muatan = []
    for path in sorted(glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv'))):
        stock = os.path.basename(path).split('_')[0]
        df = _read(stock)
        if df is not None:
            muatan.append((stock, df))

    if not muatan:
        return {'available': False, 'message': 'Tidak ada berkas Summary yang bisa dibaca.'}

    hari_pasar = max(df['Date'].iloc[-1] for _, df in muatan)

    rows = []
    diperiksa = 0
    dilewati_basi = 0
    for stock, df in muatan:
        if df['Date'].iloc[-1] != hari_pasar:
            dilewati_basi += 1
            continue
        diperiksa += 1
        r = measure(stock, df)
        if r:
            rows.append(r)

    # R2 & beta 250 hari dari cache Skor Kecondongan (halaman ini tidak
    # membangun panel harga sendiri). Kalau cache-nya dari hari sebelumnya,
    # tanggalnya ikut ditampilkan -- R2 250 hari nyaris tidak bergeser sehari.
    try:
        from .kecondongan import r2_cache, kelompok_r2
        r2_asof, r2_semua, beta_semua = r2_cache()
    except Exception:
        logger.exception('R2 dari cache Kecondongan tidak terbaca')
        r2_asof, r2_semua, beta_semua, kelompok_r2 = None, {}, {}, (lambda v: None)
    for r in rows:
        r['r2'] = r2_semua.get(r['stock'])
        r['beta'] = beta_semua.get(r['stock'])
        r['r2_kel'] = kelompok_r2(r['r2']) if r['r2'] is not None else None

    # Urutan: kelompok R2 lebih dulu -- satu-satunya pemisah yang bertahan di
    # semesta luas (lihat PECAHAN R2 di docstring): ikut pasar > tengah/tanpa
    # R2 > jalan sendiri. Sesudah itu kombinasi lama: status pemicu (siap >
    # lewat > menunggu > keluar), likuiditas (slippage memakan edge di emiten
    # tipis), baru kedalaman jatuhnya.
    urut_r2 = {'pasar': 0, 'tengah': 1, None: 1, 'sendiri': 2}
    urut_status = {'siap': 0, 'lewat': 1, 'menunggu': 2, 'keluar': 3}
    rows.sort(key=lambda r: (urut_r2.get(r['r2_kel'], 1), urut_status.get(r['status'], 9), not r['likuid'],
                             r['pemicu_hari'] if r['pemicu_hari'] is not None else 99,
                             r['dari_puncak']))

    try:
        dicatat = catat(rows, hari_pasar, r2_asof)
    except Exception as exc:
        logger.exception('Gagal mencatat jurnal Jatuh Dalam')
        dicatat = {'tercatat': 0, 'pesan': 'gagal: %s' % exc}
    try:
        jurnal = evaluasi(muatan, hari_pasar)
    except Exception as exc:
        logger.exception('Gagal mengevaluasi jurnal Jatuh Dalam')
        jurnal = {'available': False, 'message': 'Gagal mengevaluasi: %s' % exc}

    return {
        'r2_asof': r2_asof,
        'n_r2': {k: sum(1 for r in rows if r['r2_kel'] == k) for k in ('pasar', 'tengah', 'sendiri')},
        'catat': dicatat, 'jurnal': jurnal,
        'available': True,
        'as_of': hari_pasar.strftime('%Y-%m-%d'),
        'n_diperiksa': diperiksa,
        'n_basi': dilewati_basi,
        'n_kandidat': len(rows),
        'n_dalam_sekali': sum(1 for r in rows if r['tier'] == 'dalam_sekali'),
        'n_titik_manis': sum(1 for r in rows if r['titik_manis']),
        'n_bergejolak': sum(1 for r in rows if r['bergejolak']),
        'n_siap': sum(1 for r in rows if r['status'] == 'siap'),
        'n_likuid': sum(1 for r in rows if r['likuid']),
        'n_siap_likuid': sum(1 for r in rows if r['status'] == 'siap' and r['likuid']),
        'rows': rows,
        'config': dict(C),
        'bukti': BUKTI,
        'dibangun': time.strftime('%Y-%m-%d %H:%M'),
        'from_cache': False,
    }


def _sumber_terbaru():
    from .kesegaran import summary_terbaru
    return summary_terbaru()


def scan(force=False):
    """
    Daftar kandidat pada hari bursa terakhir.

    Di-cache terhadap mtime berkas Summary terbaru -- memindai ~880 berkas
    makan puluhan detik, dan halaman ini dibuka berkali-kali sehari.
    """
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                simpan = pickle.load(fh)
            if simpan.get('ts', 0) >= _sumber_terbaru():
                hasil = dict(simpan['result'])
                hasil['from_cache'] = True
                # BUKTI itu teks dari kode, bukan hasil hitungan -- selalu
                # yang terbaru, supaya koreksi di BUKTI langsung tampil tanpa
                # menunggu unduhan besok membasikan cache-nya.
                hasil['bukti'] = BUKTI
                return hasil
        except Exception:
            pass

    hasil = _bangun()
    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'result': hasil}, fh)
    except Exception:
        logger.exception('Gagal menyimpan cache Jatuh Dalam')
    return hasil
