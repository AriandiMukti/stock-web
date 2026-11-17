"""
Sidik jari perilaku broker: mengelompokkan broker menurut CARA MEREKA
BERDAGANG, bukan menurut berapa lot yang mereka beli hari ini.

KENAPA INI ADA
Seluruh app ini memperlakukan broker sebagai angka yang dijumlahkan: "Net
Top5 lot". Lima broker teratas dijumlah jadi satu bilangan, lalu identitas
dan perilakunya dibuang. Padahal broker yang mengakumulasi pelan-pelan
selama sebulan dan broker yang masuk-keluar dalam sehari menghasilkan angka
"net beli" yang sama persis, tapi artinya jauh berbeda.

Dengan buku besar broker (broker_ledger.py: 1,9 juta baris, 91 broker, 881
saham, 158 hari), tiap broker bisa dikarakterisasi:

    Kontrarian vs momentum  -- saat mereka membeli, harga sedang turun atau
                               sedang naik? (rata-rata drift 20 hari sebelumnya)
    Kesabaran               -- berapa hari berturut-turut mereka bertahan di
                               saham yang sama?
    Fokus vs sebar          -- berapa banyak saham berbeda yang mereka sentuh,
                               dan seberapa terkonsentrasi volumenya?
    Hasil setelahnya        -- setelah mereka masuk, apa yang terjadi pada
                               harga 20 hari kemudian?

Lalu sinyalnya berubah bentuk: bukan lagi "Top5 net beli", melainkan
"broker bertipe akumulator-sabar sedang masuk" versus "broker bertipe
hit-and-run sedang masuk" -- dua hal yang selama ini tercampur jadi satu.

BATASNYA -- BACA INI
- Kode broker BUKAN satu pemodal. Satu broker melayani banyak nasabah; yang
  terukur di sini adalah perilaku AGREGAT nasabah broker itu, bukan niat satu
  pihak. Broker ritel besar akan terlihat "sebar" bukan karena strateginya
  begitu, tapi karena nasabahnya ribuan.
- "Hasil setelahnya" adalah korelasi, bukan sebab-akibat. Broker yang
  hasilnya bagus bisa saja sekadar melayani nasabah yang kebetulan pintar,
  atau kebetulan besar di sektor yang sedang naik.
- Periode Jan-Sep 2026 (~8 bulan) dan didominasi pasar turun. Semua angka
  hasil absolut negatif; yang berarti adalah selisih antar broker.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import pickle
import time

import numpy as np
import pandas as pd

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CACHE_FILE = str(_runtime_file('', 'broker_fingerprint_cache.pkl'))


def _ledger_terbaru():
    """mtime buku besar broker -- induk semua angka di modul ini."""
    from .kesegaran import berkas_terbaru
    from .broker_ledger import CACHE_FILE as LEDGER_FILE
    return berkas_terbaru(LEDGER_FILE)


def _sumber_terbaru():
    """Buku besar broker + berkas Summary."""
    from .kesegaran import summary_terbaru, paling_baru
    return paling_baru(_ledger_terbaru(), summary_terbaru())
# Sidik jari diturunkan dari broker_ledger.pkl DAN berkas Summary
# (harga penutupan). Basi begitu salah satunya lebih baru -- lihat
# kesegaran.py untuk kenapa ini bukan TTL jam-jaman.

C = {
    'LOOK': 20,        # jendela drift harga sebelum transaksi
    'FWD': 20,         # horizon hasil setelah transaksi
    'MIN_HARI': 200,   # minimal baris (saham-hari) supaya broker ikut dinilai
    'TOP_N_SAHAM': 10, # untuk mengukur konsentrasi
}

# Ambang tipe perilaku. Sengaja berupa aturan, bukan k-means: hasilnya harus
# bisa dijelaskan ("kontrarian karena rata-rata masuk saat harga -4%"),
# bukan sekadar "klaster 3".
#
# KELUASAN DIPERIKSA DULUAN, DAN ITU PENTING.
# Versi pertama modul ini melabeli YP, PD, XL, CC sebagai "akumulator sabar"
# -- padahal mereka menyentuh SELURUH 881 saham di bursa. Broker yang hadir
# di semua saham setiap hari bukan sedang menjalankan strategi; itu platform
# ritel besar, dan yang terukur adalah perilaku agregat ribuan nasabahnya
# (yang memang cenderung beli saat turun dan menahan). Melabelinya
# "akumulator sabar" akan membuat pembaca mengira ada satu pihak yang sedang
# mengumpulkan, padahal tidak ada. Karena itu keluasan disaring lebih dulu.
LUAS_AMBANG = 700   # menyentuh >= sekian saham = hadir di hampir seluruh bursa


def klasifikasi(f):
    kontra = f['drift_saat_beli']          # negatif = masuk saat harga turun
    sabar = f['rata2_streak']              # hari berturut-turut di saham sama
    sebar = f['n_saham']

    if kontra is None or sabar is None:
        return 'tidak cukup data', 'Data belum cukup untuk mengelompokkan.'

    if sebar >= LUAS_AMBANG:
        return ('broker ritel luas',
                'Hadir di hampir semua saham di bursa (%d saham). Ini perilaku agregat '
                'ribuan nasabah, BUKAN satu pihak yang sedang mengumpulkan.' % sebar)

    if sabar >= 3.0 and kontra <= -1.0:
        return 'akumulator sabar', 'Masuk saat harga sedang turun, lalu bertahan berhari-hari.'
    if sabar >= 3.0 and kontra > 1.0:
        return 'pengikut tren', 'Bertahan lama, tapi masuknya justru saat harga sudah naik.'
    if sabar < 1.6:
        return 'pedagang cepat', 'Masuk-keluar cepat, jarang bertahan lebih dari sehari.'
    if kontra <= -1.0:
        return 'pemburu lemah', 'Cenderung masuk saat harga turun, tapi tidak bertahan lama.'
    if kontra > 1.0:
        return 'pengejar momentum', 'Cenderung masuk saat harga sudah naik, tidak bertahan lama.'
    return 'netral', 'Tidak condong ke pola tertentu.'


def _harga_fitur():
    """
    {(stock, date): (drift20, fwd20)} dari seluruh berkas Summary.
    Dipakai untuk menilai KAPAN broker masuk dan APA yang terjadi setelahnya.
    """
    import glob
    out = {}
    for path in glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')):
        stock = os.path.basename(path)[:4]
        try:
            df = pd.read_csv(path, usecols=['Date', 'Close'])
            df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
            df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
        except Exception:
            continue
        close = pd.to_numeric(df['Close'], errors='coerce')
        n = len(df)
        for i in range(n):
            c0 = close.iloc[i]
            if not np.isfinite(c0) or c0 <= 0:
                continue
            drift = None
            if i >= C['LOOK']:
                cs = close.iloc[i - C['LOOK']]
                if np.isfinite(cs) and cs > 0:
                    drift = (c0 - cs) / cs * 100.0
            fwd = None
            if i + C['FWD'] < n:
                cf = close.iloc[i + C['FWD']]
                if np.isfinite(cf):
                    fwd = (cf - c0) / c0 * 100.0
            out[(stock, df['Date'].iloc[i])] = (drift, fwd)
    return out


def build(force=False):
    """Sidik jari seluruh broker. None kalau buku besar belum dibangun."""
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            if cached.get('ts', 0) >= _sumber_terbaru():
                hasil = dict(cached['result'])
                hasil['from_cache'] = True
                return hasil
        except Exception:
            pass

    from .broker_ledger import load
    df, meta = load()
    if df is None:
        return {'available': False,
                'message': 'Buku besar broker belum dibangun. Jalankan: '
                           'python -m website.broker_ledger'}

    t0 = time.time()

    # Netto per (broker, saham, hari): beli - jual
    df = df.copy()
    df['lot_net'] = np.where(df['side'].astype(str) == 'buy', df['lot'], -df['lot'])
    net = (df.groupby(['broker', 'stock', 'date'], observed=True)
             .agg(lot_net=('lot_net', 'sum'), value=('value', 'sum'),
                  avg_price=('avg_price', 'mean'))
             .reset_index())

    fitur = _harga_fitur()
    kunci = list(zip(net['stock'].astype(str), net['date']))
    net['drift'] = [fitur.get(k, (None, None))[0] for k in kunci]
    net['fwd'] = [fitur.get(k, (None, None))[1] for k in kunci]

    # Hanya hari NET BELI yang dipakai untuk menilai perilaku masuk --
    # pertanyaannya "kapan broker ini menambah posisi", bukan "kapan dia ada".
    beli = net[net['lot_net'] > 0]

    rows = []
    for broker, g in beli.groupby('broker', observed=True):
        if len(g) < C['MIN_HARI']:
            continue

        # Kesabaran: rata-rata panjang rentetan hari beli berturut-turut
        # pada saham yang sama.
        streaks = []
        for stock, gs in g.groupby('stock', observed=True):
            tgl = gs['date'].sort_values().values
            if len(tgl) == 0:
                continue
            panjang = 1
            for i in range(1, len(tgl)):
                selisih = (tgl[i] - tgl[i - 1]) / np.timedelta64(1, 'D')
                if selisih <= 4:      # <=4 hari kalender = masih beruntun (jeda akhir pekan)
                    panjang += 1
                else:
                    streaks.append(panjang)
                    panjang = 1
            streaks.append(panjang)
        rata2_streak = float(np.mean(streaks)) if streaks else None

        vol_per_saham = g.groupby('stock', observed=True)['lot_net'].sum().sort_values(ascending=False)
        total_lot = float(vol_per_saham.sum())
        konsentrasi = (float(vol_per_saham.head(C['TOP_N_SAHAM']).sum()) / total_lot * 100.0
                       if total_lot > 0 else None)

        drift = g['drift'].dropna()
        fwd = g['fwd'].dropna()

        f = {
            'broker': str(broker),
            'n_baris': int(len(g)),
            'n_saham': int(g['stock'].nunique()),
            'total_lot': round(total_lot, 0),
            'total_nilai_m': round(float(g['value'].sum()) / 1e9, 1),
            'rata2_lot': round(float(g['lot_net'].mean()), 0),
            'konsentrasi_top10': round(konsentrasi, 1) if konsentrasi is not None else None,
            'rata2_streak': round(rata2_streak, 2) if rata2_streak is not None else None,
            'drift_saat_beli': round(float(drift.mean()), 2) if len(drift) else None,
            'fwd_rata2': round(float(fwd.mean()), 2) if len(fwd) else None,
            'fwd_win': round(float((fwd > 0).mean() * 100), 1) if len(fwd) else None,
            'n_fwd': int(len(fwd)),
        }
        f['tipe'], f['tipe_penjelasan'] = klasifikasi(f)
        rows.append(f)

    # Baseline pasar dari seluruh pengamatan yang punya fwd
    semua_fwd = net['fwd'].dropna()
    baseline = {
        'n': int(len(semua_fwd)),
        'win': round(float((semua_fwd > 0).mean() * 100), 1) if len(semua_fwd) else None,
        'mean': round(float(semua_fwd.mean()), 2) if len(semua_fwd) else None,
    }
    for r in rows:
        r['fwd_vs_baseline'] = (round(r['fwd_win'] - baseline['win'], 1)
                                if (r['fwd_win'] is not None and baseline['win'] is not None) else None)

    rows.sort(key=lambda r: -(r['total_lot'] or 0))

    tipe_counts = {}
    for r in rows:
        tipe_counts[r['tipe']] = tipe_counts.get(r['tipe'], 0) + 1

    hasil = {
        'available': True,
        'rows': rows,
        'n_broker': len(rows),
        'baseline': baseline,
        'tipe_counts': tipe_counts,
        'ledger_meta': meta,
        'config': dict(C),
        'durasi_detik': round(time.time() - t0, 1),
        'as_of': time.strftime('%Y-%m-%d %H:%M'),
        'from_cache': False,
    }

    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'result': hasil}, fh)
    except Exception:
        pass

    return hasil


# =====================================================================
# HARGA MODAL BANDAR
# =====================================================================
# Ini bagian paling berguna dari buku besar broker, dan satu-satunya yang
# lolos pengujian. Sisi "ikuti broker pintar" TIDAK lolos: diuji di tingkat
# tipe perilaku, SEMUA tipe edge-nya negatif terhadap baseline saham-hari
# (pemburu lemah -4,05; pengejar momentum -5,65; netral -5,75; ritel luas
# -5,77; pedagang cepat -6,22), dan semua potongan sifat (kontrarian,
# kesabaran, keluasan) juga negatif. Artinya keunggulan satu-dua broker
# tidak menular ke tipenya -- jangan dipakai untuk membuntuti siapa pun.
#
# Yang justru bekerja: MEMBANDINGKAN HARGA SEKARANG DENGAN HARGA MODAL
# para pembeli besar. Field `netbs_buy_avg_price` (harga rata-rata beli per
# broker per hari) selama ini tidak pernah dipakai app ini sama sekali.
#
# 98.950 pengamatan, 878 saham, return 20 hari, DIKENDALIKAN terhadap drift
# harga supaya bukan sekadar mengulang temuan Akumulasi Palsu:
#
#   drift harga   posisi vs modal       n      win%     edge   konsisten
#   turun         bandar rugi >5%    30219     48,9    +5,48   tidak
#   turun         sekitar impas      12398     45,1    +1,29   tidak
#   turun         bandar untung >5%    922     33,4   -10,91   YA
#   datar         bandar untung >5%   1836     38,5    -5,95   YA
#   naik banyak   bandar untung >5%   4122     34,5    -8,85   YA
#
# Baris kuncinya yang pertama vs ketiga: DALAM KELOMPOK HARGA YANG SAMA
# (sama-sama turun), selisihnya 15,5 poin persen. Dua saham yang sama-sama
# turun 10% terlihat identik di semua modul lain di app ini -- tapi kalau di
# satu saham pembeli besarnya masih untung (penurunan belum menyentuh modal
# mereka) sedangkan di satu lagi sudah rugi, hasilnya berbeda jauh.
#
# Mekanismenya masuk akal: bandar yang masih untung punya ruang DAN insentif
# untuk terus melepas; yang sudah rugi cenderung mempertahankan harga.
#
# BATASNYA: ini rata-rata kelompok dari ~8 bulan pasar turun, belum diuji di
# luar sampel, dan "bandar" di sini adalah agregat semua broker pembeli --
# bukan satu pihak.
# DURASI JENDELA DIPILIH DARI SAPUAN, BUKAN DITEBAK.
# Versi pertama memakai 20 hari begitu saja. Setelah disapu 5/10/20/40/60
# hari (edge vs baseline paruh masing-masing, horizon 20 hari):
#
#   jendela  bandar untung >5%        bandar rugi >5%
#            edge     konsisten       edge     konsisten
#      5h    -7,57       ya           +1,88      TIDAK
#     10h    -7,45       ya           +1,62      TIDAK
#     20h    -7,01       ya           +2,26      TIDAK   <- pilihan lama
#     40h    -3,73       ya           +3,59      ya
#     60h    -7,14       ya           +3,06      ya      <- dipakai sekarang
#
# Sisi peringatan ("bandar untung") kuat di SEMUA jendela -- jadi temuannya
# bukan artefak pemilihan jendela. Tapi sisi positif ("bandar rugi") baru
# konsisten di dua paruh mulai 40 hari ke atas: jendela pendek menangkap
# fluktuasi harga beli jangka pendek, bukan modal yang sesungguhnya
# tertanam. 60 hari satu-satunya yang KEDUA sisinya konsisten sekaligus
# peringatannya tetap kuat (40h peringatannya melemah jadi -3,73).
MODAL_HARI = 60
MODAL_AMBANG = 5.0   # persen; di atas ini bandar disebut untung/rugi
GERAK_HARI = 10      # jendela 'harga bergerak' untuk pewarnaan kartu

# Sama seperti LIKUID_MIN di jatuh_dalam.py -- angka yang sama dipakai di
# dua tempat sengaja, bukan kebetulan: posisi bandar yang "untung besar"
# di saham < Rp2 M/hari nilainya semu, ongkos keluar-masuknya sendiri
# (lihat SLIPPAGE di jatuh_dalam.py) bisa memakan habis selisih itu
# sebelum sempat direalisasikan.
LIKUID_MIN = 2e9

# ==========================================================================
# UJI LUAR SAMPEL: SELURUH KALIBRASI DI BAWAH INI GAGAL DIREPLIKASI.
#
# Semua angka "edge" di modul ini berasal dari folder Daily: 881 emiten,
# Jan-Sep 2026, satu rezim pasar, ~8 bulan. Konsistensi dua paruh di dalam
# jendela sesempit itu ternyata TIDAK cukup.
#
# Diuji ulang pada data yang sama sekali terpisah -- folder Test, 21 emiten
# besar, 2016-2025 -- dengan struktur disamakan persis (antrean FIFO
# di-reset tiap awal tahun supaya umur lot sebanding, burn-in 60 hari,
# horizon 20 hari). Tiap tahun jadi satu replikasi mandiri:
#
#     tahun    bandar rugi >5%   bandar untung >5%
#     2016         -2,03              +0,44
#     2017         +1,98              +1,21
#     2018         -1,02              +0,95
#     2019         +0,67              -3,78
#     2020         -3,16              -0,27
#     2021         +3,18             -10,96
#     2022        +14,25              -7,35
#     2023         -3,10              +6,62
#     2024         +5,07              +1,30
#     2025         +5,59              -3,11
#     ------------------------------------------
#     gabungan     -0,10              +1,16
#     in-sample    +3,06              -7,14
#
# Sisi peringatan negatif hanya di 5 dari 10 tahun -- lempar koin. Sisi
# positif gabungannya nol. KEDUA tanda gagal bertahan, dan sisi peringatan
# bahkan terbalik.
#
# Yang sempat dipasang lalu dicabut: DRIFT_BATAS_RUGI = 20, dari temuan
# "bandar rugi TAPI harga sudah naik >20% = berbahaya" (in-sample -6,77).
# Dipecah per periode: 2016-2019 -7,07 / 2020-2022 +13,48 / 2023-2025 -2,33,
# dan di 21 emiten besar tahun 2026 sel itu cuma berisi 4 pengamatan.
# Temuan itu sepenuhnya digerakkan saham lapis tiga di satu periode pendek.
#
# YANG BELUM BISA DIPISAHKAN: kegagalan ini bisa karena REZIM (2026 berbeda)
# atau karena SEMESTA (folder Test cuma 21 emiten besar, sementara sinyalnya
# mungkin memang hanya hidup di lapis tiga). Data yang ada tidak bisa
# memisahkan keduanya. Artinya angka-angka di bawah BELUM TERBUKTI SALAH,
# tapi juga tidak berhak disajikan sebagai sudah terbukti benar.
#
# Konsekuensi tampilan: modul ini menyajikan posisi modal sebagai
# PENGAMATAN, bukan sebagai sinyal terkalibrasi.
# ==========================================================================

# JENDELA PEMBANDING: 60 hari saja bisa MENYESATKAN.
# Kasus nyata WBSA: jendela 60h bilang bandar rugi 14,5% (terasa aman), tapi
# jendela 20h menunjukkan modal terkini mereka sudah 5,95% DI BAWAH harga --
# mereka sudah average down dan pembelian terakhirnya sudah untung, jadi
# tetap punya alasan melepas. Diuji, dan jebakan itu nyata:
#
#   60h bandar rugi >5% + 20h juga rugi        n=51191  edge +3,82
#   60h bandar rugi >5% + 20h sudah untung     n=11710  edge +0,08  <- keunggulan hilang
#   60h bandar rugi >5% + 20h untung >5%       n= 3319  edge -6,96  <- konsisten dua paruh
#
# Selisih +3,82 ke -6,96 = 10,8 poin persen, dari kondisi yang di layar
# 60-harian terlihat SAMA-SAMA "aman".
#
# Catatan kejujuran: "arah geser modal" (modal20 vs modal60) sempat terlihat
# sangat kuat (+4,65 untuk average down), TAPI setelah dikendalikan terhadap
# drift harga 60 hari sebagian besar menguap -- itu sebagian besar cuma efek
# "harga sudah turun" yang sudah diketahui. Yang BERTAHAN setelah kontrol
# adalah sisi negatifnya: modal yang NAIK (average up) selalu jadi sel
# terburuk di tiap kelompok drift (-1,70 s.d. -4,77). Jadi jendela pembanding
# dipakai sebagai VETO/peringatan, bukan sebagai sinyal beli.
MODAL_HARI_BANDING = 20
VETO_AMBANG = 5.0

KALIBRASI_VETO = [
    {'kondisi': 'bandar rugi >5% + modal 20h lalu juga rugi', 'n': 42183, 'win': 49.6,
     'edge': 3.83, 'konsisten': True},
    {'kondisi': 'bandar rugi >5% TAPI vs modal 20h lalu untung >5% (VETO)', 'n': 501,
     'win': 21.8, 'edge': -14.76, 'konsisten': True},
]

KALIBRASI_METODE = [
    {'versi': 'A. Bruto (hanya sisi beli)', 'rugi_edge': 2.52, 'rugi_konsisten': True,
     'untung_edge': -5.15, 'untung_konsisten': False},
    {'versi': 'B. Neto sederhana', 'rugi_edge': 2.26, 'rugi_konsisten': True,
     'untung_edge': -6.64, 'untung_konsisten': True},
    {'versi': 'C. Neto agregat (degenerate)', 'rugi_edge': 5.89, 'rugi_konsisten': True,
     'untung_edge': -11.32, 'untung_konsisten': True,
     'catatan': 'Angkanya bagus tapi menyesatkan: posisi agregat seluruh broker selalu ~nol, '
                'jadi modal cuma mengikuti harga. Hanya 13 dari 572 emiten bergerak >5%.'},
    {'versi': 'D. Akuntansi per broker (dipakai)', 'rugi_edge': 8.07, 'rugi_konsisten': True,
     'untung_edge': -5.78, 'untung_konsisten': True,
     'catatan': 'Bertahan setelah dikendalikan drift harga, tapi HANYA di saham yang sedang turun.'},
]

SAPUAN_JENDELA = [
    {'hari': 5,  'untung_edge': -7.57, 'untung_konsisten': True,  'rugi_edge': 1.88, 'rugi_konsisten': False},
    {'hari': 10, 'untung_edge': -7.45, 'untung_konsisten': True,  'rugi_edge': 1.62, 'rugi_konsisten': False},
    {'hari': 20, 'untung_edge': -7.01, 'untung_konsisten': True,  'rugi_edge': 2.26, 'rugi_konsisten': False},
    {'hari': 40, 'untung_edge': -3.73, 'untung_konsisten': True,  'rugi_edge': 3.59, 'rugi_konsisten': True},
    {'hari': 60, 'untung_edge': -7.14, 'untung_konsisten': True,  'rugi_edge': 3.06, 'rugi_konsisten': True},
]



def _posisi_label(rasio, drift=None):
    """drift dipertahankan di tanda tangan demi pemanggil lama; tidak dipakai
    lagi sejak cabang DRIFT_BATAS_RUGI gagal replikasi (lihat catatan di atas)."""
    if rasio is None:
        return None, 'netral', 'Harga modal bandar tidak bisa dihitung.'
    if rasio > MODAL_AMBANG:
        return ('bandar untung >5%', 'merah',
                'Pembeli besar sedang untung %.1f%% di atas modalnya -- mereka punya ruang '
                'dan insentif untuk melepas. CATATAN: pembacaan ini gagal direplikasi di '
                'luar sampel (2016-2025, 21 emiten: edge +1,16, tanda terbalik dari kalibrasi). '
                'Perlakukan sebagai pengamatan, bukan sinyal.' % rasio)
    if rasio < -MODAL_AMBANG:
        return ('bandar rugi >5%', 'hijau',
                'Pembeli besar sedang rugi %.1f%% dari modalnya. Di data kalibrasi kelompok ini '
                'lebih baik, tapi di luar sampel keunggulannya hilang (edge -0,10 sepanjang '
                '2016-2025). Perlakukan sebagai pengamatan, bukan sinyal.' % abs(rasio))
    return ('sekitar impas', 'kuning',
            'Harga bergerak di sekitar modal rata-rata pembeli besar (%.1f%%).' % rasio)


def harga_modal(stock, hari=None, df=None):
    """
    Harga beli rata-rata tertimbang lot SELURUH broker pembeli selama N hari
    terakhir, dibanding harga penutupan terakhir.

    Sengaja memakai semua broker sisi beli, bukan Top5 saja: yang ditanya
    "berapa modal pihak yang sedang mengangkut", dan Top5 harian berganti
    komposisi sehingga tidak mewakili satu posisi.
    """
    hari = hari or MODAL_HARI
    if df is None:
        from .broker_ledger import load
        df, _ = load()
    if df is None:
        return None

    sub = df[(df['stock'].astype(str) == stock.upper()) & (df['side'].astype(str) == 'buy')]
    sub = sub.dropna(subset=['avg_price'])
    if sub.empty:
        return None

    batas = sub['date'].max() - pd.Timedelta(days=hari * 2)
    sub = sub[sub['date'] >= batas]
    lot = float(sub['lot'].sum())
    if lot <= 0:
        return None
    modal = float((sub['lot'] * sub['avg_price']).sum()) / lot

    # harga & drift terakhir dari Summary
    import os
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock.upper())
    close = drift = None
    if os.path.exists(path):
        try:
            d = pd.read_csv(path, usecols=['Date', 'Close'])
            d['Date'] = pd.to_datetime(d['Date'], format='%d-%b-%y', errors='coerce')
            d = d.dropna(subset=['Date']).sort_values('Date')
            c = pd.to_numeric(d['Close'], errors='coerce').dropna()
            if len(c):
                close = float(c.iloc[-1])
                if len(c) > hari:
                    c0 = float(c.iloc[-hari - 1])
                    if c0 > 0:
                        drift = (close - c0) / c0 * 100.0
        except Exception:
            pass

    rasio = ((close - modal) / modal * 100.0) if (close and modal) else None
    posisi, verdict, penjelasan = _posisi_label(rasio)

    return {
        'stock': stock.upper(),
        'hari': hari,
        'harga_modal': round(modal, 2),
        'harga_sekarang': round(close, 2) if close else None,
        'rasio': round(rasio, 2) if rasio is not None else None,
        'drift': round(drift, 2) if drift is not None else None,
        'lot_dasar': round(lot, 0),
        'posisi': posisi,
        'verdict': verdict,
        'penjelasan': penjelasan,
    }


MODAL_CACHE = str(_runtime_file('', 'modal_bandar_cache.pkl'))
# Modal bandar dibaca murni dari buku besar broker; harga Summary
# tidak ikut menentukannya.

# Kalibrasi versi D, SETELAH dikendalikan terhadap drift harga 60 hari.
# Sinyalnya bertahan di saham yang sedang TURUN; di saham datar/naik melemah
# atau tidak konsisten. Itu dinyatakan apa adanya, bukan disembunyikan.
KALIBRASI_MODAL = {
    'horizon': 20,
    'n_total': 64288,
    'metode': 'akuntansi posisi per broker, FIFO',
    'periode': 'Jan - Sep 2026',
    'baris': [
        {'drift': 'turun >5%', 'posisi': 'bandar rugi >5%', 'n': 35173, 'win': 49.8, 'edge': 2.66, 'konsisten': True},
        {'drift': 'turun >5%', 'posisi': 'impas', 'n': 7354, 'win': 35.4, 'edge': -5.62, 'konsisten': True},
        {'drift': 'turun >5%', 'posisi': 'bandar untung >5%', 'n': 941, 'win': 32.9, 'edge': -9.03, 'konsisten': True},
        {'drift': 'datar', 'posisi': 'bandar rugi >5%', 'n': 4952, 'win': 47.2, 'edge': 0.69, 'konsisten': True},
        {'drift': 'datar', 'posisi': 'impas', 'n': 6028, 'win': 43.6, 'edge': -4.84, 'konsisten': True},
        {'drift': 'datar', 'posisi': 'bandar untung >5%', 'n': 611, 'win': 41.6, 'edge': -5.36, 'konsisten': True},
        {'drift': 'naik 5-20%', 'posisi': 'bandar rugi >5%', 'n': 1780, 'win': 47.0, 'edge': 3.97, 'konsisten': True},
        {'drift': 'naik 5-20%', 'posisi': 'impas', 'n': 2555, 'win': 43.8, 'edge': -1.14, 'konsisten': False},
        {'drift': 'naik 5-20%', 'posisi': 'bandar untung >5%', 'n': 897, 'win': 39.8, 'edge': -7.18, 'konsisten': False},
        {'drift': 'naik 20-50%', 'posisi': 'bandar rugi >5%', 'n': 706, 'win': 35.6, 'edge': -6.77, 'konsisten': True},
        {'drift': 'naik 20-50%', 'posisi': 'impas', 'n': 715, 'win': 39.3, 'edge': -2.44, 'konsisten': True},
        {'drift': 'naik >50%', 'posisi': 'bandar rugi >5%', 'n': 377, 'win': 40.3, 'edge': -6.15, 'konsisten': True},
    ],
}


def _posisi_per_broker(df):
    """
    Posisi & modal TIAP BROKER di tiap saham, memakai FIFO.

    KENAPA PER BROKER.
    Percobaan sebelumnya menghitung posisi dari total beli minus total jual
    SELURUH broker. Di tingkat pasar itu selalu ~nol -- tiap transaksi punya
    pembeli dan penjual sekaligus -- sehingga posisinya runtuh dan "modal"
    cuma mengikuti harga terakhir: dari 572 emiten hanya 13 yang bergerak
    lebih dari 5%. Angka yang terlihat rapi tapi tidak berarti apa-apa.

    KENAPA FIFO, BUKAN BIAYA RATA-RATA BERGERAK.
    Dengan biaya rata-rata, pembelian setahun lalu berbobot sama dengan
    pembelian kemarin. FIFO mengasumsikan yang dijual adalah lot TERTUA
    lebih dulu, sehingga yang tersisa di tangan adalah pembelian TERBARU --
    dan harga terkini itulah yang menentukan perilaku bandar sekarang.
    Diuji (setelah dikendalikan drift harga 60 hari, horizon 20 hari):

        drift        posisi              biaya rata2   FIFO
        turun >20%   bandar rugi >10%       +3,41     +4,16
        turun >20%   impas / untung         -8,47     -6,83
        turun 5-20%  bandar rugi >10%       +2,95     +4,25
        turun 5-20%  impas / untung         -5,48     -6,35

    FIFO unggul di 3 dari 4 sel, dan paling jelas di sisi yang dipakai
    bertindak (bandar rugi): +4,16 dan +4,25 vs +3,41 dan +2,95.

    BATAS YANG HARUS DIINGAT: posisi mulai dihitung dari NOL pada hari
    pertama data (2 Jan 2026). Broker tentu sudah memegang saham sebelum
    itu, jadi yang terukur adalah modal dari tranche yang terbentuk SEJAK
    awal data, bukan modal sepanjang hidup posisi mereka.
    """
    import collections

    d = df.copy()
    for c in ('side', 'stock', 'broker'):
        d[c] = d[c].astype(str)
    piv = (d.groupby(['stock', 'broker', 'date', 'side'], observed=True)
             .agg(lot=('lot', 'sum'), lp=('avg_price', 'mean')).reset_index())
    beli = piv[piv['side'] == 'buy'].rename(columns={'lot': 'blot', 'lp': 'bp'}).drop(columns='side')
    jual = piv[piv['side'] == 'sell'].rename(columns={'lot': 'slot'}).drop(columns=['side', 'lp'])
    m = pd.merge(beli, jual, on=['stock', 'broker', 'date'], how='outer').fillna({'blot': 0, 'slot': 0})
    m = m.sort_values(['stock', 'broker', 'date']).reset_index(drop=True)

    per_hari = {}
    for (stock, _br), g in m.groupby(['stock', 'broker'], observed=True):
        lots = collections.deque()   # [lot, harga] urut waktu, tertua di depan
        for blot, bp, slot, tgl in zip(g['blot'].values, g['bp'].values,
                                       g['slot'].values, g['date'].values):
            if blot > 0 and np.isfinite(bp) and bp > 0:
                lots.append([blot, bp])
            if slot > 0:
                sisa = slot
                while sisa > 1e-9 and lots:
                    ambil = min(sisa, lots[0][0])
                    lots[0][0] -= ambil
                    sisa -= ambil
                    if lots[0][0] <= 1e-9:
                        lots.popleft()
            total = sum(l for l, _ in lots)
            if total > 1e-9:
                per_hari.setdefault((stock, tgl), []).append(
                    (total, sum(l * h for l, h in lots) / total))
    return per_hari


def _modal_terakhir(force=False):
    """{stock: (modal, n_broker, modal_lalu)} pada tanggal terakhir. Di-cache."""
    if not force and os.path.exists(MODAL_CACHE):
        try:
            with open(MODAL_CACHE, 'rb') as fh:
                c = pickle.load(fh)
            if c.get('ts', 0) >= _ledger_terbaru():
                return c['data']
        except Exception:
            pass

    from .broker_ledger import load
    df, _meta = load()
    if df is None:
        return {}

    per_hari = _posisi_per_broker(df)
    # kelompokkan per saham lalu ambil tanggal terakhir & pembanding
    per_saham = {}
    for (stock, tgl), lst in per_hari.items():
        per_saham.setdefault(stock, []).append((tgl, lst))

    out = {}
    for stock, deret in per_saham.items():
        deret.sort(key=lambda x: x[0])

        def hitung(lst):
            tot = sum(x[0] for x in lst)
            return (sum(x[0] * x[1] for x in lst) / tot, len(lst)) if tot > 0 else (None, 0)

        modal, nb = hitung(deret[-1][1])
        modal_lalu = None
        if len(deret) > MODAL_HARI_BANDING:
            modal_lalu, _ = hitung(deret[-1 - MODAL_HARI_BANDING][1])
        if modal:
            out[stock] = (modal, nb, modal_lalu)

    try:
        with open(MODAL_CACHE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'data': out}, fh)
    except Exception:
        pass
    return out



def modal_ringkas(stock):
    """
    Modal bandar satu emiten, versi ringan untuk kartu Ringkasan Sinyal.

    Memakai cache FIFO yang sama dengan tabel Sidik Jari Broker (bukan
    harga_modal(), yang masih memakai metode lama sisi-beli saja) supaya
    angka di kartu dan di tabel tidak pernah berbeda.

    Sengaja tidak mengembalikan verdict hijau/merah: pembacaan arah dari
    posisi modal GAGAL direplikasi di luar sampel (lihat catatan panjang di
    atas). Yang dikembalikan cuma faktanya, dengan verdict 'netral', supaya
    kartu tidak memberi lampu hijau/merah yang tidak punya dasar.
    """
    import glob
    import os as _os

    stock = (stock or '').upper()
    if not stock:
        return None

    # JANGAN PERNAH memicu _modal_terakhir() dari sini. Fungsi ini dipanggil
    # pada SETIAP pembukaan halaman saham dan setiap kartu di gambar
    # watchlist; kalau cache-nya kedaluwarsa, ia membangun ulang FIFO dari
    # 3,5 juta baris buku besar -- sekitar dua menit. Akibatnya nyata:
    # permintaan /saham-data/<kode> menggantung dan kartu Ringkasan Sinyal
    # tidak pernah muncul sama sekali.
    #
    # Karena itu cache dibaca LANGSUNG dari berkas, tanpa peduli TTL. Angka
    # yang agak lama jauh lebih baik daripada halaman yang tidak terbuka,
    # dan kalau memang belum pernah dibangun, kartu cukup bilang begitu.
    # Pembangunan ulangnya milik scan_modal() -- dipanggil dari halaman
    # Sidik Jari Broker, yang memang dibuka dengan sadar.
    peta = None
    if _os.path.exists(MODAL_CACHE):
        try:
            with open(MODAL_CACHE, 'rb') as fh:
                peta = pickle.load(fh).get('data')
        except Exception:
            peta = None
    if not peta or stock not in peta:
        return None
    modal, n_broker, _lalu = peta[stock]
    if not modal or modal <= 0:
        return None

    close = drift = gerak10 = None
    path = _os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
    if _os.path.exists(path):
        try:
            d = pd.read_csv(path, usecols=['Date', 'Close'])
            d['Date'] = pd.to_datetime(d['Date'], format='%d-%b-%y', errors='coerce')
            d = d.dropna(subset=['Date']).sort_values('Date')
            c = pd.to_numeric(d['Close'], errors='coerce').dropna()
            if len(c):
                close = float(c.iloc[-1])
                if len(c) > MODAL_HARI:
                    c0 = float(c.iloc[-MODAL_HARI - 1])
                    if c0 > 0:
                        drift = (close - c0) / c0 * 100.0
                # Gerak 10 hari dipakai kartu Ringkasan Sinyal untuk memberi
                # warna: bandar rugi + harga masih diam = hijau, bandar untung
                # + harga sudah bergerak jauh = merah. Nilainya BERTANDA;
                # kartu yang memutuskan mau memakai besarannya saja atau tidak.
                if len(c) > GERAK_HARI:
                    c10 = float(c.iloc[-GERAK_HARI - 1])
                    if c10 > 0:
                        gerak10 = (close - c10) / c10 * 100.0
        except Exception:
            pass
    if not close:
        return None

    rasio = (close - modal) / modal * 100.0
    if rasio > MODAL_AMBANG:
        posisi = 'bandar untung %.1f%%' % rasio
    elif rasio < -MODAL_AMBANG:
        posisi = 'bandar rugi %.1f%%' % abs(rasio)
    else:
        posisi = 'sekitar impas'
    return {
        'stock': stock,
        'harga_modal': round(float(modal), 2),
        'harga_sekarang': round(close, 2),
        'rasio': round(float(rasio), 2),
        'drift': round(float(drift), 2) if drift is not None else None,
        'hari_drift': MODAL_HARI,
        'gerak10': round(float(gerak10), 2) if gerak10 is not None else None,
        'hari_gerak': GERAK_HARI,
        'n_broker': int(n_broker),
        'posisi': posisi,
        'verdict': 'netral',
    }


def scan_modal(hari=None, stocks=None, force=False):
    """
    Modal bandar seluruh emiten. Memakai akuntansi posisi per broker --
    lihat _posisi_per_broker() untuk alasannya.
    """
    import glob

    # CATATAN: `hari` TIDAK lagi mengatur perhitungan modal. Sejak pindah ke
    # akuntansi posisi per broker, modal dihitung dari SELURUH riwayat
    # (posisi yang masih dipegang), bukan dari jendela bergulir -- dicek:
    # modal 881 emiten identik untuk jendela 5/20/60 hari. Parameter ini
    # sekarang hanya menentukan panjang kolom "drift" yang ditampilkan.
    hari = hari or MODAL_HARI
    modal_map = _modal_terakhir(force=force)
    if not modal_map:
        return {'available': False, 'message': 'Buku besar broker belum dibangun.'}

    harga = {}
    for path in glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')):
        s = os.path.basename(path)[:4]
        try:
            d = pd.read_csv(path, usecols=['Date', 'Close', 'Volume'])
            d['Date'] = pd.to_datetime(d['Date'], format='%d-%b-%y', errors='coerce')
            d = d.dropna(subset=['Date']).sort_values('Date')
            c = pd.to_numeric(d['Close'], errors='coerce').dropna()
            if not len(c):
                continue
            close = float(c.iloc[-1])
            drift = None
            if len(c) > hari:
                c0 = float(c.iloc[-hari - 1])
                if c0 > 0:
                    drift = (close - c0) / c0 * 100.0
            # ADV (rata-rata nilai transaksi harian, Rp) -- jendela 20 hari,
            # definisi & konstanta SAMA seperti jatuh_dalam.py/risiko.py
            # supaya angkanya bisa dibandingkan lintas halaman, bukan
            # metode baru yang cuma dipakai di sini.
            vol = pd.to_numeric(d['Volume'], errors='coerce').dropna()
            adv = None
            if len(c) >= 5 and len(vol) >= 5:
                adv = float(c.tail(20).mean() * vol.tail(20).mean())
            harga[s] = (close, drift, adv)
        except Exception:
            continue

    daftar = set(stocks) if stocks else None
    rows = []
    for stock, (modal, nb, modal_lalu) in modal_map.items():
        if daftar and stock not in daftar:
            continue
        if stock not in harga:
            continue
        close, drift, adv = harga[stock]
        if not close or not modal:
            continue
        rasio = (close - modal) / modal * 100.0
        posisi, verdict, penjelasan = _posisi_label(rasio, drift)

        rasio_b = ((close - modal_lalu) / modal_lalu * 100.0) if modal_lalu else None
        veto = bool(rasio < -MODAL_AMBANG and rasio_b is not None and rasio_b > VETO_AMBANG)
        if veto:
            verdict = 'merah'
            penjelasan = ('Terlihat aman (bandar rugi %.1f%%), TAPI dibanding modal %d hari lalu '
                          'posisinya sudah +%.1f%% -- mereka sudah average down, jadi tetap punya '
                          'alasan melepas.' % (abs(rasio), MODAL_HARI_BANDING, rasio_b))

        rows.append({
            'stock': stock, 'hari': hari,
            'harga_modal': round(float(modal), 2),
            'harga_sekarang': round(close, 2),
            'rasio': round(rasio, 2),
            'n_broker_pemegang': nb,
            'hari_banding': MODAL_HARI_BANDING,
            'harga_modal_banding': round(float(modal_lalu), 2) if modal_lalu else None,
            'rasio_banding': round(rasio_b, 2) if rasio_b is not None else None,
            'veto': veto,
            'drift': round(drift, 2) if drift is not None else None,
            'lot_dasar': None,
            'adv_value_b': round(adv / 1e9, 2) if adv is not None else None,
            'likuid': bool(adv is not None and adv >= LIKUID_MIN),
            'posisi': posisi, 'verdict': verdict, 'penjelasan': penjelasan,
        })

    rows.sort(key=lambda r: -(r['rasio'] or 0))
    counts = {}
    for r in rows:
        counts[r['posisi']] = counts.get(r['posisi'], 0) + 1

    return {
        'available': True,
        'rows': rows,
        'total': len(rows),
        'counts': counts,
        'hari': hari,
        'metode': 'akuntansi posisi per broker, FIFO (yang tersisa = pembelian terbaru)',
        'kalibrasi': KALIBRASI_MODAL,
        'kalibrasi_veto': KALIBRASI_VETO,
        'kalibrasi_metode': KALIBRASI_METODE,
        'n_veto': sum(1 for r in rows if r.get('veto')),
        'hari_banding': MODAL_HARI_BANDING,
        'sapuan_jendela': SAPUAN_JENDELA,
        'jendela_pilihan': MODAL_HARI,
        'as_of': time.strftime('%Y-%m-%d %H:%M'),
    }


def untuk_saham(stock, hari=5):
    """
    Siapa yang sedang net beli di satu saham beberapa hari terakhir, beserta
    TIPE PERILAKU-nya -- inilah gunanya sidik jari ini dalam pemakaian nyata.
    """
    from .broker_ledger import load
    df, _meta = load()
    if df is None:
        return {'available': False, 'message': 'Buku besar broker belum dibangun.'}

    sidik = build()
    tipe_map = {r['broker']: r for r in (sidik.get('rows') or [])}

    sub = df[df['stock'].astype(str) == stock.upper()].copy()
    if sub.empty:
        return {'available': False, 'message': 'Tidak ada data broker untuk %s.' % stock}

    batas = sub['date'].max() - pd.Timedelta(days=hari * 2)
    sub = sub[sub['date'] >= batas]
    sub['lot_net'] = np.where(sub['side'].astype(str) == 'buy', sub['lot'], -sub['lot'])

    agg = (sub.groupby('broker', observed=True)
              .agg(lot_net=('lot_net', 'sum'), nilai=('value', 'sum'),
                   harga_rata2=('avg_price', 'mean'))
              .reset_index())
    agg = agg[agg['lot_net'] != 0].sort_values('lot_net', ascending=False)

    baris = []
    for _, r in agg.iterrows():
        info = tipe_map.get(str(r['broker']), {})
        baris.append({
            'broker': str(r['broker']),
            'lot_net': round(float(r['lot_net']), 0),
            'nilai_m': round(float(r['nilai']) / 1e9, 2),
            'harga_rata2': round(float(r['harga_rata2']), 0) if np.isfinite(r['harga_rata2']) else None,
            'tipe': info.get('tipe', 'tidak dinilai'),
            'fwd_win': info.get('fwd_win'),
            'fwd_vs_baseline': info.get('fwd_vs_baseline'),
            'drift_saat_beli': info.get('drift_saat_beli'),
            'rata2_streak': info.get('rata2_streak'),
        })

    return {
        'available': True,
        'stock': stock.upper(),
        'hari': hari,
        'rows': baris,
        'pembeli': [b for b in baris if b['lot_net'] > 0][:15],
        'penjual': [b for b in baris if b['lot_net'] < 0][-15:][::-1],
        'baseline': sidik.get('baseline'),
    }
