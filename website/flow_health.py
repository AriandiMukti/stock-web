"""
Kesehatan arus pasca-sinyal: setelah sebuah sinyal muncul (dari Kering
Screener, Scanner Lab, atau manapun) dan harga bergerak, modul ini
menjawab pertanyaan yang tidak bisa dijawab harga sendirian --
"pergerakan ini asli atau cuma noise?"

KENAPA HARGA SAJA TIDAK CUKUP
Harga turun setelah sinyal bisa berarti dua hal yang berlawanan: bandar
benar-benar keluar (sinyal gagal), atau cuma koreksi wajar sementara
akumulasi tetap berjalan. Begitu juga harga naik: bisa kelanjutan
akumulasi sungguhan, bisa breakout palsu yang arusnya sudah berbalik
duluan. Membedakan keduanya butuh melihat ARUS (Net Top5, Retail), bukan
cuma harga.

METODE: PAKAI DEFINISI YANG SAMA, JENDELA YANG BEDA
bdm_screener_v2.py mendeteksi akumulasi dengan: korelasi kumulatif Net
Top5 naik terhadap waktu, dan korelasi kumulatif Retail turun terhadap
waktu, diambil yang PALING LEMAH dari keduanya sebagai skor. Modul ini
memakai definisi identik, tapi jendelanya SETELAH tanggal sinyal, bukan
sebelum -- supaya bisa dijawab: apakah pola yang memicu sinyal itu masih
bertahan sesudahnya?

Jendelanya SENGAJA hanya memakai hari SETELAH sinyal (signal_date+1
sampai checkpoint), tidak menjorok balik ke periode sebelum sinyal.
Kalau jendelanya dibiarkan menjorok balik, korelasi kuat dari sebelum
sinyal (yang sudah diketahui, itulah yang memicu sinyal) akan mengencerkan
sinyal pembalikan yang baru terjadi -- membuat pembalikan sungguhan
terlihat "masih sehat" padahal sudah tidak.

BATAS STATISTIK, DAN INI PENTING
Korelasi pada jendela pendek (5-10 hari) sangat berisik -- beberapa titik
data saja, satu hari aneh bisa membalik korelasinya. Checkpoint 5 hari
adalah pembacaan paling awal yang bisa didapat, bukan yang paling
dipercaya; checkpoint 21 hari jauh lebih stabil tapi hanya tersedia untuk
sinyal yang sudah cukup lama. Halaman yang memakai modul ini WAJIB
menunjukkan checkpoint mana yang tersedia dan mana yang belum, bukan
memaksakan checkpoint pendek seolah-olah sekuat yang panjang.
"""
import os

import numpy as np
import pandas as pd

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')

# Checkpoint dalam hari BURSA setelah tanggal sinyal. Menyamai HORIZONS
# yang sudah dipakai Scanner Lab (fwd20) dan Kering Screener (H=5..63)
# supaya angkanya bisa dibandingkan lintas halaman tanpa terjemahan.
CHECKPOINTS = [5, 10, 21]

# Di bawah ambang ini harga dianggap "sideways", bukan naik/turun --
# tanpa zona mati, pergerakan 0,3% akan diberi label "naik" atau "turun"
# padahal itu cuma noise harian biasa.
PRICE_DEADZONE_PCT = 2.0

# Skor pasca-sinyal di atas ini dianggap arus masih akumulasi, di bawah
# minus itu dianggap sudah berbalik (distribusi). Jauh lebih longgar
# daripada SKOR_MIN=0.75 milik screener aslinya dengan sengaja -- di sini
# pertanyaannya "apakah arus sudah berbalik", bukan "apakah ini akumulasi
# sekuat saat pertama terdeteksi". Menuntut 0.75 lagi pada jendela yang
# jauh lebih pendek akan membuat hampir semua checkpoint awal gagal
# lolos bukan karena arusnya buruk, tapi karena sampelnya kecil.
FLOW_THRESHOLD = 0.2

VERDICTS = {
    ('naik', 'akumulasi'): ('lanjutan', 'Lanjutan sungguhan',
        'Harga naik DAN arus tetap mengonfirmasi -- Top5 masih menambah, Retail masih mengurangi.'),
    ('naik', 'netral'): ('naik_lemah', 'Naik tanpa konfirmasi arus',
        'Harga naik tapi arus tidak jelas arahnya -- belum tentu didukung akumulasi lanjutan.'),
    ('naik', 'distribusi'): ('palsu', 'Rawan breakout palsu',
        'Harga naik TAPI arus sudah berbalik -- Top5 melambat/Retail masuk. Kenaikan tidak lagi didukung arus.'),
    ('sideways', 'akumulasi'): ('konsolidasi', 'Konsolidasi sehat',
        'Harga mendatar, tapi arus masih diam-diam mengakumulasi.'),
    ('sideways', 'netral'): ('belum_jelas', 'Belum jelas arahnya',
        'Harga mendatar dan arus juga tidak menunjukkan arah yang jelas.'),
    ('sideways', 'distribusi'): ('keluar_diam', 'Mulai keluar diam-diam',
        'Harga masih terlihat tenang, tapi arus sudah mulai berbalik -- sering mendahului penurunan harga.'),
    ('turun', 'akumulasi'): ('koreksi_sehat', 'Koreksi sehat',
        'Harga turun TAPI arus masih mengonfirmasi akumulasi -- Top5 masih menambah, Retail masih keluar. Pola khas koreksi wajar, bukan bandar kabur.'),
    ('turun', 'netral'): ('turun_belum_jelas', 'Turun, arus belum jelas',
        'Harga turun dan arus tidak cukup jelas untuk membedakan koreksi dari breakdown.'),
    ('turun', 'distribusi'): ('breakdown', 'Breakdown sungguhan',
        'Harga turun DAN arus juga berbalik -- Top5 melambat/Retail masuk. Ciri bandar benar-benar keluar, bukan sekadar koreksi.'),
}


def load_stock(stock):
    """Sama seperti live_scan.load_stock() -- fillna(0) WAJIB, lihat
    catatan di sana soal kenapa membiarkan NaN mengubah hasil rolling."""
    path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path).fillna(0)
    except Exception:
        return None
    if df.empty or 'Date' not in df.columns:
        return None
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
    for col in ['Close', 'Net Top5 All Lot', 'Retail']:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df.set_index('Date')


def _classify(price_pct, skor_post):
    if price_pct > PRICE_DEADZONE_PCT:
        arah_harga = 'naik'
    elif price_pct < -PRICE_DEADZONE_PCT:
        arah_harga = 'turun'
    else:
        arah_harga = 'sideways'

    if skor_post > FLOW_THRESHOLD:
        arah_arus = 'akumulasi'
    elif skor_post < -FLOW_THRESHOLD:
        arah_arus = 'distribusi'
    else:
        arah_arus = 'netral'

    key, label, penjelasan = VERDICTS[(arah_harga, arah_arus)]
    return {'key': key, 'label': label, 'penjelasan': penjelasan,
            'arah_harga': arah_harga, 'arah_arus': arah_arus}


def check(stock, signal_date, checkpoints=None, df=None):
    """
    Kesehatan arus pasca-sinyal untuk satu emiten di satu tanggal sinyal,
    pada tiap checkpoint hari bursa yang tersedia.

    Dipakai sebagai fungsi mandiri (bisa dipanggil untuk KODE+TANGGAL
    APAPUN, tidak terikat pada Kering Screener maupun Scanner Lab) --
    supaya bisa muncul di Halaman Saham, Kering Screener, dan Scanner Lab
    tanpa menulis ulang logikanya tiga kali.
    """
    checkpoints = checkpoints or CHECKPOINTS
    stock = (stock or '').strip().upper()
    signal_date = pd.Timestamp(signal_date)

    if df is None:
        df = load_stock(stock)
    if df is None or df.empty:
        return {'available': False, 'message': 'Tidak ada data harian untuk %s.' % stock}

    idx = df.index
    # searchsorted() pada DatetimeIndex mengembalikan np.int64, bukan int
    # Python biasa. Dibungkus int() di sini supaya SEMUA yang diturunkan
    # darinya (i1, n, dst.) ikut jadi tipe Python biasa -- np.int64/
    # np.bool_ bisa membuat jsonify() gagal atau berlaku tak terduga saat
    # baris ini dikirim ke browser.
    pos = int(idx.searchsorted(signal_date))
    if pos >= len(idx) or idx[pos] != signal_date:
        # Tanggal sinyal bukan hari bursa persis (jarang, tapi bisa
        # terjadi kalau data direvisi) -- pakai hari bursa berikutnya
        # yang terdekat.
        if pos >= len(idx):
            return {'available': False, 'message': 'Tanggal sinyal di luar rentang data.'}

    close = df['Close']
    net5 = df['Net Top5 All Lot']
    retail = df['Retail']
    entry_price = float(close.iloc[pos])

    results = []
    for h in checkpoints:
        i1 = pos + h
        if i1 >= len(idx):
            results.append({'horizon': h, 'available': False,
                            'message': 'Belum %d hari bursa sejak sinyal.' % h})
            continue

        window = slice(pos + 1, i1 + 1)   # STRICTLY setelah signal_date
        n = i1 - pos
        if n < 3:
            results.append({'horizon': h, 'available': False,
                            'message': 'Jendela terlalu pendek untuk dihitung.'})
            continue

        t = np.arange(n, dtype=float)
        top5_kum = net5.iloc[window].cumsum().values
        ritel_kum = retail.iloc[window].cumsum().values

        def corr(series):
            if np.std(series) == 0 or np.std(t) == 0:
                return None
            return float(np.corrcoef(series, t)[0, 1])

        corr_top5 = corr(top5_kum)
        corr_ritel = corr(ritel_kum)
        if corr_top5 is None or corr_ritel is None:
            results.append({'horizon': h, 'available': False,
                            'message': 'Arus datar di jendela ini, korelasi tidak terdefinisi.'})
            continue

        skor_post = min(corr_top5, -corr_ritel)
        exit_price = float(close.iloc[i1])
        price_pct = (exit_price / entry_price - 1) * 100 if entry_price else 0.0

        verdict = _classify(price_pct, skor_post)
        results.append({
            'horizon': h, 'available': True, 'n_hari': int(n),
            'price_pct': round(price_pct, 2),
            'corr_top5': round(corr_top5, 2), 'corr_ritel': round(corr_ritel, 2),
            'skor_post': round(skor_post, 2),
            'low_sample': bool(n < 8),   # peringatan sampel kecil, bukan disembunyikan
            **verdict,
        })

    return {
        'available': True, 'stock': stock,
        'signal_date': signal_date.strftime('%Y-%m-%d'),
        'entry_price': entry_price,
        'as_of': idx[-1].strftime('%Y-%m-%d'),
        'checkpoints': results,
    }


def check_current(stock, window=5, df=None):
    """
    Sama seperti check(), tapi TIDAK di-anchor ke tanggal sinyal --
    jendelanya H-`window` sampai HARI TERAKHIR yang datanya tersedia
    (mengambang mengikuti "sekarang"), bukan menempel ke satu tanggal
    sinyal historis. Dipakai supaya Kesehatan Arus SELALU tersedia
    walau tidak ada sinyal scanner aktif untuk ticker itu.

    Metodenya identik dengan check() (korelasi kumulatif Net Top5 naik
    & Retail turun terhadap waktu, diambil yang paling lemah) -- cuma
    titik jangkarnya beda. Karena jendelanya selalu bergerak, batas
    statistik yang sama tetap berlaku: window pendek (5 hari) tetap
    berisik, low_sample tetap ditandai jelas, bukan disembunyikan.
    """
    stock = (stock or '').strip().upper()
    if df is None:
        df = load_stock(stock)
    if df is None or df.empty:
        return {'available': False, 'message': 'Tidak ada data harian untuk %s.' % stock}

    idx = df.index
    n_total = len(idx)
    if n_total < window + 1:
        return {'available': False, 'message': 'Data terlalu pendek untuk jendela %d hari.' % window}

    close = df['Close']
    net5 = df['Net Top5 All Lot']
    retail = df['Retail']

    i1 = n_total - 1
    pos = i1 - window
    entry_price = float(close.iloc[pos])

    window_slice = slice(pos + 1, i1 + 1)
    t = np.arange(window, dtype=float)
    top5_kum = net5.iloc[window_slice].cumsum().values
    ritel_kum = retail.iloc[window_slice].cumsum().values

    def corr(series):
        if np.std(series) == 0 or np.std(t) == 0:
            return None
        return float(np.corrcoef(series, t)[0, 1])

    corr_top5 = corr(top5_kum)
    corr_ritel = corr(ritel_kum)
    if corr_top5 is None or corr_ritel is None:
        return {'available': False, 'message': 'Arus datar di jendela ini, korelasi tidak terdefinisi.'}

    skor_post = min(corr_top5, -corr_ritel)
    exit_price = float(close.iloc[i1])
    price_pct = (exit_price / entry_price - 1) * 100 if entry_price else 0.0

    verdict = _classify(price_pct, skor_post)
    return {
        'available': True, 'stock': stock, 'window': window,
        'as_of': idx[i1].strftime('%Y-%m-%d'),
        'price_pct': round(price_pct, 2),
        'corr_top5': round(corr_top5, 2), 'corr_ritel': round(corr_ritel, 2),
        'skor_post': round(skor_post, 2),
        'low_sample': bool(window < 8),
        **verdict,
    }
