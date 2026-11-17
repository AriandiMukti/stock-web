"""
Reinforcement learning untuk trading: satu kebijakan yang memutuskan
SEKALIGUS saham mana yang dibeli, seberapa besar porsinya, di mana take
profit dan stop loss-nya, dan berapa lama ditahan.

======================================================================
KENAPA BENTUKNYA SEPERTI INI
======================================================================
Permintaannya adalah mengoptimalkan tujuh hal bersamaan (jenis saham,
jumlah saham, TP, SL, porsi per transaksi, porsi per saham, lama hold,
kondisi beli/jual). Cara paling naif -- satu agen dengan aksi kontinu di
atas 900 emiten -- punya ruang aksi yang praktis tak terbatas sementara
datanya cuma ~4.000 hari bursa. Itu resep menghafal, bukan belajar.

Maka ruang aksinya DIFAKTORKAN jadi beberapa kepala keputusan diskret
yang dipakai bersama satu jaringan:

    masuk?   {tidak, ya}                  -> jenis & jumlah saham
    porsi    {4%, 8%, 15%, 25%} ekuitas   -> porsi per transaksi/saham
    TP       {1,5x  3x  5x  8x} ATR       -> take profit
    SL       {1x  2x  3x  5x} ATR         -> stop loss
    hold     {5, 10, 21, 60} hari         -> lama tahan maksimum
    keluar?  {tahan, jual sekarang}       -> jual lebih awal

"Kondisi beli dan jual ketika apa" TIDAK dijadikan kepala keputusan --
itu justru FUNGSI yang dipelajari: state -> distribusi aksi. Halaman
Research membacanya balik dengan membandingkan profil fitur saat agen
memilih masuk versus saat ia melewatkan (lihat `profil_masuk`).

TP/SL dinyatakan dalam KELIPATAN ATR, bukan persen tetap. Stop 3% itu
sangat longgar untuk BBCA dan sangat ketat untuk saham gorengan; dalam
satuan ATR, satu kebijakan yang sama bisa dipakai lintas emiten.

======================================================================
YANG MEMBUAT ANGKANYA BOLEH DIPERCAYA (ATAU TIDAK)
======================================================================
Modul ini dibangun dengan asumsi hasil RL default-nya MENIPU, jadi semua
pelindung berikut wajib, bukan opsional:

1. WALK-FORWARD. Agen dilatih di jendela N tahun, diuji di tahun
   BERIKUTNYA yang belum pernah dilihat, lalu jendela digeser. Tidak ada
   satu pun angka utama di halaman yang berasal dari periode latih.
   Ini menegakkan aturan yang sudah dipegang modul lain di app ini
   (lihat pattern_miner.py & screener_side.py: temuan in-sample di app
   ini berulang kali runtuh di luar sampel).

2. EKSEKUSI DI HARI BERIKUTNYA. Keputusan dibuat dari data sampai
   penutupan hari t, order tereksekusi di PEMBUKAAN hari t+1. Tidak ada
   satu pun fitur yang memakai harga hari yang sama dengan eksekusinya.
   Satu-satunya pengecualian (opsional, grup 'lintas'): sesi luar negeri
   bertanggal t, yang selesai sebelum BEI buka t+1 -- lihat FITUR_EKSTRA.

3. BIAYA NYATA. Fee beli 0,15%, fee jual 0,25% (sudah termasuk pajak
   final 0,1%), plus slippage dua arah. Backtest tanpa biaya di pasar
   Indonesia bisa terlihat untung padahal rugi.

4. BATAS LIKUIDITAS. Order dibatasi maksimum sekian persen dari nilai
   transaksi rata-rata 20 hari saham itu. Tanpa ini agen akan "membeli"
   Rp10 miliar saham yang sehari cuma ditransaksikan Rp200 juta.

5. LOT 100 LEMBAR. Porsi dibulatkan ke bawah ke kelipatan lot, jadi
   saham mahal memang tidak bisa diporsi halus -- persis seperti nyata.

6. PEMBANDING WAJIB. Tiap fold dibandingkan dengan beli-tahan bobot
   sama dan dengan kebijakan ACAK yang ruang aksinya identik. Kebijakan
   acak itu penting: kalau agen tidak mengalahkan aksi acak, yang
   terukur cuma efek pasar dan efek ukuran posisi, bukan kecerdasan.

7. BEBERAPA SEED. Satu seed tidak memberi tahu apa pun soal seberapa
   besar hasilnya cuma keberuntungan inisialisasi. Sebaran antar-seed
   ditampilkan berdampingan dengan rata-ratanya.

======================================================================
EMPAT KEPUTUSAN DESAIN YANG DITETAPKAN, BUKAN DITEBAK
======================================================================
1. SUMBER DATA. Harga & transaksi seluruhnya dari Yahoo Finance. Berkas
   Daily/Summary dan modul-modul lain app ini berperan sebagai SINYAL
   PENDUKUNG saja (opsional, default mati), bukan tulang punggung data.
2. REWARD ABSOLUT sebagai default: yang dikejar untung, bukan selisih
   terhadap IHSG. Konsekuensinya memegang kas bernilai reward nol.
3. TIDAK BERDAGANG ITU BOLEH. Agen tidak dipaksa punya posisi. Karena
   "diam" jadi keluaran yang sah, ia harus TERUKUR: tiap fold melaporkan
   eksposur rata-rata, persen hari terisi, dan rentetan kosong
   terpanjang, dan ada vonis khusus untuk agen yang memilih diam.
4. UNIVERSE TIDAK DIBATASI. Bisa seluruh daftar emiten app ini. Yang
   membuatnya muat: latihan mengambil sampel acak beberapa puluh emiten
   per episode sementara evaluasi memakai universe penuh (lihat _iris).

======================================================================
BATAS YANG TIDAK BISA DIHILANGKAN
======================================================================
- Data OHLC Yahoo Finance untuk emiten IDX: harga penutupan sudah
  disesuaikan corporate action, tapi kualitas emiten kecil/tidak likuid
  lebih buruk (bolong, volume nol berhari-hari). Universe likuid
  dianjurkan.
- Emiten yang sudah delisting tidak ada di Yahoo, jadi ada BIAS
  BERTAHAN HIDUP: universe apa pun yang dipilih hari ini otomatis berisi
  perusahaan yang selamat sampai hari ini. Memakai "semua emiten" TIDAK
  menghilangkan ini -- daftar emitennya tetap daftar hari ini.
- Pemangkasan ke N emiten paling likuid memakai peringkat yang dihitung
  dari seluruh periode, jadi fold-fold awal "tahu" emiten mana yang akan
  likuid belakangan. Kebocorannya di tingkat pemilihan semesta, bukan
  sinyal, tapi tetap nyata. Set batasnya 0 untuk menghilangkannya.
- Sinyal arus broker (Net Top5, ritel) dari folder Daily/Summary hanya
  ada ~161 hari bursa (Jan-Sep 2026). Terlalu pendek untuk melatih RL.
  Itu sebabnya opsinya default MATI: kalau dinyalakan, fitur arus diisi
  nol untuk hampir seluruh sejarah dan hanya hidup di fold terakhir --
  berguna untuk memeriksa apakah agen memakainya, bukan untuk mengklaim
  hasil.
- Reward dihitung dari perubahan log-ekuitas portofolio, sementara satu
  langkah waktu berisi BANYAK aksi (satu per emiten). Kredit dibagi rata
  ke semua aksi pada hari itu. Ini penyederhanaan standar di RL
  portofolio, dan ia membuat aksi yang bagus di hari yang buruk ikut
  dihukum.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import hashlib
import math
import os
import pickle
import time

import numpy as np
import pandas as pd

from . import research

CACHE_DIR = str(_runtime_file('', 'research_cache'))
CACHE_TTL = 60 * 60 * 12

# ---- ruang aksi -----------------------------------------------------------
PORSI_GRID = [0.04, 0.08, 0.15, 0.25]      # bagian ekuitas per transaksi
TP_GRID = [2.0, 4.0, 6.0, 10.0]            # kelipatan ATR14 di atas harga masuk
SL_GRID = [1.5, 2.5, 4.0, 6.0]             # kelipatan ATR14 di bawah harga masuk
HOLD_GRID = [10, 21, 42, 120]              # batas hari bursa menahan posisi

# Kenapa batas bawah grid dinaikkan dari versi pertama (SL 1x ATR, hold 5
# hari): stop 1x ATR berada DI DALAM derau harian menurut definisi ATR --
# ia bukan pilihan risiko, ia stop-out yang hampir pasti kena. Diukur pada
# universe 120 emiten: dengan grid lama, rata-rata posisi bertahan 7,7 hari,
# ~230 transaksi setahun, dan ongkos+slippage sendirian memakan ~19% ekuitas
# per tahun -- cukup untuk menenggelamkan sinyal apa pun yang mungkin ada.
# Pilihan yang secara struktural pasti kalah oleh biaya dibuang dari grid;
# yang tersisa tetap mencakup gaya cepat maupun sabar.

FITUR = [
    'ret1', 'ret5', 'ret20', 'ret60', 'pos20', 'pos60',
    'ma20', 'ma50', 'ma200', 'atrpct', 'volrat', 'rsi',
    'dd250', 'mkt20', 'rs20', 'regime', 'likuid',
    'arus_top5', 'arus_ritel', 'arus_ada',
]
FITUR_LABEL = {
    'ret1': 'Return 1 hari', 'ret5': 'Return 5 hari', 'ret20': 'Return 20 hari',
    'ret60': 'Return 60 hari', 'pos20': 'Posisi dalam rentang 20 hari',
    'pos60': 'Posisi dalam rentang 60 hari', 'ma20': 'Jarak ke MA20',
    'ma50': 'Jarak ke MA50', 'ma200': 'Jarak ke MA200',
    'atrpct': 'Volatilitas (ATR/harga)', 'volrat': 'Volume vs rata-rata 20h',
    'rsi': 'RSI 14', 'dd250': 'Jarak dari puncak 250 hari',
    'mkt20': 'Return IHSG 20 hari', 'rs20': 'Kekuatan relatif vs IHSG',
    'regime': 'IHSG di atas MA200', 'likuid': 'Likuiditas (log nilai harian)',
    'arus_top5': 'Net Top5 broker 20h', 'arus_ritel': 'Arus ritel 20h',
    'arus_ada': 'Data arus tersedia',
}
# Fitur tambahan, per grup, default MATI -- supaya hasil lama tetap bisa
# diulang persis dan versi dengan/tanpa grup bisa dibandingkan di fold & seed
# yang sama (riset_pola_naik/rl_banding.py). Yang dimasukkan cuma yang sudah
# lolos uji luar sampel di modul lain, bukan semua data yang ada: dengan
# ~4.000 hari bursa tiap fitur ekstra adalah peluang baru untuk menghafal.
#
# lintas  : kabar semalam (riset_pola_naik/lintas_pasar.py, kabar_semalam.py).
#           Satu-satunya fitur yang memakai data SETELAH penutupan hari t:
#           sesi luar bertanggal t (S&P, futures komoditas) selesai ~03:00-05:00
#           WIB t+1, sebelum pembukaan BEI t+1 tempat order agen dieksekusi.
#           Jadi sah, asal keputusan dianggap diambil pagi sebelum pasar buka.
# sinyal  : tembus basis 30h / puncak 52 minggu + volume (tembus_basis.fitur,
#           rumus halaman /tembus-basis) dan support chart (replika
#           utilities.compute_levels, riset_pola_naik/chart_support.py).
# insider : jual insider 60 hari, digeser JEDA_INSIDER hari bursa karena
#           datanya ditarik ~sebulan sekali. Datanya baru ada sejak April
#           2026 -- sama seperti arus broker, nol di hampir seluruh sejarah,
#           jadi untuk memeriksa, bukan untuk mengklaim.
FITUR_EKSTRA = {
    'lintas': ['sp_semalam', 'kom_semalam', 'kembar'],
    'sinyal': ['s_basis', 's_puncak', 'umur_sinyal', 'jarak_sup', 'ada_sup', 'jebol_sup'],
    'insider': ['insider_jual60', 'insider_ada'],
}
FITUR_LABEL.update({
    'sp_semalam': 'S&P 500 semalam', 'kom_semalam': 'Komoditas kembaran semalam',
    'kembar': 'Saham komoditas (punya kembaran)',
    's_basis': 'Sinyal tembus basis 30h', 's_puncak': 'Sinyal puncak 52 minggu',
    'umur_sinyal': 'Hari sejak sinyal tembus terakhir', 'jarak_sup': 'Jarak ke support chart',
    'ada_sup': 'Ada support chart di bawah harga', 'jebol_sup': 'Jebol support chart (5h)',
    'insider_jual60': 'Jual insider 60h (terlihat)', 'insider_ada': 'Data insider tersedia',
})
LINTAS_SERI = ['^GSPC', 'BZ=F', 'GC=F', 'HG=F']
JEDA_INSIDER = 21

KONTEKS_POSISI = ['dipegang', 'laba_belum_nyata', 'lama_dipegang', 'bobot']
KONTEKS_PORTOFOLIO = ['kas', 'slot_terpakai', 'drawdown']
DIM_KONTEKS = len(KONTEKS_POSISI) + len(KONTEKS_PORTOFOLIO)
DIM = len(FITUR) + DIM_KONTEKS     # versi dasar; panel ber-fitur tambahan: len(panel['fitur'])


def _grup_ekstra(cfg):
    return [g for g, k in (('lintas', 'pakai_lintas'), ('sinyal', 'pakai_sinyal'),
                           ('insider', 'pakai_insider')) if cfg.get(k)]


def daftar_fitur(cfg):
    return FITUR + [x for g in _grup_ekstra(cfg) for x in FITUR_EKSTRA[g]]

# 21 emiten folder Test (New BDM\Test) -- semesta uji luar sampel yang sudah
# dipakai pattern_miner.py & screener_side.py. Dipakai ulang di sini supaya
# hasil RL bisa dibandingkan dengan temuan modul-modul itu di semesta sama.
TEST21 = ['ADRO', 'ANTM', 'BBCA', 'BBRI', 'BREN', 'BRMS', 'BRPT', 'BUMI',
          'CDIA', 'CUAN', 'HRUM', 'INDY', 'INKP', 'INTP', 'ISAT', 'PSAB',
          'PTBA', 'PTRO', 'TINS', 'TPIA']

LIKUID30 = ['BBCA', 'BBRI', 'BMRI', 'BBNI', 'TLKM', 'ASII', 'UNTR', 'ADRO',
            'ANTM', 'INCO', 'MDKA', 'PTBA', 'ITMG', 'INDF', 'ICBP', 'KLBF',
            'UNVR', 'SMGR', 'INTP', 'PGAS', 'JSMR', 'AKRA', 'CPIN', 'ERAA',
            'MEDC', 'INKP', 'TINS', 'BRPT', 'EXCL', 'MAPI']


# ==========================================================================
# Data
# ==========================================================================
def _cache_path(nama):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return str(_runtime_file('research_cache', nama))


def _unduh_harga(tickers, mulai, akhir, kanal):
    """
    OHLCV harian dari Yahoo Finance untuk emiten IDX (suffix .JK), di-cache
    ke disk. Di-cache karena satu sesi riset biasanya menjalankan beberapa
    run berturut-turut dengan universe sama -- mengunduh ulang tiap kali
    membuang menit dan berisiko kena rate limit Yahoo di tengah latihan.

    Diunduh per rombongan ~120 simbol, bukan sekaligus: dengan universe
    penuh (900+ emiten) satu permintaan raksasa gampang gagal separuh jalan
    dan menghanguskan seluruh unduhan. Per rombongan, kegagalan satu
    rombongan tidak menjatuhkan sisanya, dan kemajuannya bisa dilihat.
    """
    kunci = hashlib.md5(('|'.join(sorted(tickers)) + mulai + akhir).encode()).hexdigest()[:16]
    berkas = _cache_path('harga_%s.pkl' % kunci)
    if os.path.exists(berkas) and (time.time() - os.path.getmtime(berkas)) < CACHE_TTL:
        with open(berkas, 'rb') as f:
            data = pickle.load(f)
        kanal.log('Harga dibaca dari cache (%d emiten).' % len(data))
        return data

    import yfinance as yf
    kanal.log('Mengunduh %d emiten dari Yahoo Finance (%s s.d. %s)...'
              % (len(tickers), mulai, akhir))
    data = {}
    pendek = 0
    ROMBONGAN = 120
    for i in range(0, len(tickers), ROMBONGAN):
        if kanal.berhenti():
            raise RuntimeError('Dihentikan saat mengunduh data.')
        potong = tickers[i:i + ROMBONGAN]
        simbol = [t + '.JK' for t in potong]
        try:
            mentah = yf.download(simbol, start=mulai, end=akhir, interval='1d',
                                 progress=False, auto_adjust=True, group_by='ticker',
                                 threads=True)
        except Exception as exc:
            kanal.log('  rombongan %d-%d gagal: %s' % (i, i + len(potong), exc), 'warn')
            continue
        for t, s in zip(potong, simbol):
            try:
                df = mentah[s] if isinstance(mentah.columns, pd.MultiIndex) else mentah
            except KeyError:
                continue
            try:
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna(how='all')
            except KeyError:
                continue
            df = df[df['Close'] > 0]
            if len(df) >= 400:
                data[t] = df
            else:
                pendek += 1
        kanal.log('  %d/%d emiten diproses, %d terpakai.'
                  % (min(i + ROMBONGAN, len(tickers)), len(tickers), len(data)))
    with open(berkas, 'wb') as f:
        pickle.dump(data, f)
    kanal.log('Terunduh %d emiten dengan data memadai (%d dilewati karena '
              'riwayatnya < 400 hari).' % (len(data), pendek))
    return data


def _unduh_ihsg(mulai, akhir, kanal):
    berkas = _cache_path('ihsg_%s_%s.pkl' % (mulai, akhir))
    if os.path.exists(berkas) and (time.time() - os.path.getmtime(berkas)) < CACHE_TTL:
        with open(berkas, 'rb') as f:
            return pickle.load(f)
    import yfinance as yf
    df = yf.download('^JKSE', start=mulai, end=akhir, interval='1d',
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    s = df['Close'].dropna()
    with open(berkas, 'wb') as f:
        pickle.dump(s, f)
    kanal.log('IHSG: %d hari.' % len(s))
    return s


def _baca_arus(ticker):
    """
    Fitur arus broker dari Daily/Summary (Net Top5 + ritel). Hanya ada untuk
    2026 -- lihat catatan di docstring modul. Mengembalikan DataFrame kosong
    kalau berkasnya tidak ada, bukan melempar error: universe riset dipilih
    dari Yahoo dan tidak semua emitennya punya berkas Summary.
    """
    from .config import DAILY_PATH
    berkas = os.path.join(DAILY_PATH, 'Summary', '%s_Summary.csv' % ticker)
    if not os.path.exists(berkas):
        return None
    try:
        df = pd.read_csv(berkas)
        df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
        df = df.dropna(subset=['Date']).set_index('Date').sort_index()
        return df[['Net Top5 All Lot', 'Retail']]
    except Exception:
        return None


def _unduh_lintas(mulai, akhir, kanal):
    """Close harian S&P 500 + futures komoditas kembaran (Brent/emas/tembaga).
    Kalau Yahoo gagal, jatuh ke cache riset lintas_pasar (berhenti di tanggal
    unduhnya -- sisa hari terakhir jadi nol semalam, bukan error)."""
    berkas = _cache_path('rl_lintas_%s_%s.pkl' % (mulai, akhir))
    if os.path.exists(berkas) and (time.time() - os.path.getmtime(berkas)) < CACHE_TTL:
        with open(berkas, 'rb') as f:
            return pickle.load(f)
    seri = {}
    try:
        import yfinance as yf
        for k in LINTAS_SERI:
            df = yf.download(k, start=mulai, end=akhir, interval='1d',
                             progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            s = df['Close'].dropna()
            s = s[s > 0]
            if len(s) > 250:
                seri[k] = s
    except Exception as exc:
        kanal.log('Unduh data lintas pasar gagal: %s' % exc, 'warn')
    kurang = [k for k in LINTAS_SERI if k not in seri]
    if kurang:
        try:
            with open(str(_runtime_file('research_cache', 'lintas_pasar', 'global_2012.pkl')), 'rb') as f:
                g = pickle.load(f)['data']
            for k in kurang:
                if k in g:
                    seri[k] = g[k]['Close'].dropna()
            kanal.log('Lintas pasar %s diambil dari cache riset (s.d. %s).'
                      % (', '.join(kurang), max(seri[k].index[-1].date() for k in kurang
                                                if k in seri)), 'warn')
        except Exception as exc:
            kanal.log('Cache lintas pasar juga gagal: %s' % exc, 'warn')
    with open(berkas, 'wb') as f:
        pickle.dump(seri, f)
    kanal.log('Lintas pasar: %s.' % ', '.join('%s %d hari' % (k, len(s)) for k, s in seri.items()))
    return seri


def _baca_insider_jual(kanal):
    """Jumlah transaksi JUAL pasar oleh insider per emiten per tanggal
    TRANSAKSI. Pergeseran ke tanggal terlihat dilakukan di _fitur_ekstra."""
    try:
        from . import insider_activity as ia
        df = ia.load_all()
    except Exception as exc:
        kanal.log('Data insider tidak terbaca: %s' % exc, 'warn')
        return {}, None
    df = df[(df['action_type'] == 'ACTION_TYPE_SELL')
            & df['is_market_trade'].astype(bool)].dropna(subset=['date'])
    if df.empty:
        return {}, None
    hitung = {t: g['date'].dt.normalize().value_counts().sort_index()
              for t, g in df.groupby('ticker')}
    kanal.log('Insider jual: %d transaksi, %d emiten, %s s.d. %s -- di luar rentang '
              'itu fiturnya nol.' % (len(df), len(hitung), df['date'].min().date(),
                                    df['date'].max().date()), 'warn')
    return hitung, df['date'].min().normalize()


# ==========================================================================
# Fitur
# ==========================================================================
def _rsi(close, n=14):
    delta = close.diff()
    naik = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    turun = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = naik / turun.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _atr(df, n=14):
    tinggi, rendah, tutup = df['High'], df['Low'], df['Close']
    tutup_l = tutup.shift(1)
    tr = pd.concat([tinggi - rendah, (tinggi - tutup_l).abs(),
                    (rendah - tutup_l).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _fitur_satu(df, ihsg, arus):
    """Semua fitur untuk satu emiten. Setiap kolom hanya memakai data sampai
    penutupan hari itu -- tidak ada shift(-1) di mana pun."""
    tutup = df['Close']
    f = pd.DataFrame(index=df.index)
    f['ret1'] = tutup.pct_change(1)
    f['ret5'] = tutup.pct_change(5)
    f['ret20'] = tutup.pct_change(20)
    f['ret60'] = tutup.pct_change(60)

    lo20, hi20 = tutup.rolling(20).min(), tutup.rolling(20).max()
    lo60, hi60 = tutup.rolling(60).min(), tutup.rolling(60).max()
    f['pos20'] = (tutup - lo20) / (hi20 - lo20).replace(0, np.nan)
    f['pos60'] = (tutup - lo60) / (hi60 - lo60).replace(0, np.nan)
    f['ma20'] = tutup / tutup.rolling(20).mean() - 1
    f['ma50'] = tutup / tutup.rolling(50).mean() - 1
    f['ma200'] = tutup / tutup.rolling(200).mean() - 1

    atr = _atr(df)
    f['atrpct'] = atr / tutup
    nilai = tutup * df['Volume']
    f['volrat'] = df['Volume'] / df['Volume'].rolling(20).mean().replace(0, np.nan)
    f['rsi'] = _rsi(tutup) / 100.0
    f['dd250'] = tutup / tutup.rolling(250, min_periods=60).max() - 1
    f['likuid'] = np.log10(nilai.rolling(20).mean().clip(lower=1e6)) - 9.0

    ih = ihsg.reindex(df.index).ffill()
    f['mkt20'] = ih.pct_change(20)
    f['rs20'] = f['ret20'] - f['mkt20']
    f['regime'] = (ih > ih.rolling(200).mean()).astype(float)

    if arus is not None and len(arus):
        a = arus.reindex(df.index)
        top5 = a['Net Top5 All Lot'].rolling(20, min_periods=5).mean()
        ritel = a['Retail'].rolling(20, min_periods=5).mean()
        skala = df['Volume'].rolling(20).mean().replace(0, np.nan)
        f['arus_top5'] = (top5 * 100 / skala).clip(-2, 2)
        f['arus_ritel'] = (ritel * 100 / skala).clip(-2, 2)
        f['arus_ada'] = a['Net Top5 All Lot'].notna().astype(float)
    else:
        f['arus_top5'] = 0.0
        f['arus_ritel'] = 0.0
        f['arus_ada'] = 0.0

    f['atr_abs'] = atr
    f['adv'] = nilai.rolling(20).mean()
    return f


def _semalam(s, indeks):
    """log return sebuah seri luar dari tutup terakhir bertanggal <= hari bursa
    sebelumnya ke tutup terakhir bertanggal <= hari ini (lihat FITUR_EKSTRA)."""
    lv = np.log(s.astype(float))
    lv = lv[~lv.index.duplicated(keep='last')].sort_index()
    return lv.reindex(lv.index.union(indeks)).ffill().reindex(indeks).diff().clip(-0.2, 0.2)


def _fitur_ekstra(kode, df, grup, lintas, kembar, insider):
    f = pd.DataFrame(index=df.index)
    if 'lintas' in grup:
        sp = lintas.get('^GSPC')
        f['sp_semalam'] = _semalam(sp, df.index) if sp is not None else 0.0
        k = kembar.get(kode)
        if k and k in lintas:
            f['kom_semalam'] = _semalam(lintas[k], df.index)
            f['kembar'] = 1.0
        else:
            f['kom_semalam'] = 0.0
            f['kembar'] = 0.0

    if 'sinyal' in grup:
        from .tembus_basis import fitur as tb_fitur
        from .riset_pola_naik import chart_support as CS
        tb = tb_fitur(df)
        sb = tb['s_basis'].fillna(False).astype(bool)
        sp_ = tb['s_puncak'].fillna(False).astype(bool)
        f['s_basis'] = sb.astype(float)
        f['s_puncak'] = sp_.astype(float)
        nomor = pd.Series(np.arange(len(df), dtype=float), index=df.index)
        terakhir = nomor.where(sb | sp_).ffill()
        f['umur_sinyal'] = ((nomor - terakhir).fillna(60).clip(upper=60) / 60.0)

        lv = CS.per_emiten((kode, df))
        sup = lv['sup'].reindex(df.index) if lv is not None else pd.Series(np.nan, index=df.index)
        tutup = df['Close']
        f['ada_sup'] = sup.notna().astype(float)
        f['jarak_sup'] = (tutup / sup - 1).fillna(0).clip(0, 0.5)
        # definisi jebol riset (close < support kemarin x 0,97), ditahan 5
        # hari supaya agen yang sedang memegang masih sempat bereaksi
        jebol = (tutup < sup.shift(1) * 0.97).astype(float)
        f['jebol_sup'] = jebol.rolling(5, min_periods=1).max()

    if 'insider' in grup:
        hitung, mulai_data = insider
        h = hitung.get(kode)
        if h is not None:
            harian = h.reindex(h.index.union(df.index), fill_value=0).cumsum()
            kum = harian.reindex(df.index).ffill().fillna(0)   # transaksi s.d. hari itu
            terlihat = kum.shift(JEDA_INSIDER).fillna(0)
            f['insider_jual60'] = np.log1p((terlihat - terlihat.shift(60).fillna(0)).clip(lower=0))
        else:
            f['insider_jual60'] = 0.0
        if mulai_data is not None:
            f['insider_ada'] = pd.Series((df.index >= mulai_data).astype(float),
                                         index=df.index).shift(JEDA_INSIDER).fillna(0)
        else:
            f['insider_ada'] = 0.0
    return f


def bangun_panel(config, kanal):
    """
    Susun semua emiten jadi array sejajar [T, N]. Panel dibuat SEKALI untuk
    seluruh rentang, lalu fold walk-forward cuma mengiris barisnya -- jadi
    normalisasi per-fold tetap bisa dihitung dari periode latih saja tanpa
    perlu menghitung ulang fiturnya.
    """
    tickers = _universe(config, kanal)
    mulai = '%d-01-01' % (int(config['mulai_tahun']) - 2)   # 2 tahun ekstra untuk MA200 dst
    akhir = time.strftime('%Y-%m-%d')

    harga = _unduh_harga(tickers, mulai, akhir, kanal)
    if len(harga) < 3:
        raise RuntimeError('Data harga terlalu sedikit (%d emiten). '
                           'Periksa koneksi atau daftar emitennya.' % len(harga))

    # Pemangkasan likuiditas. Bukan soal selera: dengan universe penuh
    # (900+ emiten) panel fitur bisa lewat 400 MB dan tiap langkah PPO
    # memproses matriks 900 baris. Dipangkas ke N paling likuid supaya
    # muat, dengan CATATAN JUJUR bahwa peringkat likuiditas dihitung dari
    # SELURUH periode -- termasuk masa depan relatif terhadap fold-fold
    # awal. Itu bentuk kebocoran halus di tingkat pemilihan semesta (bukan
    # di tingkat sinyal), dan satu-satunya cara menghilangkannya adalah
    # memakai daftar likuid historis per tahun, yang tidak tersedia di sini.
    maks_emiten = int(config.get('maks_emiten') or 0)
    if maks_emiten and len(harga) > maks_emiten:
        skor = {t: float((df['Close'] * df['Volume']).median()) for t, df in harga.items()}
        simpan = sorted(skor, key=lambda t: -skor[t])[:maks_emiten]
        kanal.log('Dipangkas dari %d ke %d emiten paling likuid (median nilai '
                  'transaksi harian). Peringkatnya memakai seluruh periode, jadi '
                  'ada kebocoran ringan di tingkat pemilihan semesta.'
                  % (len(harga), maks_emiten), 'warn')
        harga = {t: harga[t] for t in simpan}

    ihsg = _unduh_ihsg(mulai, akhir, kanal)

    pakai_arus = bool(config.get('pakai_arus'))
    if pakai_arus:
        kanal.log('Sinyal arus broker DINYALAKAN -- ingat cakupannya cuma '
                  '~161 hari bursa (2026), jadi nol di hampir seluruh sejarah.', 'warn')

    grup = _grup_ekstra(config)
    nama_fitur = daftar_fitur(config)
    lintas, kembar, insider = {}, {}, ({}, None)
    if 'lintas' in grup:
        lintas = _unduh_lintas(mulai, akhir, kanal)
        from .rapat_agen import KEMBAR_KOMODITAS as kembar
    if 'insider' in grup:
        insider = _baca_insider_jual(kanal)
    if grup:
        kanal.log('Fitur tambahan: %s (%d fitur, total %d).'
                  % (', '.join(grup), len(nama_fitur) - len(FITUR), len(nama_fitur)))

    kanal.tahap('Menghitung fitur')
    kode = sorted(harga.keys())
    fitur_per = {}
    for i, t in enumerate(kode):
        arus = _baca_arus(t) if pakai_arus else None
        fitur_per[t] = _fitur_satu(harga[t], ihsg, arus)
        if grup:
            fitur_per[t] = fitur_per[t].join(
                _fitur_ekstra(t, harga[t], grup, lintas, kembar, insider))
        if kanal.berhenti():
            raise RuntimeError('Dihentikan saat menghitung fitur.')
        kanal.maju(0.05 + 0.10 * (i + 1) / len(kode))

    indeks = None
    for t in kode:
        indeks = harga[t].index if indeks is None else indeks.union(harga[t].index)
    indeks = indeks.sort_values()
    indeks = indeks[indeks >= pd.Timestamp('%d-01-01' % int(config['mulai_tahun']))]

    # float32, bukan float64: dengan universe penuh selisihnya ratusan MB,
    # dan presisi ganda tidak berarti apa-apa untuk harga saham IDX.
    T, N, F = len(indeks), len(kode), len(nama_fitur)
    op = np.full((T, N), np.nan, dtype=np.float32)
    hi = np.full((T, N), np.nan, dtype=np.float32)
    lo = np.full((T, N), np.nan, dtype=np.float32)
    cl = np.full((T, N), np.nan, dtype=np.float32)
    atr = np.full((T, N), np.nan, dtype=np.float32)
    adv = np.zeros((T, N), dtype=np.float32)
    X = np.zeros((T, N, F), dtype=np.float32)
    dapat_diperdagangkan = np.zeros((T, N), dtype=bool)

    for j, t in enumerate(kode):
        df = harga[t].reindex(indeks)
        f = fitur_per[t].reindex(indeks)
        ada = df['Close'].notna().values & (df['Volume'].fillna(0).values > 0)
        df = df.ffill()
        f = f.ffill()
        op[:, j] = df['Open'].values
        hi[:, j] = df['High'].values
        lo[:, j] = df['Low'].values
        cl[:, j] = df['Close'].values
        atr[:, j] = f['atr_abs'].values
        adv[:, j] = np.nan_to_num(f['adv'].values)
        X[:, j, :] = np.nan_to_num(
            f[nama_fitur].values.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        siap = f['ma200'].notna().values & f['atr_abs'].notna().values
        dapat_diperdagangkan[:, j] = ada & siap & (adv[:, j] > 0)

    # Return pasar harian bobot sama atas emiten yang layak hari itu. Dipakai
    # sebagai pembanding di dalam REWARD (bukan cuma di laporan): tanpa ini,
    # "tidak berdagang" bernilai reward 0 dan jadi optimum lokal yang sangat
    # kuat -- agen belajar diam saja, yang secara teknis benar (biaya nol)
    # tapi tidak menjawab apa pun. Diukur: dengan reward absolut, evaluasi
    # menghasilkan 0 transaksi di ketujuh fold.
    ret_besok = np.where(np.isfinite(cl[1:]) & np.isfinite(cl[:-1]) & (cl[:-1] > 0),
                         cl[1:] / np.where(cl[:-1] > 0, cl[:-1], np.nan) - 1, np.nan)
    layak_pasar = dapat_diperdagangkan[:-1]
    mkt = np.zeros(T, dtype=np.float32)
    with np.errstate(invalid='ignore'):
        for t in range(T - 1):
            m = layak_pasar[t] & np.isfinite(ret_besok[t])
            mkt[t] = float(np.clip(ret_besok[t][m].mean(), -0.35, 0.35)) if m.any() else 0.0

    kanal.log('Panel siap: %d hari bursa x %d emiten (%s s.d. %s), %.0f MB.'
              % (T, N, indeks[0].date(), indeks[-1].date(),
                 (X.nbytes + op.nbytes * 6) / 1e6))
    layak = dapat_diperdagangkan.sum(axis=1)
    kanal.log('Rata-rata emiten layak per hari: %.1f (minimum %d).'
              % (layak.mean(), layak.min()))

    return {
        'kode': kode, 'indeks': indeks, 'open': op, 'high': hi, 'low': lo,
        'close': cl, 'atr': atr, 'adv': adv, 'X': X, 'ok': dapat_diperdagangkan,
        'mkt': mkt, 'fitur': nama_fitur,
    }


def _iris(panel, a, b, kolom=None):
    """
    Potongan panel: baris [a,b) dan (opsional) sebagian kolom emiten,
    dikembalikan sebagai panel utuh yang berdiri sendiri mulai indeks 0.

    Ada supaya universe boleh sebesar apa pun. Melatih PPO langsung di atas
    900 emiten berarti tensor rollout [1500 hari, 900 emiten, 24 fitur] --
    sekitar setengah gigabyte untuk satu iterasi. Dengan potongan ini, tiap
    episode latihan mengambil sampel acak beberapa puluh emiten saja
    (matriksnya jadi ~1 MB), sementara EVALUASI tetap memakai universe
    penuh. Itu sah karena semua fiturnya relatif terhadap sahamnya sendiri
    dan tidak ada satu pun parameter per-emiten di jaringan -- kebijakannya
    memang harus buta identitas. Efek sampingnya menguntungkan: agen tidak
    bisa menghafal "BBRI biasanya naik".
    """
    if kolom is None:
        potong = lambda arr: arr[a:b]
        kode = list(panel['kode'])
    else:
        kolom = np.asarray(kolom)
        potong = lambda arr: (arr[a:b][:, kolom] if arr.ndim >= 2 else arr[a:b])
        kode = [panel['kode'][j] for j in kolom]
    return {
        'kode': kode,
        'indeks': panel['indeks'][a:b],
        'open': potong(panel['open']), 'high': potong(panel['high']),
        'low': potong(panel['low']), 'close': potong(panel['close']),
        'atr': potong(panel['atr']), 'adv': potong(panel['adv']),
        'X': potong(panel['X']), 'ok': potong(panel['ok']),
        'mkt': panel['mkt'][a:b], 'fitur': panel['fitur'],
    }


def _universe(config, kanal):
    pilih = config.get('universe', 'likuid30')
    if pilih == 'semua':
        from .models import stockList
        daftar = sorted(set(stockList))
        kanal.log('Universe "semua": %d kode dari daftar emiten app ini. Yang '
                  'riwayat Yahoo-nya < 400 hari akan gugur sendiri saat unduh.'
                  % len(daftar))
        return daftar
    if pilih == 'test21':
        daftar = list(TEST21)
    elif pilih == 'likuid30':
        daftar = list(LIKUID30)
    elif pilih == 'portofolio':
        # Daftarnya diisi endpoint (yang punya app context); thread riset ini
        # berjalan di luar konteks Flask jadi tidak bisa query DB sendiri.
        daftar = [s.upper() for s in (config.get('portofolio_kode') or [])]
        if len(daftar) < 5:
            kanal.log('Portofolio cuma %d emiten -- ditambah dari daftar likuid.'
                      % len(daftar), 'warn')
            daftar = sorted(set(daftar) | set(LIKUID30))
    else:
        daftar = [s.strip().upper() for s in str(config.get('kustom', '')).replace(',', ' ').split()
                  if s.strip()]
        if len(daftar) < 3:
            raise RuntimeError('Daftar emiten kustom minimal 3 kode.')
    kanal.log('Universe "%s": %d emiten -- %s' % (pilih, len(daftar), ', '.join(daftar)))
    return daftar


# ==========================================================================
# Simulator portofolio
# ==========================================================================
class Portofolio:
    """
    Satu perjalanan melewati rentang hari, digerakkan oleh sebuah kebijakan.

    Aturan waktu yang dipegang ketat: keputusan dibuat dari state pada
    PENUTUPAN hari t, eksekusi terjadi pada PEMBUKAAN hari t+1, dan TP/SL
    baru boleh kena mulai hari t+1 juga. Tanpa aturan ini backtest apa pun
    akan tampak jauh lebih untung daripada kenyataannya.
    """

    def __init__(self, panel, cfg, awal, akhir, mu, sd):
        self.p = panel
        self.cfg = cfg
        self.a, self.b = awal, akhir           # indeks hari [awal, akhir)
        self.mu, self.sd = mu, sd
        self.N = len(panel['kode'])

    def _state(self, t, kas, ekuitas, shares, harga_masuk, hari_dipegang, puncak):
        p = self.p
        X = (p['X'][t] - self.mu) / self.sd
        X = np.clip(X, -5, 5)
        # nan_to_num wajib: emiten yang belum listing punya Close NaN, dan
        # 0 lembar * NaN tetap NaN -- satu NaN di sini merambat ke seluruh
        # jaringan dan membuat semua logit jadi NaN tanpa error apa pun.
        tutup = np.nan_to_num(p['close'][t])
        nilai = shares * tutup
        dipegang = (shares > 0).astype(np.float32)
        laba = np.where(shares > 0, tutup / np.maximum(harga_masuk, 1e-9) - 1, 0.0)
        lama = np.where(shares > 0, hari_dipegang / 60.0, 0.0)
        bobot = nilai / max(ekuitas, 1e-9)
        n_buka = int((shares > 0).sum())
        ctx = np.array([kas / max(ekuitas, 1e-9),
                        n_buka / float(self.cfg['maks_posisi']),
                        ekuitas / max(puncak, 1e-9) - 1.0], dtype=np.float32)
        pos = np.stack([dipegang, np.clip(laba, -1, 3), lama, bobot], axis=1).astype(np.float32)
        return np.concatenate([X, pos, np.tile(ctx, (self.N, 1))], axis=1).astype(np.float32)

    def jalankan(self, kebijakan, deterministik, rekam=False, catat_trade=False):
        p, cfg = self.p, self.cfg
        modal = float(cfg['modal'])
        kas = modal
        shares = np.zeros(self.N)
        harga_masuk = np.zeros(self.N)
        tp = np.zeros(self.N)
        sl = np.zeros(self.N)
        batas_hold = np.zeros(self.N, dtype=int)
        hari_dipegang = np.zeros(self.N, dtype=int)
        masuk_pada = np.zeros(self.N, dtype=int)
        pilihan_masuk = np.zeros((self.N, 4), dtype=int)   # porsi, tp, sl, hold

        fee_beli = cfg['fee_beli']
        fee_jual = cfg['fee_jual']
        slip = cfg['slippage']
        maks_pos = int(cfg['maks_posisi'])
        cap_saham = float(cfg['maks_porsi_saham'])
        cap_adv = float(cfg['maks_porsi_adv'])

        ekuitas_seri = []
        tanggal_seri = []
        trades = []
        jejak = {'X': [], 'kandidat': [], 'dipegang': [], 'masuk': [], 'porsi': [],
                 'tp': [], 'sl': [], 'hold': [], 'keluar': [], 'logp': [], 'nilai': [],
                 'reward': []}
        n_masuk_diambil = 0
        n_kandidat_dilihat = 0
        hari_terisi = 0
        bobot_jml = 0.0
        flat_berjalan = 0
        flat_maks = 0
        fitur_masuk = []
        fitur_lewat_n = 0
        fitur_lewat_jml = np.zeros(len(p['fitur']))

        puncak = modal
        ekuitas_l = modal
        dd_lama = 0.0

        for t in range(self.a, self.b - 1):
            ekuitas = kas + float(np.nansum(shares * p['close'][t]))
            puncak = max(puncak, ekuitas)
            dipegang = shares > 0
            kandidat = p['ok'][t] & ~dipegang

            S = self._state(t, kas, ekuitas, shares, harga_masuk, hari_dipegang, puncak)
            aksi = kebijakan(S, dipegang, kandidat, deterministik)

            # ---- profil "kondisi beli": fitur mentah saat masuk vs saat lewat
            mask_masuk = aksi['masuk'] & kandidat
            if kandidat.any():
                n_kandidat_dilihat += int(kandidat.sum())
                lewat = kandidat & ~mask_masuk
                if lewat.any():
                    fitur_lewat_jml += p['X'][t][lewat].sum(axis=0)
                    fitur_lewat_n += int(lewat.sum())

            # ---- 1) jual: perintah keluar dari agen, dieksekusi di open t+1
            jual = np.where(dipegang & aksi['keluar'])[0]
            for j in jual:
                harga = p['open'][t + 1, j] * (1 - slip)
                if not np.isfinite(harga) or harga <= 0:
                    continue
                kas += shares[j] * harga * (1 - fee_jual)
                if catat_trade:
                    trades.append(_trade(p, j, masuk_pada[j], t + 1, harga_masuk[j],
                                         harga, shares[j], 'agen jual',
                                         pilihan_masuk[j], hari_dipegang[j]))
                shares[j] = 0.0
                hari_dipegang[j] = 0

            # ---- 2) beli: dieksekusi di open t+1, dibatasi slot, kas, ADV, lot
            urut = np.argsort(-aksi['prob_masuk'] * mask_masuk)
            for j in urut:
                if not mask_masuk[j]:
                    continue
                if int((shares > 0).sum()) >= maks_pos:
                    break
                harga = p['open'][t + 1, j] * (1 + slip)
                if not np.isfinite(harga) or harga <= 0:
                    continue
                target = min(PORSI_GRID[aksi['porsi'][j]] * ekuitas, cap_saham * ekuitas)
                target = min(target, kas / (1 + fee_beli), cap_adv * p['adv'][t, j])
                lot = int(target // (harga * 100))
                if lot < 1:
                    continue
                lembar = lot * 100
                biaya = lembar * harga * (1 + fee_beli)
                if biaya > kas:
                    continue
                kas -= biaya
                shares[j] = lembar
                harga_masuk[j] = harga
                a_t = p['atr'][t, j]
                if not np.isfinite(a_t) or a_t <= 0:
                    a_t = harga * 0.02
                tp[j] = harga + TP_GRID[aksi['tp'][j]] * a_t
                sl[j] = harga - SL_GRID[aksi['sl'][j]] * a_t
                batas_hold[j] = HOLD_GRID[aksi['hold'][j]]
                hari_dipegang[j] = 0
                masuk_pada[j] = t + 1
                pilihan_masuk[j] = [aksi['porsi'][j], aksi['tp'][j],
                                    aksi['sl'][j], aksi['hold'][j]]
                n_masuk_diambil += 1
                fitur_masuk.append(p['X'][t, j].copy())

            # ---- 3) hari t+1 berjalan: TP/SL/batas hold
            for j in np.where(shares > 0)[0]:
                hari_dipegang[j] += 1
                l, h = p['low'][t + 1, j], p['high'][t + 1, j]
                keluar_di = None
                alasan = None
                # SL diperiksa lebih dulu: kalau satu hari menyentuh keduanya,
                # asumsi terburuk yang dipakai. Mengasumsikan TP duluan akan
                # membuat hasil backtest lebih bagus dari yang bisa terjadi.
                if np.isfinite(l) and l <= sl[j]:
                    keluar_di, alasan = min(sl[j], p['open'][t + 1, j]), 'stop loss'
                elif np.isfinite(h) and h >= tp[j]:
                    keluar_di, alasan = max(tp[j], p['open'][t + 1, j]), 'take profit'
                elif hari_dipegang[j] >= batas_hold[j]:
                    keluar_di, alasan = p['close'][t + 1, j], 'batas hold'
                if keluar_di is not None and np.isfinite(keluar_di) and keluar_di > 0:
                    harga = keluar_di * (1 - slip)
                    kas += shares[j] * harga * (1 - fee_jual)
                    if catat_trade:
                        trades.append(_trade(p, j, masuk_pada[j], t + 1, harga_masuk[j],
                                             harga, shares[j], alasan,
                                             pilihan_masuk[j], hari_dipegang[j]))
                    shares[j] = 0.0
                    hari_dipegang[j] = 0

            ekuitas_b = kas + float(np.nansum(shares * p['close'][t + 1]))

            # Eksposur dicatat karena "tidak berdagang" adalah hasil yang SAH
            # tapi harus terlihat. Tanpa angka ini, agen yang diam sepanjang
            # tahun dan agen yang aktif tapi kebetulan impas terbaca sama di
            # kolom return.
            terisi = int((shares > 0).sum()) > 0
            hari_terisi += 1 if terisi else 0
            bobot_jml += 1.0 - kas / max(ekuitas_b, 1e-9)
            flat_berjalan = 0 if terisi else flat_berjalan + 1
            flat_maks = max(flat_maks, flat_berjalan)

            imbalan = 100.0 * math.log(max(ekuitas_b, 1e-6) / max(ekuitas_l, 1e-6))
            if cfg['imbalan'] == 'relatif':
                imbalan -= 100.0 * math.log(max(1.0 + p['mkt'][t], 0.05))

            # Penalti risiko dikenakan pada PENDALAMAN drawdown hari itu,
            # bukan pada level drawdown yang sedang berjalan.
            #
            # Versi pertama menghukum levelnya tiap hari, dan itu diam-diam
            # mengganti tujuannya: drawdown 20% yang bertahan 200 hari
            # menumpuk penalti ~400, sementara seluruh suku keuntungan setahun
            # cuma berkisar +-20. Terukur di log latihan sebagai reward -150
            # s.d. -490 per episode padahal evaluasinya cuma -15%. Yang
            # dioptimalkan agen jadi "jangan pernah turun", bukan "cari untung"
            # -- padahal tujuannya dinyatakan keuntungan absolut. Dengan versi
            # pendalaman, total penaltinya sebanding dengan drawdown maksimum,
            # jadi ia tetap sekelas dengan suku keuntungan alih-alih menelannya.
            dd = ekuitas_b / max(puncak, 1e-9) - 1.0
            if dd < dd_lama:
                imbalan -= float(cfg['risk_aversion']) * 100.0 * (dd_lama - dd)
            dd_lama = dd
            ekuitas_l = ekuitas_b
            ekuitas_seri.append(ekuitas_b)
            tanggal_seri.append(p['indeks'][t + 1])

            if rekam:
                jejak['X'].append(S)
                jejak['kandidat'].append(kandidat.copy())
                jejak['dipegang'].append(dipegang.copy())
                for k in ('masuk', 'porsi', 'tp', 'sl', 'hold', 'keluar'):
                    jejak[k].append(aksi[k].copy())
                jejak['logp'].append(aksi['logp'])
                jejak['nilai'].append(aksi['nilai'])
                jejak['reward'].append(imbalan)

        # tutup semua posisi di harga penutupan terakhir (biaya tetap dikenakan)
        t_akhir = self.b - 1
        for j in np.where(shares > 0)[0]:
            harga = p['close'][t_akhir, j] * (1 - slip)
            kas += shares[j] * harga * (1 - fee_jual)
            if catat_trade:
                trades.append(_trade(p, j, masuk_pada[j], t_akhir, harga_masuk[j],
                                     harga, shares[j], 'akhir periode',
                                     pilihan_masuk[j], hari_dipegang[j]))
            shares[j] = 0.0

        profil = None
        if fitur_masuk and fitur_lewat_n:
            rata_masuk = np.mean(fitur_masuk, axis=0)
            rata_lewat = fitur_lewat_jml / fitur_lewat_n
            profil = (rata_masuk, rata_lewat, len(fitur_masuk), fitur_lewat_n)

        n_hari = max(1, len(ekuitas_seri))
        return {
            'ekuitas': np.array(ekuitas_seri), 'tanggal': tanggal_seri,
            'trades': trades, 'jejak': jejak, 'profil': profil,
            'n_masuk': n_masuk_diambil, 'n_kandidat': n_kandidat_dilihat,
            'kas_akhir': kas,
            'hari_terisi_pct': 100.0 * hari_terisi / n_hari,
            'eksposur_pct': 100.0 * bobot_jml / n_hari,
            'flat_terpanjang': flat_maks,
        }


def _trade(p, j, t_masuk, t_keluar, harga_masuk, harga_keluar, lembar, alasan,
           pilihan, lama):
    kotor = harga_keluar / max(harga_masuk, 1e-9) - 1
    return {
        'kode': p['kode'][j],
        'masuk': str(p['indeks'][t_masuk].date()),
        'keluar': str(p['indeks'][t_keluar].date()),
        'hari': int(lama),
        'harga_masuk': float(harga_masuk),
        'harga_keluar': float(harga_keluar),
        'nilai': float(lembar * harga_masuk),
        'return_pct': float(kotor * 100),
        'alasan': alasan,
        'porsi': PORSI_GRID[int(pilihan[0])],
        'tp': TP_GRID[int(pilihan[1])],
        'sl': SL_GRID[int(pilihan[2])],
        'hold': HOLD_GRID[int(pilihan[3])],
    }


# ==========================================================================
# Kebijakan
# ==========================================================================
def _torch():
    import torch
    torch.set_num_threads(max(1, min(4, (os.cpu_count() or 4) // 2)))
    return torch


class Jaringan:
    """Satu batang bersama + enam kepala keputusan. Kecil dengan sengaja:
    dengan ~4.000 hari data, jaringan besar hanya menghafal lebih cepat."""

    def __init__(self, dim, lebar=64, seed=0, n_kandidat=30, p_keluar_awal=0.005):
        torch = _torch()
        import torch.nn as nn
        torch.manual_seed(seed)
        self.torch = torch
        self.batang = nn.Sequential(nn.Linear(dim, lebar), nn.Tanh(),
                                    nn.Linear(lebar, lebar), nn.Tanh())
        self.kepala = nn.ModuleDict({
            'masuk': nn.Linear(lebar, 2),
            'porsi': nn.Linear(lebar, len(PORSI_GRID)),
            'tp': nn.Linear(lebar, len(TP_GRID)),
            'sl': nn.Linear(lebar, len(SL_GRID)),
            'hold': nn.Linear(lebar, len(HOLD_GRID)),
            'keluar': nn.Linear(lebar, 2),
        })
        self.nilai = nn.Sequential(nn.Linear(lebar, lebar), nn.Tanh(), nn.Linear(lebar, 1))
        self.modul = nn.ModuleList([self.batang, self.kepala, self.nilai])

        # ------------------------------------------------------------------
        # Inisialisasi condong-ke-diam, DISKALAKAN KE BESAR UNIVERSE.
        # INI BUKAN DETAIL KECIL -- dua kali ia yang menentukan hasil.
        #
        # (1) Dengan inisialisasi biasa, kepala 'masuk' dan 'keluar'
        #     berpeluang 50/50 di hari pertama. Setiap hari separuh kandidat
        #     mencoba masuk dan separuh posisi langsung dijual: ~4 putaran
        #     beli-jual per hari, masing-masing ~0,55% biaya + slippage.
        #     Diukur: ~1.200 transaksi setahun, ekuitas -55% per fold.
        #
        # (2) Memasang peluang masuk TETAP (mis. 3%) juga salah begitu
        #     universe boleh sebesar apa pun: 3% dari 10 emiten berarti 0,3
        #     percobaan masuk per hari, 3% dari 120 emiten berarti 3,6 --
        #     perilaku awal yang sepenuhnya berbeda hanya karena daftar
        #     emitennya lebih panjang. Jadi biasnya diskalakan supaya
        #     JUMLAH percobaan masuk per hari kira-kira tetap (~1), berapa
        #     pun besar universe-nya.
        #
        # Peluang keluar dipasang sangat rendah (0,5%/hari) karena keluar
        # sudah ditangani TP/SL/batas hold; kepala ini cuma untuk membatalkan
        # posisi lebih awal, bukan mesin utama pergantian posisi. Pada versi
        # sebelumnya (5%/hari) ia sendirian memangkas umur posisi jadi ~8
        # hari dan membuat ongkos ~19% setahun.
        # ------------------------------------------------------------------
        p_masuk_awal = min(0.05, 1.0 / max(1, n_kandidat))
        with torch.no_grad():
            for nama in self.kepala:
                self.kepala[nama].weight.mul_(0.01)
                self.kepala[nama].bias.zero_()
            self.kepala['masuk'].bias[1] = math.log(p_masuk_awal / (1 - p_masuk_awal))
            self.kepala['keluar'].bias[1] = math.log(p_keluar_awal / (1 - p_keluar_awal))

    def parameters(self):
        return self.modul.parameters()

    def forward(self, X):
        """X: [.., N, D] -> logits tiap kepala + nilai state (pooled per hari)."""
        h = self.batang(X)
        logits = {k: self.kepala[k](h) for k in self.kepala}
        nilai = self.nilai(h.mean(dim=-2)).squeeze(-1)
        return logits, nilai


def buat_kebijakan(net, torch):
    """Bungkus jaringan jadi fungsi yang dipanggil simulator tiap hari."""
    def kebijakan(S, dipegang, kandidat, deterministik):
        with torch.no_grad():
            X = torch.from_numpy(S)
            logits, nilai = net.forward(X)
            logp_total = 0.0
            hasil = {}
            p_masuk = torch.softmax(logits['masuk'], dim=-1)[:, 1].numpy()

            def ambil(nama, mask):
                lg = logits[nama]
                dist = torch.distributions.Categorical(logits=lg)
                pilih = lg.argmax(dim=-1) if deterministik else dist.sample()
                lp = (dist.log_prob(pilih) * torch.from_numpy(mask.astype(np.float32))).sum()
                return pilih.numpy(), float(lp)

            m_kandidat = kandidat.astype(bool)
            m_pegang = dipegang.astype(bool)
            pilih_masuk, lp1 = ambil('masuk', m_kandidat)
            pilih_keluar, lp2 = ambil('keluar', m_pegang)
            masuk = (pilih_masuk == 1) & m_kandidat
            porsi, lp3 = ambil('porsi', masuk)
            tp, lp4 = ambil('tp', masuk)
            sl, lp5 = ambil('sl', masuk)
            hold, lp6 = ambil('hold', masuk)
            logp_total = lp1 + lp2 + lp3 + lp4 + lp5 + lp6

            hasil.update(masuk=masuk, keluar=(pilih_keluar == 1) & m_pegang,
                         porsi=porsi, tp=tp, sl=sl, hold=hold,
                         prob_masuk=p_masuk, logp=logp_total, nilai=float(nilai))
            return hasil
    return kebijakan


def kebijakan_acak(rng):
    """Ruang aksi identik, keputusan acak. Pembanding paling penting: kalau
    agen tidak mengalahkan ini, yang terukur cuma efek pasar."""
    def kebijakan(S, dipegang, kandidat, deterministik, laju=0.02):
        n = len(dipegang)
        masuk = (rng.random(n) < laju) & kandidat.astype(bool)
        return {
            'masuk': masuk,
            'keluar': (rng.random(n) < 0.03) & dipegang.astype(bool),
            'porsi': rng.integers(0, len(PORSI_GRID), n),
            'tp': rng.integers(0, len(TP_GRID), n),
            'sl': rng.integers(0, len(SL_GRID), n),
            'hold': rng.integers(0, len(HOLD_GRID), n),
            'prob_masuk': rng.random(n),
            'logp': 0.0, 'nilai': 0.0,
        }
    return kebijakan


# ==========================================================================
# Latihan PPO
# ==========================================================================
def latih(panel, cfg, a_latih, b_latih, mu, sd, seed, kanal, lapor):
    torch = _torch()
    N_total = len(panel['kode'])
    K = min(int(cfg['emiten_per_episode']) or N_total, N_total)
    net = Jaringan(len(panel['fitur']) + DIM_KONTEKS, seed=seed, n_kandidat=K)
    opt = torch.optim.Adam(net.parameters(), lr=cfg['lr'])
    kebijakan = buat_kebijakan(net, torch)
    rng = np.random.default_rng(seed)

    panjang = int(cfg['panjang_episode'])
    n_iter = int(cfg['iterasi'])
    n_ep = int(cfg['episode_per_iterasi'])
    gamma, lam = 0.99, 0.95
    riwayat_reward = []

    for it in range(n_iter):
        if kanal.berhenti():
            break
        batch = []
        for _ in range(n_ep):
            span = b_latih - a_latih
            if span > panjang + 5:
                a = a_latih + int(rng.integers(0, span - panjang - 1))
                b = a + panjang
            else:
                a, b = a_latih, b_latih
            kolom = None if K >= N_total else np.sort(rng.choice(N_total, K, replace=False))
            sim = Portofolio(_iris(panel, a, b, kolom), cfg, 0, b - a, mu, sd)
            keluar = sim.jalankan(kebijakan, deterministik=False, rekam=True)
            batch.append(keluar)

        # --- GAE per episode
        semua_X, semua_A, semua_M, semua_adv, semua_ret, semua_logp = [], [], [], [], [], []
        total_reward = []
        for keluar in batch:
            j = keluar['jejak']
            r = np.array(j['reward'], dtype=np.float32)
            v = np.array(j['nilai'], dtype=np.float32)
            total_reward.append(float(r.sum()))
            adv = np.zeros_like(r)
            akhir = 0.0
            for i in range(len(r) - 1, -1, -1):
                v_next = v[i + 1] if i + 1 < len(r) else 0.0
                delta = r[i] + gamma * v_next - v[i]
                akhir = delta + gamma * lam * akhir
                adv[i] = akhir
            ret = adv + v
            semua_X.append(np.stack(j['X']))
            semua_A.append({k: np.stack(j[k]) for k in ('masuk', 'porsi', 'tp', 'sl', 'hold', 'keluar')})
            semua_M.append({'kandidat': np.stack(j['kandidat']),
                            'dipegang': np.stack(j['dipegang'])})
            semua_adv.append(adv)
            semua_ret.append(ret)
            semua_logp.append(np.array(j['logp'], dtype=np.float32))

        X = torch.from_numpy(np.concatenate(semua_X))
        adv = torch.from_numpy(np.concatenate(semua_adv))
        ret = torch.from_numpy(np.concatenate(semua_ret))
        logp_lama = torch.from_numpy(np.concatenate(semua_logp))
        A = {k: torch.from_numpy(np.concatenate([a[k] for a in semua_A]).astype(np.int64))
             for k in ('porsi', 'tp', 'sl', 'hold')}
        A['masuk'] = torch.from_numpy(
            np.concatenate([a['masuk'] for a in semua_A]).astype(np.int64))
        A['keluar'] = torch.from_numpy(
            np.concatenate([a['keluar'] for a in semua_A]).astype(np.int64))
        M = {k: torch.from_numpy(np.concatenate([m[k] for m in semua_M]).astype(np.float32))
             for k in ('kandidat', 'dipegang')}
        adv = (adv - adv.mean()) / (adv.std() + 1e-6)

        n = X.shape[0]
        idx = np.arange(n)
        for _ in range(int(cfg['epoch_ppo'])):
            rng.shuffle(idx)
            for s in range(0, n, 64):
                mb = torch.from_numpy(idx[s:s + 64])
                logits, nilai = net.forward(X[mb])
                m_masuk = M['kandidat'][mb]
                m_pegang = M['dipegang'][mb]
                m_beli = A['masuk'][mb].float() * m_masuk

                lp = 0.0
                ent = 0.0
                for nama, mask, pilih in (
                        ('masuk', m_masuk, A['masuk'][mb]),
                        ('keluar', m_pegang, A['keluar'][mb]),
                        ('porsi', m_beli, A['porsi'][mb]),
                        ('tp', m_beli, A['tp'][mb]),
                        ('sl', m_beli, A['sl'][mb]),
                        ('hold', m_beli, A['hold'][mb])):
                    dist = torch.distributions.Categorical(logits=logits[nama])
                    lp = lp + (dist.log_prob(pilih) * mask).sum(dim=-1)
                    ent = ent + (dist.entropy() * mask).sum(dim=-1).mean()

                rasio = torch.exp(torch.clamp(lp - logp_lama[mb], -10, 10))
                a_mb = adv[mb]
                l1 = rasio * a_mb
                l2 = torch.clamp(rasio, 0.8, 1.2) * a_mb
                rugi_pi = -torch.min(l1, l2).mean()
                rugi_v = ((nilai - ret[mb]) ** 2).mean()
                rugi = rugi_pi + 0.5 * rugi_v - float(cfg['entropi']) * ent / max(1, X.shape[1])

                opt.zero_grad()
                rugi.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                opt.step()

        rata = float(np.mean(total_reward))
        riwayat_reward.append(rata)
        lapor(it + 1, n_iter, rata)

    return net, riwayat_reward


# ==========================================================================
# Metrik & pembanding
# ==========================================================================
def metrik(ekuitas, modal, n_hari_setahun=245):
    if len(ekuitas) < 2:
        return {'return_pct': 0.0, 'cagr': 0.0, 'sharpe': 0.0, 'maks_dd': 0.0}
    e = np.asarray(ekuitas, dtype=float)
    total = e[-1] / modal - 1
    tahun = len(e) / n_hari_setahun
    cagr = (e[-1] / modal) ** (1 / max(tahun, 1e-6)) - 1 if e[-1] > 0 else -1.0
    r = np.diff(e) / e[:-1]
    sharpe = (r.mean() / r.std() * math.sqrt(n_hari_setahun)) if r.std() > 1e-12 else 0.0
    puncak = np.maximum.accumulate(e)
    dd = float((e / puncak - 1).min())
    return {'return_pct': float(total * 100), 'cagr': float(cagr * 100),
            'sharpe': float(sharpe), 'maks_dd': float(dd * 100)}


def beli_tahan(panel, cfg, a, b):
    """Beli bobot sama di pembukaan hari pertama, jual di penutupan terakhir.
    Biaya tetap dikenakan supaya pembandingnya adil."""
    p = panel
    modal = float(cfg['modal'])
    # Hari pertama fold bisa baris libur (Yahoo menulis baris bervolume nol,
    # mis. 2 Jan 2017): tanpa ini tak ada yang layak dibeli dan beli-tahan
    # tercatat persis 0%.
    while a < b - 2 and not p['ok'][a].any():
        a += 1
    layak = np.where(p['ok'][a])[0]
    if len(layak) == 0:
        return np.array([modal])
    per = modal / len(layak)
    shares = np.zeros(len(p['kode']))
    kas = modal
    for j in layak:
        harga = p['open'][a + 1, j] * (1 + cfg['slippage'])
        if not np.isfinite(harga) or harga <= 0:
            continue
        lot = int(min(per, kas) // (harga * 100))
        if lot < 1:
            continue
        shares[j] = lot * 100
        kas -= lot * 100 * harga * (1 + cfg['fee_beli'])
    seri = []
    for t in range(a + 1, b):
        seri.append(kas + float(np.nansum(shares * p['close'][t])))
    if seri:
        seri[-1] = kas + float(np.nansum(shares * p['close'][b - 1]
                                         * (1 - cfg['slippage']) * (1 - cfg['fee_jual'])))
    return np.array(seri) if seri else np.array([modal])


# ==========================================================================
# Runner walk-forward
# ==========================================================================
def jalankan_rl(config, kanal):
    cfg = _normalkan(config)
    kanal.tahap('Menyiapkan data')
    kanal.maju(0.02)
    panel = bangun_panel(cfg, kanal)

    indeks = panel['indeks']
    tahun = np.array([d.year for d in indeks])
    tahun_awal = int(indeks[0].year)
    tahun_akhir = int(indeks[-1].year)
    latih_th = int(cfg['latih_tahun'])
    uji_th = int(cfg['uji_tahun'])

    folds = []
    y = tahun_awal + latih_th
    while y + uji_th - 1 <= tahun_akhir:
        a_l = int(np.searchsorted(tahun, y - latih_th))
        b_l = int(np.searchsorted(tahun, y))
        b_u = int(np.searchsorted(tahun, y + uji_th))
        if b_l - a_l > 300 and b_u - b_l > 60:
            folds.append({'tahun': y, 'a_latih': a_l, 'b_latih': b_l,
                          'a_uji': b_l, 'b_uji': b_u})
        y += uji_th
    if not folds:
        raise RuntimeError('Rentang data tidak cukup untuk satu fold walk-forward. '
                           'Turunkan "latih_tahun" atau mundurkan "mulai_tahun".')

    kanal.log('%d fold walk-forward: uji %s.'
              % (len(folds), ', '.join(str(f['tahun']) for f in folds)))
    n_seed = int(cfg['n_seed'])
    total_kerja = len(folds) * n_seed
    kanal.log('Perkiraan kerja: %d fold x %d seed x %d iterasi PPO.'
              % (len(folds), n_seed, cfg['iterasi']))

    hasil_fold = []
    ekuitas_rantai = [1.0]
    tanggal_rantai = []
    semua_trade = []
    F = len(panel['fitur'])
    profil_masuk_jml = np.zeros(F)
    profil_lewat_jml = np.zeros(F)
    profil_masuk_n = profil_lewat_n = 0
    kerja = 0

    for f in folds:
        if kanal.berhenti():
            kanal.log('Dihentikan atas permintaan.', 'warn')
            break
        kanal.tahap('Fold uji %d' % f['tahun'])
        Xl = panel['X'][f['a_latih']:f['b_latih']].reshape(-1, F)
        mu = Xl.mean(axis=0).astype(np.float32)
        sd = (Xl.std(axis=0) + 1e-6).astype(np.float32)
        kanal.log('Latih %s s.d. %s (%d hari), uji %s s.d. %s (%d hari).' % (
            indeks[f['a_latih']].date(), indeks[f['b_latih'] - 1].date(),
            f['b_latih'] - f['a_latih'],
            indeks[f['a_uji']].date(), indeks[f['b_uji'] - 1].date(),
            f['b_uji'] - f['a_uji']))

        per_seed = []
        for s in range(n_seed):
            if kanal.berhenti():
                break
            seed = int(cfg['seed']) + s * 101
            t0 = time.time()

            def lapor(it, n, r, _s=seed):
                kanal.log('  seed %d  iterasi %2d/%d  reward rata-rata %+7.2f'
                          % (_s, it, n, r))

            net, riwayat = latih(panel, cfg, f['a_latih'], f['b_latih'],
                                 mu, sd, seed, kanal, lapor)
            torch = _torch()
            kebijakan = buat_kebijakan(net, torch)

            # Evaluasi memakai kebijakan STOKASTIK, bukan argmax.
            #
            # Argmax terdengar lebih "bersih", tapi pada kepala biner dengan
            # laju dasar rendah ia selalu memilih "tidak masuk" kecuali
            # peluangnya melewati 50% -- ambang yang praktis tidak pernah
            # tercapai untuk aksi yang memang jarang. Diukur: evaluasi argmax
            # menghasilkan NOL transaksi di ketujuh fold, padahal kebijakannya
            # jelas bukan "jangan pernah beli". Lagi pula yang dioptimalkan PPO
            # memang imbal hasil harapan DARI kebijakan stokastik, jadi inilah
            # objek yang benar untuk diukur. Beberapa rollout dirata-ratakan
            # supaya derau samplingnya terlihat, bukan disembunyikan.
            #
            # Evaluasi memakai UNIVERSE PENUH (bukan sampel seperti saat
            # latihan): kalau universe-nya 400 emiten, itulah yang akan
            # dihadapi kebijakannya kalau dipakai sungguhan.
            panel_uji = _iris(panel, f['a_uji'], f['b_uji'])
            rollout = []
            for k in range(int(cfg['n_eval'])):
                torch.manual_seed(seed * 1000 + k)
                sim = Portofolio(panel_uji, cfg, 0, len(panel_uji['indeks']), mu, sd)
                rollout.append(sim.jalankan(kebijakan, deterministik=False,
                                            catat_trade=True))
            ret_r = [metrik(r['ekuitas'], cfg['modal'])['return_pct'] for r in rollout]
            uji = rollout[0]
            m = metrik(uji['ekuitas'], cfg['modal'])
            m['return_pct'] = float(np.mean(ret_r))
            m['sharpe'] = float(np.mean([metrik(r['ekuitas'], cfg['modal'])['sharpe']
                                         for r in rollout]))
            m['maks_dd'] = float(np.mean([metrik(r['ekuitas'], cfg['modal'])['maks_dd']
                                          for r in rollout]))
            m['n_trade'] = float(np.mean([len(r['trades']) for r in rollout]))
            m['eksposur'] = float(np.mean([r['eksposur_pct'] for r in rollout]))
            m['hari_terisi'] = float(np.mean([r['hari_terisi_pct'] for r in rollout]))
            m['flat_terpanjang'] = float(np.mean([r['flat_terpanjang'] for r in rollout]))
            m['ret_rollout'] = ret_r
            m['seed'] = seed
            m['detik'] = round(time.time() - t0, 1)
            m['reward_latih'] = riwayat[-1] if riwayat else None
            per_seed.append({'metrik': m, 'uji': uji, 'rollout': rollout})
            kanal.log('  seed %d selesai (%.0f dtk): return %+.2f%% (rollout %+.1f..%+.1f), '
                      '%.0f transaksi, DD maks %.1f%%'
                      % (seed, m['detik'], m['return_pct'], min(ret_r), max(ret_r),
                         m['n_trade'], m['maks_dd']))
            kerja += 1
            kanal.maju(0.15 + 0.83 * kerja / total_kerja)

        if not per_seed:
            break

        bh = beli_tahan(panel, cfg, f['a_uji'], f['b_uji'])
        m_bh = metrik(bh, cfg['modal'])

        rng = np.random.default_rng(int(cfg['seed']) + 7)
        acak_ret = []
        for _ in range(5):
            sim = Portofolio(panel, cfg, f['a_uji'], f['b_uji'], mu, sd)
            ka = sim.jalankan(kebijakan_acak(rng), deterministik=True)
            acak_ret.append(metrik(ka['ekuitas'], cfg['modal'])['return_pct'])
        m_acak = float(np.mean(acak_ret))

        ret_seed = [p['metrik']['return_pct'] for p in per_seed]
        rata_ret = float(np.mean(ret_seed))
        # Sebaran yang dilaporkan adalah sebaran SELURUH rollout, bukan cuma
        # antar-seed: dengan kebijakan stokastik, dua jalan uji dari jaringan
        # yang SAMA bisa berbeda 20 poin persen. Melaporkan sebaran antar-seed
        # saja (yang jadi nol persis kalau seed cuma satu) menyembunyikan
        # sumber ketidakpastian yang justru paling besar di sini.
        ret_semua = [x for p in per_seed for x in p['metrik']['ret_rollout']]

        # Kurva ekuitas gabungan memakai seed PERTAMA, bukan yang terbaik --
        # memilih seed terbaik per fold setelah melihat hasil ujinya adalah
        # bentuk halus dari melihat masa depan.
        pakai = per_seed[0]['uji']
        e = pakai['ekuitas'] / cfg['modal']
        dasar = ekuitas_rantai[-1]
        ekuitas_rantai.extend((e * dasar).tolist())
        tanggal_rantai.extend([str(d.date()) for d in pakai['tanggal']])

        # Statistik sebaran (TP/SL/porsi/hold, profil kondisi beli, per emiten)
        # dikumpulkan dari SEMUA rollout dan SEMUA seed, bukan cuma kurva yang
        # ditampilkan -- sampelnya jadi jauh lebih besar dan tidak bergantung
        # pada satu jalur acak yang kebetulan.
        for p_s in per_seed:
            for r in p_s['rollout']:
                semua_trade.extend(r['trades'])
                if r['profil']:
                    rm, rl, nm, nl = r['profil']
                    profil_masuk_jml += rm * nm
                    profil_lewat_jml += rl * nl
                    profil_masuk_n += nm
                    profil_lewat_n += nl

        hasil_fold.append({
            'tahun': f['tahun'],
            'latih': '%s..%s' % (indeks[f['a_latih']].date(), indeks[f['b_latih'] - 1].date()),
            'uji': '%s..%s' % (indeks[f['a_uji']].date(), indeks[f['b_uji'] - 1].date()),
            'hari_uji': f['b_uji'] - f['a_uji'],
            'agen_rata': rata_ret,
            'agen_min': float(np.min(ret_semua)),
            'agen_maks': float(np.max(ret_semua)),
            'agen_n_run': len(ret_semua),
            'agen_seed1': float(ret_seed[0]),
            'agen_per_seed': [float(x) for x in ret_seed],
            'beli_tahan': m_bh['return_pct'],
            'acak': m_acak,
            'alfa': rata_ret - m_bh['return_pct'],
            'sharpe': float(np.mean([p['metrik']['sharpe'] for p in per_seed])),
            'maks_dd': float(np.mean([p['metrik']['maks_dd'] for p in per_seed])),
            'n_trade': int(np.mean([p['metrik']['n_trade'] for p in per_seed])),
            'eksposur': float(np.mean([p['metrik']['eksposur'] for p in per_seed])),
            'hari_terisi': float(np.mean([p['metrik']['hari_terisi'] for p in per_seed])),
            'flat_terpanjang': float(np.mean([p['metrik']['flat_terpanjang']
                                              for p in per_seed])),
            'detik': float(np.sum([p['metrik']['detik'] for p in per_seed])),
        })
        kanal.log('Fold %d: agen %+.2f%% (sebaran %d run: %+.2f..%+.2f) | beli-tahan '
                  '%+.2f%% | acak %+.2f%% | alfa %+.2f pp | eksposur %.0f%% '
                  '(terisi %.0f%% hari, flat terpanjang %.0f hari)'
                  % (f['tahun'], rata_ret, len(ret_semua), np.min(ret_semua),
                     np.max(ret_semua), m_bh['return_pct'], m_acak,
                     rata_ret - m_bh['return_pct'], hasil_fold[-1]['eksposur'],
                     hasil_fold[-1]['hari_terisi'], hasil_fold[-1]['flat_terpanjang']), 'ok')

    if not hasil_fold:
        raise RuntimeError('Tidak ada fold yang selesai.')

    kanal.tahap('Merangkum')
    return _rangkum(cfg, panel, hasil_fold, ekuitas_rantai, tanggal_rantai,
                    semua_trade, profil_masuk_jml, profil_masuk_n,
                    profil_lewat_jml, profil_lewat_n, kanal)


def _rangkum(cfg, panel, folds, ekuitas, tanggal, trades, pm_jml, pm_n,
             pl_jml, pl_n, kanal):
    alfa = np.array([f['alfa'] for f in folds])
    menang = int((alfa > 0).sum())
    n = len(folds)
    rata_alfa = float(alfa.mean())
    se = float(alfa.std(ddof=1) / math.sqrt(n)) if n > 1 else 0.0
    t_stat = rata_alfa / se if se > 1e-9 else 0.0

    agen_total = (ekuitas[-1] - 1) * 100 if len(ekuitas) > 1 else 0.0
    bh_kumulatif = 1.0
    for f in folds:
        bh_kumulatif *= (1 + f['beli_tahan'] / 100)
    acak_kumulatif = 1.0
    for f in folds:
        acak_kumulatif *= (1 + f['acak'] / 100)

    # kombinasi yang dipilih agen -- ini jawaban langsung atas pertanyaan
    # "kombinasi TP/SL/porsi/hold mana yang menang"
    def sebaran(kunci, grid, sufiks=''):
        jml = {}
        for t in trades:
            jml[t[kunci]] = jml.get(t[kunci], 0) + 1
        total = max(1, sum(jml.values()))
        return [{'nilai': '%s%s' % (g, sufiks), 'n': jml.get(g, 0),
                 'pct': round(100.0 * jml.get(g, 0) / total, 1)} for g in grid]

    per_kode = {}
    for t in trades:
        d = per_kode.setdefault(t['kode'], {'kode': t['kode'], 'n': 0, 'jml': 0.0, 'menang': 0})
        d['n'] += 1
        d['jml'] += t['return_pct']
        d['menang'] += 1 if t['return_pct'] > 0 else 0
    daftar_kode = sorted(per_kode.values(), key=lambda d: -d['jml'])
    for d in daftar_kode:
        d['rata'] = round(d['jml'] / max(1, d['n']), 2)
        d['win'] = round(100.0 * d['menang'] / max(1, d['n']), 1)

    alasan = {}
    for t in trades:
        a = alasan.setdefault(t['alasan'], {'alasan': t['alasan'], 'n': 0, 'jml': 0.0})
        a['n'] += 1
        a['jml'] += t['return_pct']
    daftar_alasan = sorted(alasan.values(), key=lambda a: -a['n'])
    for a in daftar_alasan:
        a['rata'] = round(a['jml'] / max(1, a['n']), 2)

    profil = []
    if pm_n and pl_n:
        rm = pm_jml / pm_n
        rl = pl_jml / pl_n
        nama = panel['fitur']
        sd = panel['X'].reshape(-1, len(nama)).std(axis=0) + 1e-9
        z = (rm - rl) / sd
        urut = np.argsort(-np.abs(z))
        for i in urut[:10]:
            profil.append({
                'fitur': FITUR_LABEL.get(nama[i], nama[i]),
                'saat_masuk': round(float(rm[i]), 4),
                'saat_lewat': round(float(rl[i]), 4),
                'z': round(float(z[i]), 3),
            })

    ret_trade = np.array([t['return_pct'] for t in trades]) if trades else np.array([0.0])
    ringkas = {
        'n_fold': n,
        'fold_menang': menang,
        'alfa_rata': round(rata_alfa, 2),
        'alfa_t': round(t_stat, 2),
        'agen_kumulatif': round(agen_total, 1),
        'bh_kumulatif': round((bh_kumulatif - 1) * 100, 1),
        'acak_kumulatif': round((acak_kumulatif - 1) * 100, 1),
        # n_trade = perkiraan jumlah transaksi SATU jalur melewati seluruh
        # periode uji. len(trades) jauh lebih besar karena mengumpulkan semua
        # rollout & seed -- itu ukuran sampel statistik, bukan jumlah transaksi.
        'n_trade': int(sum(f['n_trade'] for f in folds)),
        'n_trade_sampel': len(trades),
        'win_rate': round(100.0 * float((ret_trade > 0).mean()), 1) if trades else 0.0,
        'rata_trade': round(float(ret_trade.mean()), 2) if trades else 0.0,
        'rata_hari': round(float(np.mean([t['hari'] for t in trades])), 1) if trades else 0.0,
        'maks_dd': round(float(np.mean([f['maks_dd'] for f in folds])), 1),
        'sharpe': round(float(np.mean([f['sharpe'] for f in folds])), 2),
        'eksposur': round(float(np.mean([f['eksposur'] for f in folds])), 1),
        'hari_terisi': round(float(np.mean([f['hari_terisi'] for f in folds])), 1),
        'flat_terpanjang': int(np.max([f['flat_terpanjang'] for f in folds])),
    }
    eksposur = ringkas['eksposur']

    if eksposur < 5.0:
        # Hasil ini SAH, bukan bug: dengan reward absolut, memegang kas
        # bernilai nol dan agen boleh menyimpulkan tidak ada peluang yang
        # menutupi biayanya. Tapi ia harus dibedakan dari dua hal lain yang
        # tampak sama di kolom return -- optimizer yang kolaps, dan latihan
        # yang terlalu pendek. Reward latihan di log adalah pembedanya.
        vonis = 'diam'
        vonis_teks = (
            'Agen memilih HAMPIR TIDAK BERDAGANG: rata-rata hanya %.1f%% modal '
            'terpakai, portofolio kosong di sebagian besar hari (terpanjang %d hari '
            'bursa berturut-turut tanpa posisi). Dengan reward absolut ini kesimpulan '
            'yang sah -- artinya agen tidak menemukan aturan yang keuntungannya '
            'menutupi biaya transaksi. Sebelum menerimanya, periksa dulu kolom '
            'reward rata-rata di log: kalau ia tidak pernah naik, yang terjadi bukan '
            '"tidak ada peluang" melainkan latihannya terlalu pendek. Return kumulatif '
            'yang tercatat: %+.1f%% versus beli-tahan %+.1f%%.'
            % (eksposur, ringkas['flat_terpanjang'], agen_total,
               (bh_kumulatif - 1) * 100))
    elif menang * 2 < n or rata_alfa <= 0:
        vonis = 'gagal'
        # Perbandingan ke kebijakan acak disebut di sini, bukan cuma di tabel:
        # "kalah dari beli-tahan tapi jauh di atas acak" dan "kalah dari
        # keduanya" adalah dua keadaan yang sangat berbeda -- yang pertama
        # berarti ada yang dipelajari tapi belum cukup, yang kedua berarti
        # tidak ada apa-apa yang dipelajari.
        vs_acak = agen_total - (acak_kumulatif - 1) * 100
        vonis_teks = (
            'Agen TIDAK mengalahkan beli-tahan di luar sampel: alfa rata-rata '
            '%+.2f pp, menang di %d dari %d fold. Ini hasil yang paling sering '
            'muncul pada RL trading dan tidak boleh diperhalus. %s'
            % (rata_alfa, menang, n,
               ('Tapi ia mengungguli kebijakan acak %+.1f pp secara kumulatif, '
                'jadi ada sesuatu yang dipelajari -- cuma belum cukup untuk '
                'menutupi biaya dan mengalahkan sekadar memegang saham.' % vs_acak)
               if vs_acak > 5 else
               ('Ia juga tidak mengungguli kebijakan acak (%+.1f pp), jadi tidak ada '
                'bukti apa pun bahwa ada yang dipelajari -- yang terukur hanya efek '
                'pasar, biaya, dan ukuran posisi.' % vs_acak)))
    elif abs(t_stat) < 2.0 or menang < 0.7 * n:
        vonis = 'lemah'
        vonis_teks = (
            'Alfa rata-rata %+.2f pp (menang %d/%d fold, t=%.2f). Arahnya positif '
            'tapi TIDAK signifikan -- dengan %d fold, hasil sebesar ini masih '
            'sangat mungkin kebetulan. Belum layak dipakai sebagai dasar beli.'
            % (rata_alfa, menang, n, t_stat, n))
    elif eksposur < 40.0:
        vonis = 'menjanjikan'
        vonis_teks = (
            'Alfa rata-rata %+.2f pp, menang %d/%d fold, t=%.2f, dan itu dicapai '
            'dengan rata-rata hanya %.0f%% modal terpakai -- jadi per rupiah yang '
            'benar-benar berisiko, selisihnya lebih besar lagi. Tetap belum cukup '
            'untuk dipakai: ulangi di universe lain dan rentang tahun lain dulu.'
            % (rata_alfa, menang, n, t_stat, eksposur))
    else:
        vonis = 'menjanjikan'
        vonis_teks = (
            'Alfa rata-rata %+.2f pp, menang %d/%d fold, t=%.2f. Ini cukup kuat '
            'untuk dilanjutkan, TAPI belum cukup untuk dipakai: ulangi di '
            'universe lain dan rentang tahun lain dulu. Semua angka di sini masih '
            'dari satu semesta emiten dan satu bursa.'
            % (rata_alfa, menang, n, t_stat))

    kanal.log(vonis_teks, 'ok' if vonis == 'menjanjikan' else 'warn')

    langkah = max(1, len(ekuitas) // 800)     # kurva dijarangkan supaya JSON-nya ringan
    return {
        'judul_config': '%s · %d fold · %d emiten · seed %s' % (
            cfg['universe'], n, len(panel['kode']), cfg['seed']),
        'ringkas': ringkas,
        'vonis': vonis,
        'vonis_teks': vonis_teks,
        'folds': folds,
        'kurva': {
            'tanggal': tanggal[::langkah],
            'agen': [round(v, 4) for v in ekuitas[1:][::langkah]],
        },
        'sebaran': {
            'porsi': sebaran('porsi', PORSI_GRID),
            'tp': sebaran('tp', TP_GRID, 'x ATR'),
            'sl': sebaran('sl', SL_GRID, 'x ATR'),
            'hold': sebaran('hold', HOLD_GRID, ' hari'),
        },
        'per_kode': daftar_kode[:25],
        'alasan_keluar': daftar_alasan,
        'profil_masuk': profil,
        'trade_contoh': sorted(trades, key=lambda t: t['masuk'])[-40:],
        'universe': panel['kode'],
        'config': cfg,
    }


# ==========================================================================
# Konfigurasi
# ==========================================================================
def _normalkan(config):
    def f(k, d):
        try:
            return float(config.get(k, d))
        except (TypeError, ValueError):
            return d

    def i(k, d):
        try:
            return int(float(config.get(k, d)))
        except (TypeError, ValueError):
            return d

    return {
        'universe': config.get('universe', 'likuid30'),
        'kustom': config.get('kustom', ''),
        'portofolio_kode': config.get('portofolio_kode') or [],
        'mulai_tahun': i('mulai_tahun', 2012),
        'latih_tahun': max(2, i('latih_tahun', 5)),
        'uji_tahun': max(1, i('uji_tahun', 1)),
        'modal': f('modal', 100_000_000),
        'maks_posisi': max(1, i('maks_posisi', 8)),
        'maks_porsi_saham': f('maks_porsi_saham', 0.25),
        'maks_porsi_adv': f('maks_porsi_adv', 0.05),
        'fee_beli': f('fee_beli', 0.0015),
        'fee_jual': f('fee_jual', 0.0025),
        'slippage': f('slippage', 0.0015),
        'risk_aversion': f('risk_aversion', 0.5),
        'iterasi': max(1, i('iterasi', 12)),
        'episode_per_iterasi': max(1, i('episode_per_iterasi', 6)),
        'panjang_episode': max(60, i('panjang_episode', 250)),
        'epoch_ppo': max(1, i('epoch_ppo', 3)),
        'lr': f('lr', 0.0003),
        'entropi': f('entropi', 0.01),
        'n_seed': max(1, min(5, i('n_seed', 2))),
        'n_eval': max(1, min(10, i('n_eval', 4))),
        'maks_emiten': max(0, i('maks_emiten', 150)),
        'emiten_per_episode': max(5, i('emiten_per_episode', 40)),
        'imbalan': config.get('imbalan', 'absolut'),
        'seed': i('seed', 7),
        'pakai_arus': bool(config.get('pakai_arus')),
        'pakai_lintas': bool(config.get('pakai_lintas')),
        'pakai_sinyal': bool(config.get('pakai_sinyal')),
        'pakai_insider': bool(config.get('pakai_insider')),
    }


FIELDS = [
    {'k': 'universe', 'label': 'Universe', 'tipe': 'pilih', 'opsi': [
        ['semua', 'Semua emiten (seluruh daftar app ini)'],
        ['likuid30', '30 emiten likuid'],
        ['test21', '21 emiten folder Test (semesta uji modul lain)'],
        ['portofolio', 'Isi portofolio saya'],
        ['kustom', 'Daftar sendiri'],
    ], 'bantu': 'Semesta penuh butuh unduhan awal beberapa menit (lalu di-cache).'},
    {'k': 'maks_emiten', 'label': 'Batas jumlah emiten', 'tipe': 'angka', 'min': 0, 'max': 1000,
     'bantu': '0 = tanpa batas. Kalau melebihi, disaring ke yang paling likuid. '
              'Di atas ~300 emiten panelnya berat di memori.'},
    {'k': 'emiten_per_episode', 'label': 'Emiten per episode latihan', 'tipe': 'angka',
     'min': 5, 'max': 200,
     'bantu': 'Latihan memakai sampel acak sebesar ini tiap episode; evaluasi tetap '
              'memakai universe penuh. Ini yang membuat universe besar tetap muat.'},
    {'k': 'kustom', 'label': 'Daftar kustom', 'tipe': 'teks',
     'bantu': 'Kode dipisah spasi/koma, mis. BBRI ANTM ADRO', 'hanya_jika': 'kustom'},
    {'k': 'mulai_tahun', 'label': 'Mulai tahun', 'tipe': 'angka', 'min': 2005, 'max': 2023},
    {'k': 'latih_tahun', 'label': 'Tahun latih per fold', 'tipe': 'angka', 'min': 2, 'max': 12},
    {'k': 'uji_tahun', 'label': 'Tahun uji per fold', 'tipe': 'angka', 'min': 1, 'max': 3},
    {'k': 'iterasi', 'label': 'Iterasi PPO', 'tipe': 'angka', 'min': 1, 'max': 60,
     'bantu': 'Terukur ~0,8 detik per (iterasi x episode) per fold. Unduhan awal '
              'universe penuh menambah ~70 detik sekali, lalu di-cache.'},
    {'k': 'episode_per_iterasi', 'label': 'Episode per iterasi', 'tipe': 'angka', 'min': 1, 'max': 16},
    {'k': 'n_seed', 'label': 'Jumlah seed', 'tipe': 'angka', 'min': 1, 'max': 5,
     'bantu': 'Sebaran antar-seed adalah ukuran seberapa banyak hasilnya cuma keberuntungan.'},
    {'k': 'n_eval', 'label': 'Rollout evaluasi per seed', 'tipe': 'angka', 'min': 1, 'max': 10,
     'bantu': 'Kebijakannya stokastik, jadi tiap jalan uji beda. Dirata-ratakan.'},
    {'k': 'imbalan', 'label': 'Reward yang dioptimalkan', 'tipe': 'pilih', 'opsi': [
        ['absolut', 'Absolut (log ekuitas saja) — kejar untung, boleh diam'],
        ['relatif', 'Relatif pasar (log ekuitas - log pasar) — wajib kalahkan pasar'],
    ], 'bantu': 'Absolut: memegang kas bernilai nol, jadi agen boleh memilih tidak '
                'berdagang saat tidak ada peluang. Periksa kolom eksposur di hasil.'},
    {'k': 'maks_posisi', 'label': 'Maks posisi bersamaan', 'tipe': 'angka', 'min': 1, 'max': 20},
    {'k': 'maks_porsi_saham', 'label': 'Batas porsi per saham', 'tipe': 'angka',
     'step': 0.05, 'min': 0.05, 'max': 1},
    {'k': 'maks_porsi_adv', 'label': 'Batas order vs likuiditas', 'tipe': 'angka',
     'step': 0.01, 'min': 0.005, 'max': 0.5,
     'bantu': 'Order dibatasi sekian bagian nilai transaksi rata-rata 20 hari.'},
    {'k': 'modal', 'label': 'Modal awal (Rp)', 'tipe': 'angka', 'step': 1000000},
    {'k': 'fee_beli', 'label': 'Fee beli', 'tipe': 'angka', 'step': 0.0005},
    {'k': 'fee_jual', 'label': 'Fee jual', 'tipe': 'angka', 'step': 0.0005},
    {'k': 'slippage', 'label': 'Slippage per sisi', 'tipe': 'angka', 'step': 0.0005},
    {'k': 'risk_aversion', 'label': 'Penalti drawdown', 'tipe': 'angka', 'step': 0.1,
     'bantu': '0 = kejar return apa pun risikonya. Naikkan untuk kurva lebih halus.'},
    {'k': 'seed', 'label': 'Seed dasar', 'tipe': 'angka'},
    {'k': 'pakai_arus', 'label': 'Pakai sinyal arus broker (Net Top5 + ritel)',
     'tipe': 'centang',
     'bantu': 'Cakupannya cuma ~161 hari (2026). Nyalakan untuk memeriksa, bukan untuk mengklaim.'},
    {'k': 'pakai_lintas', 'label': 'Pakai kabar semalam (S&P + komoditas kembaran)',
     'tipe': 'centang',
     'bantu': 'Sesi luar bertanggal t selesai sebelum BEI buka t+1, saat order dieksekusi.'},
    {'k': 'pakai_sinyal', 'label': 'Pakai sinyal tembus basis / 52w high + support chart',
     'tipe': 'centang',
     'bantu': 'Rumus sama dengan halaman Tembus Basis dan garis support chart.'},
    {'k': 'pakai_insider', 'label': 'Pakai jual insider 60 hari',
     'tipe': 'centang',
     'bantu': 'Data baru ada sejak April 2026, digeser %d hari bursa. Untuk memeriksa saja.'
              % JEDA_INSIDER},
]

DEFAULTS = _normalkan({})

research.register(
    key='rl_trading',
    label='RL Trading (PPO, walk-forward)',
    ringkas=('Satu kebijakan yang memutuskan sekaligus saham mana yang dibeli, '
             'porsinya, TP/SL dalam kelipatan ATR, dan berapa lama ditahan. '
             'Dilatih per jendela tahun dan diuji di tahun berikutnya yang belum '
             'pernah dilihat, dibandingkan beli-tahan dan kebijakan acak.'),
    runner=jalankan_rl,
    fields=FIELDS,
    defaults=DEFAULTS,
)
