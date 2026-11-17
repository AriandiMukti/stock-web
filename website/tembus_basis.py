"""
Tembus Basis: emiten yang keluar dari basis harga tenang, atau mencetak
harga penutupan tertinggi 52 minggu -- dua-duanya dengan volume di atas 2x
rata-rata.

KENAPA INI ADA
==============
Pertanyaan aslinya: "saham yang harganya tenang 30 hari, apakah lebih
mungkin naik?" Diuji di ~750 emiten likuid 2013-2026 dan jawabannya TIDAK.
Harga tenang justru MENURUNKAN peluang naik >=10% dalam sebulan: 10,9%
lawan 18,7% di sampel validasi, konsisten di keempat sel uji dan hampir
semua tahun. Arahnya sama dengan hipotesis "melandai dulu, baru naik
banyak" yang sudah gagal di jatuh_dalam.py -- bedanya, dulu diuji di 21
emiten, sekarang di semesta ~35 kali lebih besar.

Emiten yang tenang memang jarang jatuh 10% (9,4% lawan 21,1%), jadi ia
sedikit mengalahkan emiten rata-rata. Tapi ia TENANG, bukan NAIK. Sebagai
portofolio setelah ongkos hasilnya sekitar nol per tahun.

Yang bertahan bukan KEADAAN tenangnya, tapi SAAT basis tenang itu
DITEMBUS -- dan paling kuat kalau tembusnya sekaligus puncak 52 minggu.

CARA UJINYA
===========
Kode risetnya di riset_pola_naik/ (lihat docstring paket itu):
  - Harga: cache Yahoo Finance di research_cache (888 emiten, 2012 s.d.
    8 Sep 2026). Hanya emiten likuid: median nilai transaksi 20 hari
    >= Rp1 M, harga >= Rp100, diperdagangkan >= 90% hari. Tanpa saringan
    ini "tenang" kebanyakan berarti tidak ada yang bertransaksi, atau
    harga yang tertahan di Rp50.
  - PENCARIAN di separuh emiten (paritas md5 kodenya) 2013-2019,
    VALIDASI di separuh LAIN 2020-2026 -- periode DAN semesta terpisah.
  - Masuk di close hari bursa SETELAH sinyal; satu sinyal per emiten per
    20 hari; return dimajemukkan (rata-rata log), dibandingkan dengan
    emiten likuid lain PADA HARI YANG SAMA supaya pola yang kebetulan
    muncul di pasar naik tidak mendapat kredit dari pasarnya.
  - Sekitar 40 pola diuji; yang gagal ikut dilaporkan.

BUKTI (sel validasi: separuh emiten yang tidak dipakai mencari, 2020-2026)
==========================================================================
                                   n   naik>=10%  +10% dulu   vs pasar
                                       dlm 20h    sblm -10%   60 hari
    semua hari (pembanding)     8.638    18,7%      47,3%     -0,1%
    tenang: rentang 30h <15%    2.687    10,9%      50,1%     +2,7%
    TEMBUS BASIS (<20%) + vol    827    20,9%      56,5%     +4,7% (t 4,7)
    PUNCAK 52 MINGGU + vol        841    26,8%      55,4%     +2,7% (t 1,7)
    KEDUANYA sekaligus *          246    21,5%      62,9%     +7,1% (t 3,3)
    Jatuh Dalam (pembanding)      820    26,2%      36,6%     -7,5% (t -5,6)

  * dipilih SETELAH data validasi dilihat -- buktinya lebih lemah. Jurnal
    maju di bawah yang mengujinya dengan jujur.

Tembus basis dan puncak 52 minggu positif terhadap pasar 13 dari 14 tahun
(2013-2026, semua emiten). Puncak 52 minggu punya peluang +10% tertinggi,
tapi peluang -10%-nya juga naik (25,4%): taruhan gejolak yang condong ke
atas, bukan jaminan.

Sebagai portofolio (10 slot, tahan 60 hari, ongkos pulang-pergi 0,9%):
puncak 52 minggu ~18,6%/tahun 2013-2026, keduanya ~19,0%, beli semua emiten
3,7%, IHSG 3,0%. Tahan diuji terhadap urutan pengisian slot, ongkos dua kali
lipat, dan jumlah slot. TAPI win per transaksi cuma ~47% dan median
transaksinya sedikit negatif: tanpa 10 transaksi terbaik (JARR +1205%, MSIN
+483%, ...) hasilnya kembali ke kisaran beli-semua. Untungnya dari ekor
kanan -- ambil SEMUA sinyal, potong yang rugi, biarkan yang untung jalan.

ARUS BROKER TIDAK MENAMBAH APA PUN
Top5 akumulasi vs distribusi, asing beli vs jual, ritel beli vs jual,
jumlah pembeli vs penjual -- diuji di 21 emiten folder Test 2016-2026 dan
~850 emiten 2026, sendirian maupun di atas pola tenang dan pola tembus.
Tidak ada yang memisahkan secara konsisten. Sejalan dengan temuan lama
bahwa sumbu arus tidak punya daya pisah (lihat _fase_ayunan di
utilities.py).

KENAPA DUA SUMBER HARGA
=======================
Puncak 52 minggu butuh 250 hari bursa ke belakang; berkas Summary baru
mulai Januari 2026. Sebelum tanggal pertama Summary tiap emiten, harganya
diambil dari riwayat Yahoo (tembus_basis_riwayat_cache.pkl, dibangun sekali
dari research_cache atau diunduh ulang). Summary sendiri harganya DARI
Yahoo juga (SummaryActivityDaily.py), jadi sambungannya hampir mulus --
diukur: rasio close Summary/Yahoo 1,0000 di BBRI/ADRO/TLKM/ANTM/SIDO, 1,0039
di BBCA. Rasio itu tetap dipakai menyetarakan riwayat per emiten. Sekitar
Januari 2027 Summary sudah cukup panjang sendiri dan riwayat tidak dipakai
lagi.

Hari yang TIDAK punya baris Summary (tidak ada data broker hari itu)
dianggap hari tanpa transaksi: harga ditahan, volume nol -- sama dengan
cara Yahoo menulis hari tanpa transaksi di data risetnya. Saringan
"diperdagangkan >= 90% hari" lalu menyingkirkan emiten yang sering bolong.

JURNAL MAJU
===========
Angka di atas tetap angka masa lalu. Tiap hari bursa, sinyal hari itu
ditulis ke tembus_basis_jurnal.csv SEBELUM hasilnya ada, lalu diukur 20 dan
60 hari bursa kemudian terhadap pasar hari yang sama. Yang dicatat bukan
cuma yang lolos aturan, tapi SEMUA emiten layak yang menembus tertinggi 30
hari atau mencetak puncak 52 minggu, dengan ukuran mentahnya -- supaya
ambang yang digeser belakangan tetap bisa diuji terhadap catatan lama
(alasan yang sama dengan pola_jurnal.py).

tembus_basis_hari.csv mencatat hari mana saja jurnalnya jalan. Tanpa itu,
hari tanpa satu pun sinyal tidak bisa dibedakan dari hari jurnalnya mati.
Keduanya append-only dan SENGAJA tidak bernama *_cache: cache bisa dibangun
ulang, jurnal tidak.

BATASNYA
========
- Data Yahoo cuma berisi emiten yang MASIH tercatat. Emiten yang delisting
  hilang beserta kerugiannya, jadi semua angka di atas agak terlalu
  optimistis -- paling parah untuk pola kejatuhan, paling ringan untuk
  pola puncak.
- Efeknya paling besar di emiten Rp1-5 M/hari, persis tempat slippage
  sungguhan lebih mahal dari yang dimodelkan.
- Bahkan yang terbaik cuma menggeser "+10% sebelum -10%" dari ~47% ke
  ~56-63%. Tidak ada pola yang peluangnya "tinggi".
- Ini kecondongan populasi, bukan ramalan per emiten. Daftar di halaman
  ini daftar KANDIDAT, dan aturan yang diuji menuntut SEMUA sinyal diambil.
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

HERE = os.path.dirname(__file__)
SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'tembus_basis_cache.pkl'))
RIWAYAT_FILE = str(_runtime_file('', 'tembus_basis_riwayat_cache.pkl'))
RESEARCH_CACHE = str(_runtime_file('', 'research_cache'))
JURNAL_FILE = str(_runtime_file('', 'tembus_basis_jurnal.csv'))
HARI_FILE = str(_runtime_file('', 'tembus_basis_hari.csv'))

# SAMA PERSIS dengan yang diuji di riset_pola_naik/. Menggeser satu angka
# di sini berarti halaman ini menampilkan aturan yang TIDAK pernah diuji --
# BUKTI di bawah jadi tidak berlaku untuknya.
C = {
    'BASIS_W': 30,        # jendela basis, hari bursa SEBELUM hari tembus
    'BASIS_MAX': 0.20,    # rentang basis (tertinggi-terendah)/close < 20%
    'VOL_W': 20,          # pembanding volume: rata-rata 20 hari SEBELUMNYA
    'VOL_X': 2.0,         # volume hari sinyal > 2x pembanding
    'PUNCAK_W': 250,      # 52 minggu = 250 hari bursa
    'MIN_RIWAYAT': 260,   # bar minimal sebelum emiten dinilai
    'MIN_HARGA': 100.0,   # Rp; di bawah ini fraksi harga & "gocap" merusak ukuran rentang
    'MIN_NILAI': 1e9,     # median nilai transaksi 20 hari, Rp
    'MIN_AKTIF': 0.9,     # porsi hari bervolume dalam 30 hari
    'LONCAT': 0.45,       # |gerak 1 hari| di atas ini mustahil di BEI -> aksi korporasi / data rusak
    'BERSIH_W': 60,       # jendela yang harus bebas loncatan
    'JEDA': 20,           # satu sinyal per emiten per 20 hari bursa (sama dgn riset)
    'TAHAN': 60,          # horizon utama yang diuji
    'UMUR_MAX': 5,        # sinyal sampai 5 hari bursa ke belakang ditampilkan
}

# Angka hasil pengujian, ditaruh di sini supaya halaman menampilkan yang
# SAMA PERSIS dengan docstring -- bukan angka yang diketik ulang di template.
BUKTI = {
    'sampel': ('~750 emiten likuid (median nilai >= Rp1 M/hari, harga >= Rp100), '
               'Yahoo Finance 2013 - Sep 2026. Dicari di separuh emiten 2013-2019, '
               'divalidasi di separuh LAIN 2020-2026.'),
    # Sel validasi. vs_pasar = return majemuk 60 hari dikurangi emiten likuid
    # lain yang dibeli di hari yang sama.
    'validasi': [
        {'kunci': 'pembanding', 'pola': 'Semua hari (pembanding)', 'n': 8638, 'naik60': 42.4,
         'p10': 18.7, 'm10': 21.1, 'dulu10': 47.3, 'median60': -3.1, 'vs_pasar': -0.1, 't': -0.3},
        {'kunci': 'tenang15', 'pola': 'Tenang: rentang 30 hari <15%', 'n': 2687, 'naik60': 45.4,
         'p10': 10.9, 'm10': 9.4, 'dulu10': 50.1, 'median60': -1.2, 'vs_pasar': 2.7, 't': 4.0},
        {'kunci': 'tenang10', 'pola': 'Tenang: rentang 30 hari <10%', 'n': 1097, 'naik60': 45.1,
         'p10': 7.5, 'm10': 8.1, 'dulu10': 49.2, 'median60': -1.0, 'vs_pasar': 3.1, 't': 3.4},
        {'kunci': 'basis', 'pola': 'Tembus basis <20% + volume >2x', 'n': 827, 'naik60': 49.9,
         'p10': 20.9, 'm10': 14.3, 'dulu10': 56.5, 'median60': 0.0, 'vs_pasar': 4.7, 't': 4.7},
        {'kunci': 'puncak', 'pola': 'Puncak 52 minggu + volume >2x', 'n': 841, 'naik60': 47.8,
         'p10': 26.8, 'm10': 25.4, 'dulu10': 55.4, 'median60': -0.9, 'vs_pasar': 2.7, 't': 1.7},
        {'kunci': 'keduanya', 'pola': 'Keduanya sekaligus *', 'n': 246, 'naik60': 52.3,
         'p10': 21.5, 'm10': 13.0, 'dulu10': 62.9, 'median60': 1.0, 'vs_pasar': 7.1, 't': 3.3},
        {'kunci': 'jatuh', 'pola': 'Jatuh Dalam (pembanding)', 'n': 820, 'naik60': 37.6,
         'p10': 26.2, 'm10': 36.2, 'dulu10': 36.6, 'median60': -10.7, 'vs_pasar': -7.5, 't': -5.6},
    ],
    'validasi_catatan': ('* Kombinasi "keduanya" dipilih SETELAH data validasi dilihat, jadi '
                         'buktinya lebih lemah -- jurnal maju yang mengujinya. "+10% dulu sblm '
                         '-10%" dihitung dari emiten yang menyentuh salah satunya dalam 60 hari.'),
    # vs pasar 60 hari di keempat sel. Sel "silang" berbagi satu dimensi
    # dengan pencarian (periode ATAU emiten), jadi bukan uji luar sampel
    # penuh -- dipakai untuk melihat apakah arahnya bertahan di mana-mana.
    'empat_sel': [
        {'pola': 'Tembus basis + volume', 'cari': 1.63, 'validasi': 4.69, 'silang_b': 3.16, 'silang_a': 2.49},
        {'pola': 'Puncak 52 minggu + volume', 'cari': 5.19, 'validasi': 2.74, 'silang_b': 3.76, 'silang_a': 2.94},
        {'pola': 'Keduanya sekaligus *', 'cari': 3.94, 'validasi': 7.09, 'silang_b': 5.10, 'silang_a': 5.23},
        {'pola': 'Tenang <15% (pembanding)', 'cari': 0.53, 'validasi': 2.67, 'silang_b': 1.65, 'silang_a': 3.08},
    ],
    'tahun': ('Terhadap pasar, per tahun sinyal 2013-2026 (semua emiten, 60 hari): tembus basis '
              '13/14 tahun positif, puncak 52 minggu 13/14, tenang <15% 11/14 tapi naik-turun '
              '(-3,0 di 2020, +13,3 di 2026), Jatuh Dalam cuma 4/13.'),
    # Simulasi: modal dibagi 10 slot, beli di close hari setelah sinyal,
    # tahan 60 hari bursa. Ongkos 0,15% beli + 0,25% jual + slippage 0,25%
    # per sisi = 0,9% pulang-pergi.
    'portofolio': [
        {'strategi': 'Puncak 52 minggu + volume', 'cagr': 18.6, 'cagr_val': 18.3, 'dd': -44.9, 'win': 47.3},
        {'strategi': 'Keduanya sekaligus *', 'cagr': 19.0, 'cagr_val': 35.1, 'dd': -35.8, 'win': 48.8},
        {'strategi': 'Tembus basis + volume + tutup kuat', 'cagr': 3.9, 'cagr_val': -2.9, 'dd': -43.1, 'win': 46.3},
        {'strategi': 'Tenang <15%', 'cagr': -0.5, 'cagr_val': -1.3, 'dd': -56.4, 'win': 45.5},
        {'strategi': 'Jatuh Dalam', 'cagr': -19.1, 'cagr_val': -27.3, 'dd': -95.6, 'win': 37.0},
        {'strategi': 'Beli semua emiten layak (tanpa ongkos)', 'cagr': 3.7, 'cagr_val': 8.3, 'dd': -64.7, 'win': None},
        {'strategi': 'IHSG', 'cagr': 3.0, 'cagr_val': 0.5, 'dd': -41.5, 'win': None},
    ],
    'portofolio_catatan': ('Tahan diuji: urutan pengisian slot diacak 10 kali (puncak 16,5-25,6%/tahun), '
                           'ongkos dua kali lipat (16,6%), 5 atau 20 slot. TAPI win per transaksi cuma '
                           '~47% dan median transaksinya sedikit negatif. Tanpa 10 transaksi terbaik '
                           '(JARR +1205%, MSIN +483%, ...) hasilnya kembali ke kisaran beli-semua. '
                           'Artinya: ambil SEMUA sinyal, potong yang rugi, biarkan yang untung jalan '
                           '-- memilih-milih atau ambil untung cepat membunuh edge-nya. Tembus basis '
                           'TANPA puncak baru cuma setara beli-semua sebagai portofolio: pemenang '
                           'besarnya datang dari puncak baru.'),
    'arus': ('Arus broker tidak menambah apa pun: Top5 akumulasi vs distribusi, asing beli vs jual, '
             'ritel beli vs jual, jumlah pembeli vs penjual. Diuji di 21 emiten folder Test 2016-2026 '
             'dan ~850 emiten 2026, sendirian maupun ditumpuk di atas pola tenang dan pola tembus. '
             'Tidak ada yang memisahkan secara konsisten.'),
    'gagal_lain': ('Juga gagal: volume mengering, "sudah naik 20% dalam 20 hari", pemenang 6 bulan, '
                   'volatilitas tinggi. Semuanya menaikkan peluang +10%, tapi kalah dari pasar '
                   'setelah dimajemukkan -- mereka cuma lebih liar, bukan lebih naik.'),
    'batas': [
        'Data Yahoo cuma berisi emiten yang MASIH tercatat; kerugian emiten yang delisting hilang. '
        'Semua angka agak terlalu optimistis.',
        'Efeknya paling besar di emiten Rp1-5 M/hari, persis tempat slippage sungguhan lebih mahal '
        'dari yang dimodelkan.',
        'Yang terbaik pun cuma menggeser "+10% sebelum -10%" dari ~47% ke ~56-63%. Tidak ada pola '
        'yang peluangnya tinggi.',
        'Kecondongan populasi, bukan ramalan per emiten: ini daftar KANDIDAT.',
    ],
}

# Harapan backtest per aturan untuk dibandingkan dengan jurnal maju.
HARAPAN = {
    'basis': {'p10': 20.9, 'naik60': 49.9, 'vs_pasar60': 4.7},
    'puncak': {'p10': 26.8, 'naik60': 47.8, 'vs_pasar60': 2.7},
    'keduanya': {'p10': 21.5, 'naik60': 52.3, 'vs_pasar60': 7.1},
}
ATURAN_LABEL = {'basis': 'Tembus basis', 'puncak': 'Puncak 52 minggu', 'keduanya': 'Keduanya'}

KOLOM_JURNAL = ['tanggal', 'stock', 'close', 'basis30', 'vol_x', 'tembus30', 'puncak52',
                'dari_puncak', 'nilai', 'posisi', 'naik']
KOLOM_HARI = ['tanggal', 'dicatat', 'n_segar', 'n_layak', 'n_baris']


# ---------------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------------
def _baca_summary(path):
    try:
        df = pd.read_csv(path, usecols=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
    except Exception:
        return None
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    for col in ('Open', 'High', 'Low', 'Close', 'Volume'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['Date', 'Close'])
    df = df[df['Close'] > 0]
    if df.empty:
        return None
    df = df.drop_duplicates('Date', keep='last').set_index('Date').sort_index()
    df['Volume'] = df['Volume'].fillna(0)
    return df


def _cari_cache_yahoo():
    """Pickle harga Yahoo dengan baris terbanyak di research_cache (dibuat
    rl_trading.py). Baris, bukan jumlah emiten -- lihat riset_pola_naik/
    panel.sumber_harga() soal dua pickle 888 emiten yang beda panjangnya."""
    terbaik, kunci_terbaik = None, (0, 0)
    for path in glob.glob(str(_runtime_file('research_cache', 'harga_*.pkl'))):
        try:
            with open(path, 'rb') as fh:
                data = pickle.load(fh)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        kunci = (sum(len(v) for v in data.values()), len(data))
        if kunci > kunci_terbaik:
            terbaik, kunci_terbaik = data, kunci
    return terbaik


def _unduh_yahoo(tickers, mulai, akhir):
    """Cadangan kalau research_cache kosong: unduh per rombongan 120 emiten."""
    import yfinance as yf
    data = {}
    for i in range(0, len(tickers), 120):
        potong = tickers[i:i + 120]
        try:
            mentah = yf.download([t + '.JK' for t in potong], start=mulai, end=akhir, interval='1d',
                                 progress=False, auto_adjust=True, group_by='ticker', threads=True)
        except Exception as exc:
            logger.warning('Unduh riwayat %d-%d gagal: %s', i, i + len(potong), exc)
            continue
        for t in potong:
            try:
                df = mentah[t + '.JK'] if isinstance(mentah.columns, pd.MultiIndex) else mentah
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna(how='all')
            except KeyError:
                continue
            if len(df):
                data[t] = df
    return data


def _riwayat(tickers):
    """
    Riwayat harga Yahoo Jun 2024 - Mar 2026 per emiten, untuk menutup jendela
    250 hari sebelum Summary dimulai. Dibangun SEKALI (dari research_cache
    kalau ada, kalau tidak diunduh), lalu disimpan. Ujung Mar 2026 sengaja
    tumpang tindih dengan Summary: bagian itu dipakai menghitung rasio
    penyetara, bukan harganya.
    """
    if os.path.exists(RIWAYAT_FILE):
        try:
            with open(RIWAYAT_FILE, 'rb') as fh:
                return pickle.load(fh)
        except Exception:
            logger.exception('Riwayat Tembus Basis tidak terbaca, dibangun ulang')

    mulai, akhir = '2024-06-01', '2026-04-01'
    sumber = _cari_cache_yahoo()
    asal = 'research_cache'
    if not sumber:
        sumber = _unduh_yahoo(sorted(tickers), mulai, akhir)
        asal = 'yahoo'
    data = {}
    for t, df in (sumber or {}).items():
        try:
            d = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        except KeyError:
            continue
        d.index = pd.to_datetime(d.index)
        d = d[(d.index >= mulai) & (d.index < akhir)]
        d = d[d['Close'] > 0]
        if len(d):
            data[t] = d.astype('float64')
    simpan = {'asal': asal, 'dibangun': time.strftime('%Y-%m-%d %H:%M'), 'data': data}
    if data:
        try:
            with open(RIWAYAT_FILE, 'wb') as fh:
                pickle.dump(simpan, fh)
        except Exception:
            logger.exception('Gagal menyimpan riwayat Tembus Basis')
    return simpan


def _kalender(muatan):
    """Hari bursa = tanggal yang muncul di >= 25% berkas Summary.

    Bukan tanggal berkas terbesar saja: satu berkas yang kebetulan bolong
    akan membolongkan kalender semua emiten. Bukan gabungan mentah juga:
    satu baris bertanggal salah akan jadi "hari bursa" bagi semuanya."""
    hitung = {}
    for _, df in muatan:
        for d in df.index:
            hitung[d] = hitung.get(d, 0) + 1
    ambang = max(1, int(len(muatan) * 0.25))
    return pd.DatetimeIndex(sorted(d for d, n in hitung.items() if n >= ambang))


def _sambung(stock, df_s, kal, riwayat):
    """Summary (disetel ke kalender bursa) + riwayat Yahoo sebelum Summary mulai."""
    k = kal[(kal >= df_s.index[0]) & (kal <= df_s.index[-1])]
    s = df_s.reindex(k)
    kosong = s['Close'].isna()
    s['Close'] = s['Close'].ffill()
    for col in ('Open', 'High', 'Low'):
        s[col] = s[col].where(~kosong, s['Close'])
    s['Volume'] = s['Volume'].where(~kosong, 0.0)

    r = riwayat.get(stock)
    if r is None or r.empty:
        return s, None
    # Rasio penyetara dari hari-hari yang ada di KEDUA sumber dan sama-sama
    # bertransaksi. Median, bukan satu hari: satu hari bisa saja salah catat.
    tumpang = r.index.intersection(df_s.index)
    rasio = 1.0
    if len(tumpang):
        a = df_s.loc[tumpang]
        b = r.loc[tumpang]
        ok = (a['Volume'] > 0) & (b['Volume'] > 0) & (b['Close'] > 0)
        if ok.any():
            rasio = float((a.loc[ok, 'Close'] / b.loc[ok, 'Close']).iloc[:20].median())
    lama = r[r.index < df_s.index[0]].copy()
    for col in ('Open', 'High', 'Low', 'Close'):
        lama[col] = lama[col] * rasio
    return pd.concat([lama, s]), rasio


def fitur(df):
    """
    Ukuran yang dipakai aturan -- rumusnya SAMA PERSIS dengan
    riset_pola_naik/panel.py (dicek lewat `python -m website.riset_pola_naik.uji
    cek-setara`). df: indeks tanggal, kolom Open/High/Low/Close/Volume.
    """
    Cl = df['Close'].astype(float)
    V = df['Volume'].astype(float).fillna(0)
    H = np.maximum(df['High'].astype(float).fillna(Cl), Cl)
    L = np.minimum(df['Low'].astype(float).fillna(Cl), Cl)
    n = len(df)
    out = pd.DataFrame(index=df.index)
    out['close'] = Cl
    nilai = Cl * V
    loncat = (Cl.pct_change().abs() > C['LONCAT']).astype(float)
    out['hist'] = np.arange(n)
    out['aktif30'] = (V > 0).astype(float).rolling(30, min_periods=30).mean()
    out['nilai20'] = nilai.rolling(20, min_periods=20).median()
    out['loncat60'] = loncat.rolling(C['BERSIH_W'], min_periods=1).max()
    ph = H.rolling(C['BASIS_W'], min_periods=C['BASIS_W']).max().shift(1)
    pl = L.rolling(C['BASIS_W'], min_periods=C['BASIS_W']).min().shift(1)
    out['basis30'] = (ph - pl) / Cl.shift(1)
    out['tembus30'] = (Cl > ph).astype(float)
    vref = V.rolling(C['VOL_W'], min_periods=C['VOL_W']).mean().shift(1)
    out['vol_x'] = V / vref.replace(0, np.nan)
    maks = Cl.rolling(C['PUNCAK_W'], min_periods=C['PUNCAK_W']).max()
    out['puncak52'] = (Cl >= maks.shift(1)).astype(float)
    out['dari_puncak'] = Cl / maks - 1
    out['posisi'] = (Cl - L) / (H - L).replace(0, np.nan)
    out['naik'] = Cl.pct_change()
    out['layak'] = ((out['hist'] >= C['MIN_RIWAYAT']) & (Cl >= C['MIN_HARGA'])
                    & (out['nilai20'] >= C['MIN_NILAI']) & (out['aktif30'] >= C['MIN_AKTIF'])
                    & (out['loncat60'] == 0))
    vol = out['vol_x'] > C['VOL_X']
    out['s_basis'] = out['layak'] & (out['tembus30'] == 1) & (out['basis30'] < C['BASIS_MAX']) & vol
    out['s_puncak'] = out['layak'] & (out['puncak52'] == 1) & vol
    out['s_keduanya'] = out['s_basis'] & out['s_puncak']
    return out


def _panel():
    """Semua emiten: harga tersambung + fitur. Plus hari bursa terakhir pasar."""
    muatan = []
    for path in sorted(glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv'))):
        stock = os.path.basename(path).split('_')[0]
        df = _baca_summary(path)
        if df is not None:
            muatan.append((stock, df))
    if not muatan:
        return None
    kal = _kalender(muatan)
    rw = _riwayat([s for s, _ in muatan])
    riwayat = rw.get('data', {}) if isinstance(rw, dict) else {}

    fit, rasio = {}, {}
    for stock, df in muatan:
        df = df[df.index.isin(kal)]
        if df.empty:
            continue
        gabung, r = _sambung(stock, df, kal, riwayat)
        fit[stock] = fitur(gabung)
        rasio[stock] = r
    return {'kal': kal, 'fit': fit, 'rasio': rasio,
            'riwayat_asal': rw.get('asal') if isinstance(rw, dict) else None,
            'riwayat_n': len(riwayat)}


# ---------------------------------------------------------------------------
# SINYAL
# ---------------------------------------------------------------------------
def _num(v, d=None):
    """float bersih untuk JSON: NaN/inf -> None (jsonify menulis NaN mentah
    yang ditolak JSON.parse di browser)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    return round(v, d) if d is not None else v


def _jeda(posisi, jeda=C['JEDA'], akhir=-10 ** 9):
    """Indeks yang lolos jeda: satu sinyal per `jeda` bar, yang pertama menang.
    `akhir` = posisi kejadian terakhir SEBELUM daftar ini (kalau ada)."""
    lolos = []
    for i, p in enumerate(posisi):
        if p - akhir >= jeda:
            lolos.append(i)
            akhir = p
    return lolos


def _kejadian_terakhir(f, kolom, sebelum):
    """Tanggal kejadian terakhir (rantai jeda penuh) emiten ini sebelum
    tanggal `sebelum`, menurut kolom sinyal `kolom` di panel. None kalau
    tidak ada."""
    tanda = f[kolom].to_numpy() & (f.index < sebelum)
    idx = np.flatnonzero(tanda)
    if not len(idx):
        return None
    pilih = _jeda(idx.tolist())
    return f.index[idx[pilih[-1]]]


def _baris_terbaru(stock, f, hari_pasar):
    """Sinyal terbaru emiten ini dalam UMUR_MAX hari bursa, atau None."""
    if f.index[-1] != hari_pasar:
        return None
    semua = f['s_basis'] | f['s_puncak']
    idx = np.flatnonzero(semua.to_numpy())
    if not len(idx):
        return None
    n = len(f)
    lolos = [idx[i] for i in _jeda(idx.tolist())]
    i = int(idx[-1])
    umur = n - 1 - i
    if umur > C['UMUR_MAX']:
        return None
    r = f.iloc[i]
    kini = float(f['close'].iloc[-1])
    aturan = ('keduanya' if r['s_keduanya'] else ('basis' if r['s_basis'] else 'puncak'))
    return {
        'stock': stock,
        'tanggal': f.index[i].strftime('%Y-%m-%d'),
        'umur': umur,
        'aturan': aturan,
        'basis': bool(r['s_basis']),
        'puncak': bool(r['s_puncak']),
        # Sinyal pertama dalam 20 hari = "event" dalam arti riset. Sinyal
        # ulang (emiten yang mencetak puncak baru beruntun) tidak dihitung
        # sebagai kejadian baru di pengujian.
        'pertama': bool(i in lolos),
        'close_sinyal': _num(r['close'], 2),
        'close_kini': _num(kini, 2),
        'sejak': _num((kini / float(r['close']) - 1) * 100, 2) if r['close'] else None,
        'basis30': _num(r['basis30'] * 100, 1),
        'vol_x': _num(r['vol_x'], 2),
        'dari_puncak': _num(r['dari_puncak'] * 100, 1),
        'naik': _num(r['naik'] * 100, 2),
        'posisi': _num(r['posisi'], 2),
        'nilai_b': _num(r['nilai20'] / 1e9, 2),
    }


# ---------------------------------------------------------------------------
# JURNAL MAJU
# ---------------------------------------------------------------------------
def _muat_jurnal():
    """(jurnal, hari). Berkas yang ada tapi tak terbaca -> melempar, BUKAN
    mengembalikan kosong: pemanggil yang menulis tidak boleh mengira jurnal
    kosong lalu memulai dari nol di atas riwayat yang cuma gagal dibaca."""
    j = (pd.read_csv(JURNAL_FILE, dtype={'tanggal': str, 'stock': str})
         if os.path.exists(JURNAL_FILE) else pd.DataFrame(columns=KOLOM_JURNAL))
    h = (pd.read_csv(HARI_FILE, dtype={'tanggal': str})
         if os.path.exists(HARI_FILE) else pd.DataFrame(columns=KOLOM_HARI))
    if len(j):
        j = j.drop_duplicates(['tanggal', 'stock'], keep='first')
    if len(h):
        h = h.drop_duplicates('tanggal', keep='last')
    return j, h


def catat(panel, hari_pasar):
    """
    Tambahkan potret hari bursa terakhir ke jurnal. Idempoten per (tanggal,
    emiten), bukan per tanggal: kalau pemindaian jalan waktu unduhan harian
    baru separuh, emiten yang datang belakangan tetap tercatat di pemindaian
    berikutnya malam itu -- alih-alih harinya dianggap "sudah dicatat" dan
    separuh sisanya hilang selamanya.
    """
    tanggal = hari_pasar.strftime('%Y-%m-%d')
    try:
        lama, _ = _muat_jurnal()
    except Exception as exc:
        logger.exception('Jurnal Tembus Basis tidak terbaca -- tidak menulis apa pun')
        return {'tanggal': tanggal, 'tercatat': 0, 'pesan': 'jurnal tidak terbaca: %s' % exc}

    sudah = set(lama.loc[lama['tanggal'] == tanggal, 'stock']) if len(lama) else set()
    baris, n_segar, n_layak = [], 0, 0
    for stock, f in panel['fit'].items():
        if f.index[-1] != hari_pasar:
            continue
        n_segar += 1
        r = f.iloc[-1]
        if not r['layak']:
            continue
        n_layak += 1
        # Superset: SEMUA yang menembus tertinggi 30 hari atau mencetak puncak
        # 52 minggu, lolos aturan atau tidak -- ambang yang digeser nanti
        # tetap bisa diuji terhadap catatan ini.
        if not (r['tembus30'] == 1 or r['puncak52'] == 1) or stock in sudah:
            continue
        baris.append({
            'tanggal': tanggal, 'stock': stock, 'close': _num(r['close'], 2),
            'basis30': _num(r['basis30'], 4), 'vol_x': _num(r['vol_x'], 3),
            'tembus30': int(r['tembus30']), 'puncak52': int(r['puncak52']),
            'dari_puncak': _num(r['dari_puncak'], 4), 'nilai': _num(r['nilai20'], 0),
            'posisi': _num(r['posisi'], 3), 'naik': _num(r['naik'], 4),
        })
    if baris:
        pd.DataFrame(baris, columns=KOLOM_JURNAL).to_csv(
            JURNAL_FILE, mode='a', index=False, header=not os.path.exists(JURNAL_FILE))
    pd.DataFrame([{'tanggal': tanggal, 'dicatat': time.strftime('%Y-%m-%d %H:%M'),
                   'n_segar': n_segar, 'n_layak': n_layak, 'n_baris': len(sudah) + len(baris)}],
                 columns=KOLOM_HARI).to_csv(HARI_FILE, mode='a', index=False,
                                             header=not os.path.exists(HARI_FILE))
    return {'tanggal': tanggal, 'tercatat': len(baris), 'sudah_ada': len(sudah),
            'n_segar': n_segar, 'n_layak': n_layak}


def evaluasi(panel, hari_pasar):
    """
    Hasil jurnal yang sudah matang, per aturan, terhadap pasar hari yang sama.
    Aturannya dihitung ULANG dari ukuran mentah jurnal (bukan dari cache
    sinyal), dengan jeda 20 hari per emiten per aturan -- sama dengan riset.
    """
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
        hari_bursa = [d.strftime('%Y-%m-%d') for d in kal if mulai <= d <= hari_pasar]
        tercatat = set(h['tanggal'].astype(str))
        cakupan['terlewat'] = [d for d in hari_bursa if d not in tercatat]
    else:
        cakupan['terlewat'] = []
    if j.empty:
        return {'available': True, 'cakupan': cakupan, 'aturan': [],
                'pesan': 'Jurnal baru dimulai -- belum ada baris.'}

    # Pivot close di kalender bursa + kelayakan per hari, untuk return ke
    # depan emiten jurnal DAN pembanding pasar pada tanggal yang sama.
    tutup = pd.DataFrame({s: f['close'] for s, f in panel['fit'].items()}).reindex(kal)
    layak = pd.DataFrame({s: f['layak'] for s, f in panel['fit'].items()}).reindex(kal)
    layak = layak.astype('boolean').fillna(False).astype(bool)
    loncat_cs = (tutup.pct_change(fill_method=None).abs() > C['LONCAT']).astype(float).cumsum()

    def maju(hz):
        masuk = tutup.shift(-1)
        keluar = tutup.shift(-(hz + 1))
        lr = np.log(keluar / masuk)
        # Jendela yang memuat loncatan (aksi korporasi / data rusak) dibuang,
        # sama seperti riset: loncatan di baris d+1..d+1+hz = selisih
        # jumlah kumulatifnya.
        kotor = (loncat_cs.shift(-(hz + 1)) - loncat_cs) > 0
        return lr.mask(kotor)

    j = j.copy()
    j['tgl'] = pd.to_datetime(j['tanggal'])
    j['p'] = j['tgl'].map(pos)
    j = j.dropna(subset=['p'])
    j['p'] = j['p'].astype(int)
    for kol in ('basis30', 'vol_x', 'tembus30', 'puncak52'):
        j[kol] = pd.to_numeric(j[kol], errors='coerce')
    vol = j['vol_x'] > C['VOL_X']
    j['basis'] = (j['tembus30'] == 1) & (j['basis30'] < C['BASIS_MAX']) & vol
    j['puncak'] = (j['puncak52'] == 1) & vol
    j['keduanya'] = j['basis'] & j['puncak']

    # Rantai jeda tidak boleh mulai dari nol di hari pertama jurnal: emiten
    # yang sudah bersinyal 5 hari sebelum jurnal dimulai lalu bersinyal lagi
    # hari ini adalah sinyal ULANG di riset -- tidak dihitung sebagai
    # kejadian baru. Kejadian terakhir sebelum jurnal diambil dari panel
    # (rantai penuh), dan hanya dipakai sebagai titik awal jeda.
    mulai_jurnal = j['tgl'].min()
    awal = {}
    for aturan in ('basis', 'puncak', 'keduanya'):
        for stock in j.loc[j[aturan], 'stock'].unique():
            f = panel['fit'].get(stock)
            d = _kejadian_terakhir(f, 's_' + aturan, mulai_jurnal) if f is not None else None
            if d is not None and d in pos:
                awal[(aturan, stock)] = pos[d]

    hasil = []
    for hz in (20, C['TAHAN']):
        lr = maju(hz)
        pasar = lr.where(layak).mean(axis=1)
        for aturan in ('basis', 'puncak', 'keduanya'):
            sub = j[j[aturan]].sort_values(['stock', 'p'])
            ev = []
            for stock, g in sub.groupby('stock'):
                pp = g['p'].tolist()
                ev.extend(g.iloc[_jeda(pp, akhir=awal.get((aturan, stock), -10 ** 9))].itertuples())
            n = len(ev)
            matang = [e for e in ev if e.p + hz + 1 <= hari_akhir]
            nilai, pemb = [], []
            tanpa_harga = 0
            for e in matang:
                x = lr.at[kal[e.p], e.stock] if e.stock in lr.columns else np.nan
                b = pasar.iloc[e.p]
                if not np.isfinite(x) or not np.isfinite(b):
                    tanpa_harga += 1
                    continue
                nilai.append(x)
                pemb.append(b)
            nilai, pemb = np.array(nilai), np.array(pemb)
            m = len(nilai)
            sisa = None
            if n and len(matang) < n:
                # berapa hari bursa lagi sampai sinyal tertua yang belum matang matang
                belum = [e for e in ev if e.p + hz + 1 > hari_akhir]
                sisa = int(min(e.p for e in belum) + hz + 1 - hari_akhir)
            hasil.append({
                'aturan': aturan, 'label': ATURAN_LABEL[aturan], 'horizon': hz,
                'n': n, 'n_matang': m, 'n_tanpa_harga': tanpa_harga, 'sisa_hari': sisa,
                'win': _num((nilai > 0).mean() * 100, 1) if m else None,
                'p10': _num((nilai >= np.log(1.10)).mean() * 100, 1) if m else None,
                'majemuk': _num((np.exp(nilai.mean()) - 1) * 100, 2) if m else None,
                'vs_pasar': _num((np.exp((nilai - pemb).mean()) - 1) * 100, 2) if m else None,
                'harapan': HARAPAN.get(aturan),
                'cukup': m >= 30,
            })
    return {'available': True, 'cakupan': cakupan, 'aturan': hasil}


# ---------------------------------------------------------------------------
# PEMINDAIAN
# ---------------------------------------------------------------------------
def _bangun():
    panel = _panel()
    if not panel or not panel['fit']:
        return {'available': False, 'message': 'Tidak ada berkas Summary yang bisa dibaca.'}
    hari_pasar = max(f.index[-1] for f in panel['fit'].values())

    baris, n_basi, n_pendek, n_segar, n_layak = [], 0, 0, 0, 0
    for stock, f in panel['fit'].items():
        if f.index[-1] != hari_pasar:
            n_basi += 1
            continue
        n_segar += 1
        if f['hist'].iloc[-1] < C['MIN_RIWAYAT']:
            n_pendek += 1
        if bool(f['layak'].iloc[-1]):
            n_layak += 1
        r = _baris_terbaru(stock, f, hari_pasar)
        if r:
            baris.append(r)

    # Urutan mengikuti kekuatan bukti, bukan selera: yang pertama dalam 20
    # hari dulu (itu yang diuji), lalu keduanya > basis > puncak, lalu yang
    # paling baru, lalu yang paling likuid.
    urut = {'keduanya': 0, 'basis': 1, 'puncak': 2}
    baris.sort(key=lambda r: (not r['pertama'], urut[r['aturan']], r['umur'], -(r['nilai_b'] or 0)))

    try:
        dicatat = catat(panel, hari_pasar)
    except Exception as exc:
        logger.exception('Gagal mencatat jurnal Tembus Basis')
        dicatat = {'tercatat': 0, 'pesan': 'gagal: %s' % exc}
    try:
        jurnal = evaluasi(panel, hari_pasar)
    except Exception as exc:
        logger.exception('Gagal mengevaluasi jurnal Tembus Basis')
        jurnal = {'available': False, 'message': 'Gagal mengevaluasi: %s' % exc}

    hari_ini = [r for r in baris if r['umur'] == 0 and r['pertama']]
    tanpa_riwayat = sum(1 for s, r in panel['rasio'].items() if r is None)
    return {
        'available': True,
        'as_of': hari_pasar.strftime('%Y-%m-%d'),
        'n_emiten': len(panel['fit']),
        'n_segar': n_segar,
        'n_basi': n_basi,
        'n_layak': n_layak,
        'n_riwayat_pendek': n_pendek,
        'n_tanpa_riwayat': tanpa_riwayat,
        'riwayat_asal': panel['riwayat_asal'],
        'hitung_hari_ini': {k: sum(1 for r in hari_ini if r['aturan'] == k)
                            for k in ('keduanya', 'basis', 'puncak')},
        'baris': baris,
        'catat': dicatat,
        'jurnal': jurnal,
        'config': dict(C),
        'bukti': BUKTI,
        'dibangun': time.strftime('%Y-%m-%d %H:%M'),
        'from_cache': False,
    }


def _sumber_terbaru():
    from .kesegaran import summary_terbaru, berkas_terbaru, paling_baru
    return paling_baru(summary_terbaru(), berkas_terbaru(RIWAYAT_FILE))


def scan(force=False):
    """
    Sinyal sampai hari bursa terakhir + jurnal maju.

    Di-cache terhadap mtime Summary terbaru. Pembangunan ulang SELALU
    mencatat jurnal dulu (idempoten), jadi halaman yang dibuka sesudah
    unduhan harian ikut menjaga jurnalnya tetap terisi kalau pemeriksaan
    kesehatan malam itu kebetulan tidak jalan.
    """
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                simpan = pickle.load(fh)
            if simpan.get('ts', 0) >= _sumber_terbaru():
                hasil = dict(simpan['result'])
                hasil['from_cache'] = True
                # BUKTI & C itu teks dari kode, bukan hasil hitungan: selalu
                # yang terbaru, jangan yang ikut terbekukan di cache.
                hasil['bukti'] = BUKTI
                hasil['config'] = dict(C)
                return hasil
        except Exception:
            pass

    hasil = _bangun()
    if hasil.get('available'):
        try:
            with open(CACHE_FILE, 'wb') as fh:
                pickle.dump({'ts': time.time(), 'result': hasil}, fh)
        except Exception:
            logger.exception('Gagal menyimpan cache Tembus Basis')
    return hasil


def sinyal_terbaru(umur_max=1):
    """(kode, tanggal) sinyal pertama-dalam-20-hari yang umurnya <= umur_max --
    dipakai viewer chart /tembus-basis/chart."""
    h = scan()
    return [(r['stock'], r['tanggal']) for r in (h.get('baris') or [])
            if r['pertama'] and r['umur'] <= umur_max]


if __name__ == '__main__':
    import sys
    t0 = time.time()
    h = scan(force='--force' in sys.argv)
    if not h.get('available'):
        print(h.get('message'))
        sys.exit(1)
    print('posisi %s | %d emiten, %d segar, %d layak, %d basi | riwayat: %s'
          % (h['as_of'], h['n_emiten'], h['n_segar'], h['n_layak'], h['n_basi'], h['riwayat_asal']))
    print('hari ini:', h['hitung_hari_ini'], '| jurnal:', h['catat'])
    for r in h['baris'][:25]:
        print('  %-5s %-9s umur %d %s basis %5s%% vol %5sx sejak %6s%%'
              % (r['stock'], r['aturan'], r['umur'], 'baru ' if r['pertama'] else 'ulang',
                 r['basis30'], r['vol_x'], r['sejak']))
    print('%.1f detik' % (time.time() - t0))
