"""
Menu untuk <external-tools>/Saham Kering\\bdm_screener_v2.py -- screener
"akumulasi bandar" dengan panjang window bervariasi (K=20..90 hari),
skor = min(korelasi kumulatif Top5 naik, -korelasi kumulatif Retail turun).

KENAPA DIIMPOR LANGSUNG, BUKAN DITULIS ULANG
Scanner Lab (website/live_scan.py) menulis ulang logika deteksi lima
scanner karena scriptnya sengaja membuang sinyal terbaru dan versi live
butuh perilaku BERBEDA (tanpa syarat forward). Itu perlu ditulis ulang,
dan ditulis ulang berarti perlu diverifikasi cocok dengan aslinya.

bdm_screener_v2.py beda: skornya murni trailing (rolling correlation
sampai hari t, tanpa look-ahead), jadi "kandidat terbaru" sudah otomatis
berarti kandidat sungguhan sampai hari ini -- tidak perlu versi live
terpisah. Karena tidak perlu ditulis ulang, importnya langsung ke modul
aslinya lewat sys.path, PERSIS seperti script itu sendiri mengimpor
saham_kering_idx.py dan bdm_screener.py. Zero risiko penyimpangan dari
metodologi yang sudah dikalibrasi hati-hati (lihat docstring
bdm_screener_v2.py soal 7 contoh sungguhan dan kenapa data_end dihitung
per-tiket, bukan global).

TEMUAN YANG WAJIB DILAPORKAN JUJUR
Docstring script menonjolkan bahwa skor >= 0.75 menangkap 5 dari 7 contoh
akumulasi sungguhan yang disebut user. Itu soal akurasi DETEKSI pada
kasus yang sudah diketahui hasilnya -- BUKAN bukti bahwa membeli setiap
kali sinyal ini muncul di seluruh bursa itu menguntungkan.

Backtest sungguhan (simulate_trade, ongkos+slippage nyata, terhadap
seluruh 529 sinyal per 4 Sep 2026) menunjukkan sebaliknya:

    H     n     rata2     win rate   vs pasar
    5    498   -9,44%      21,9%     -9,79pp
    10   480   -8,55%      24,4%     -8,78pp
    21   434   -6,45%      28,8%     -6,68pp
    42   328   -6,73%      28,7%     -4,98pp
    63   213  -11,60%      22,5%     -2,82pp

Dicek ulang terhadap hasil tersimpan dari 1 Sep 2026 (bdm_v2_trades.csv,
sebelum 4 hari data tambahan) -- angkanya konsisten (H=5: -9,90% vs
-9,44%), bukan kebetulan sesaat. Screener ini terbukti BAGUS mendeteksi
pola akumulasi yang sudah diketahui, tapi HASIL RATA-RATA membeli setiap
sinyalnya secara sistematis MERUGI dan kalah jauh dari pasar di semua
horizon. Halaman ini menampilkan keduanya berdampingan, apa adanya.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import os
import pickle
import sys
import time

import logging
import threading

import numpy as np
import pandas as pd

from .flow_health import check as flow_check

KERING_DIR = os.environ.get('KERING_SOURCE_DIR', str(_RUNTIME_DIR / 'external' / 'screener'))
SUMMARY_DIR = _market_file('Daily/Summary')
logger = logging.getLogger(__name__)

CACHE_FILE = str(_runtime_file('', 'kering_screener_cache.pkl'))

CONTOH_KALIBRASI = ["ASPR", "ALKA", "AYAM", "BSSR", "HOPE", "JECX", "MMIX"]


def _import_v2():
    """
    Impor bdm_screener_v2.py (dan dependensinya saham_kering_idx.py,
    bdm_screener.py) langsung dari folder aslinya. Dicek dulu nama
    modulnya tidak bentrok dengan modul app ini sebelum disisipkan ke
    sys.path -- app ini sudah punya config.py/utilities.py/views.py
    sendiri sebagai submodul package (website.config dst.), jadi tidak
    akan bentrok dengan modul bernama sama yang diimpor sebagai top-level
    (bdm_screener_v2, saham_kering_idx), tapi tetap diperiksa eksplisit
    di sini supaya kalau suatu saat ada nama yang sama, ketahuan cepat.
    """
    if not os.path.isdir(KERING_DIR):
        raise RuntimeError('Folder Saham Kering tidak ditemukan: %s' % KERING_DIR)
    if KERING_DIR not in sys.path:
        sys.path.insert(0, KERING_DIR)
    import bdm_screener_v2 as v2
    import saham_kering_idx as sk
    return v2, sk


def _run_pipeline():
    """
    Jalankan pipeline penuh: baca data -> skor -> saring -> backtest.
    ~35 detik untuk 875 emiten -- karena itu selalu dipanggil lewat
    refresh() yang meng-cache hasilnya, bukan dipanggil langsung per
    request.
    """
    v2, sk = _import_v2()

    frames, buang = v2.baca_v2(SUMMARY_DIR)
    if len(frames) < 40:
        raise RuntimeError('Data harian terlalu sedikit (%d emiten).' % len(frames))

    per, ev = {}, []
    hit_counts = {}
    for ticker, g in frames.items():
        m = v2.metrik(g)
        per[ticker] = m
        mask, kriteria = v2.saring(m)
        for key, cond in kriteria.items():
            hit_counts[key] = hit_counts.get(key, 0) + int(cond.fillna(False).sum())
        last = None
        for dt in mask[mask].index:
            if last is not None and (dt - last).days < v2.C['COOLDOWN']:
                continue
            last = dt
            ev.append(dict(date=dt, ticker=ticker, **{
                k: float(m.at[dt, k]) for k in
                ['skor', 'K', 'corr_top5', 'corr_ritel', 'naik', 'lonjakan_max', 'adv', 'close']
            }))

    events = pd.DataFrame(ev)
    if events.empty:
        raise RuntimeError('Tidak ada kandidat yang lolos saringan saat ini.')

    idx = pd.DatetimeIndex(sorted({d for m in per.values() for d in m.index}))
    score = pd.DataFrame(np.nan, index=idx, columns=list(frames))
    for ticker, m in per.items():
        pool = ((m['adv'] >= v2.C['MIN_ADV']) & (m['adv'] <= v2.C['MAX_ADV'])).fillna(False)
        score.loc[m.index[pool], ticker] = 0.1
    for _, e in events.iterrows():
        score.at[e.date, e.ticker] = 1.0

    sk.CFG['HORIZONS'] = v2.C['HORIZONS']
    bt = v2.backtest_v2(events, frames, score)

    kalibrasi = []
    for kode in CONTOH_KALIBRASI:
        rows = events[events.ticker == kode]
        if rows.empty:
            skor_max = float(per[kode]['skor'].max()) if kode in per else None
            kalibrasi.append({'ticker': kode, 'tertangkap': False, 'skor_tertinggi': skor_max})
        else:
            r = rows.iloc[-1]
            kalibrasi.append({'ticker': kode, 'tertangkap': True,
                              'date': r.date.strftime('%Y-%m-%d'),
                              'skor': round(float(r.skor), 3), 'K': int(r.K),
                              'naik_pct': round(float(r.naik) * 100, 1)})

    return {
        'events': events, 'bt': bt, 'hit_counts': hit_counts,
        'kalibrasi': kalibrasi, 'n_emiten': len(frames), 'n_dibuang': len(buang),
        'config': dict(v2.C),
    }


def _newest_summary_mtime():
    if not os.path.isdir(SUMMARY_DIR):
        return 0
    newest = 0
    for name in os.listdir(SUMMARY_DIR):
        if name.endswith('_Summary.csv'):
            mtime = os.path.getmtime(os.path.join(SUMMARY_DIR, name))
            if mtime > newest:
                newest = mtime
    return newest


_bangun_kunci = threading.Lock()
_sedang_bangun = {'jalan': False}


def _bangun_dan_simpan():
    result = _run_pipeline()
    result['built_at'] = time.time()
    result['from_cache'] = False
    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump(result, fh)
    except Exception:
        pass
    return result


_gagal_latar = {'pesan': None}


def _bangun_di_latar():
    def kerja():
        try:
            _bangun_dan_simpan()
            _gagal_latar['pesan'] = None
        except Exception as exc:
            # JANGAN ditelan diam-diam. Versi pertama memakai `except: pass`,
            # dan akibatnya: pembangunan latar gagal tanpa jejak sementara
            # halaman terus menyajikan cache basi selamanya -- terlihat
            # seperti "cache tidak pernah diperbarui" tanpa satu pun petunjuk.
            _gagal_latar['pesan'] = '%s: %s' % (type(exc).__name__, exc)
            logger.exception('Pembangunan ulang Kering Screener di latar gagal')
        finally:
            with _bangun_kunci:
                _sedang_bangun['jalan'] = False

    with _bangun_kunci:
        if _sedang_bangun['jalan']:
            return False
        _sedang_bangun['jalan'] = True
    threading.Thread(target=kerja, daemon=True, name='kering-refresh').start()
    return True


def refresh(force=False, boleh_basi=True):
    """
    Hasil pipeline dari cache.

    KENAPA BOLEH MENYAJIKAN YANG BASI

    Cache dibatalkan begitu ADA SATU SAJA dari 881 berkas Summary yang
    lebih baru daripada cache. Satu berkas tersentuh -> seluruh 875 emiten
    dihitung ulang. Terukur: cache hangat 0,4 detik, cache batal 33 detik.

    Itu terasa terus-menerus lambat karena unduhan harian menyentuh berkas
    Summary satu per satu sepanjang prosesnya -- yang bisa berjam-jam --
    jadi hampir tiap pemuatan halaman selama itu membayar 33 detik penuh
    untuk data yang baru berubah satu emiten.

    Sekarang: kalau cache ada tapi basi, cache LAMA langsung disajikan dan
    pembangunan ulang dijalankan di latar. Halaman terbuka seketika, data
    segar muncul di pemuatan berikutnya. `stale=True` ditandai di hasil
    supaya tampilan bisa memberi tahu bahwa angkanya sedang diperbarui.

    Hanya kalau BELUM ADA cache sama sekali, pemanggil menunggu 33 detik --
    dan itu memang tidak bisa dihindari.

    boleh_basi=False memaksa menunggu hasil segar (dipakai skrip/CLI).
    """
    newest = _newest_summary_mtime()
    cached = None
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
        except Exception:
            cached = None

    if not force and cached is not None and cached.get('built_at', 0) >= newest:
        cached['from_cache'] = True
        cached['stale'] = False
        return cached

    if cached is not None and boleh_basi and not force and not _gagal_latar['pesan']:
        # Sajikan yang lama, perbarui di latar. Kunci mencegah dua request
        # bersamaan sama-sama menghabiskan 33 detik untuk pekerjaan yang sama.
        _bangun_di_latar()
        cached['from_cache'] = True
        cached['stale'] = True
        return cached

    # tidak ada cache sama sekali (atau dipaksa) -> mau tak mau menunggu
    with _bangun_kunci:
        _sedang_bangun['jalan'] = True
    try:
        result = _bangun_dan_simpan()
    finally:
        with _bangun_kunci:
            _sedang_bangun['jalan'] = False
    result['stale'] = False
    return result


def _summarize(bt):
    """Sama seperti saham_kering_idx.summarize(), diringkas untuk JSON."""
    ok = bt.dropna(subset=['ret'])
    if ok.empty:
        return []
    out = []
    for horizon, g in ok.groupby('horizon'):
        mean = float(g['ret'].mean())
        out.append({
            'horizon': int(horizon), 'n': int(len(g)),
            'mean_pct': round(mean * 100, 2),
            'median_pct': round(float(g['ret'].median()) * 100, 2),
            'win_rate': round(float((g['ret'] > 0).mean() * 100), 1),
            'vs_pasar_pp': round((mean - float(g['bench'].mean())) * 100, 2),
            'vs_kontrol_pp': round((float(g['gross'].mean()) - float(g['ctrl'].mean())) * 100, 2),
        })
    return sorted(out, key=lambda r: r['horizon'])


def build_report(days_back=30, force=False):
    """Ringkasan siap-tampil untuk halaman."""
    try:
        data = refresh(force=force)
    except Exception as exc:
        return {'available': False, 'message': str(exc)}

    events = data['events']
    cutoff = events['date'].max() - pd.Timedelta(days=days_back)
    # Urut tanggal terbaru dulu, lalu skor tertinggi dulu sebagai kunci
    # kedua -- tanpa ini, baris bertanggal sama diurutkan lewat quicksort
    # (default sort_values), yang TIDAK stabil untuk nilai yang sama.
    # Akibatnya urutan kandidat dalam satu tanggal jadi artefak algoritma
    # sortir, bukan sesuatu yang berarti (terbukti: TPMA 0,79 pernah
    # muncul di atas LTLS 0,88 pada tanggal yang sama).
    recent = events[events['date'] >= cutoff].sort_values(
        ['date', 'skor'], ascending=[False, False])

    rows = []
    for _, r in recent.iterrows():
        row = {
            'date': r['date'].strftime('%Y-%m-%d'), 'ticker': r['ticker'],
            'close': round(float(r['close']), 2), 'skor': round(float(r['skor']), 3),
            'K': int(r['K']), 'naik_pct': round(float(r['naik']) * 100, 1),
            'adv_juta': round(float(r['adv']) / 1e6, 1),
        }
        # Kesehatan arus SETELAH sinyal ini -- lihat flow_health.py.
        # Dihitung di sini (bukan lewat request AJAX terpisah) karena
        # cuma ~4,5ms per baris; menambah round-trip tidak sepadan.
        try:
            fh = flow_check(r['ticker'], row['date'])
            row['flow'] = fh['checkpoints'] if fh.get('available') else []
        except Exception:
            row['flow'] = []
        rows.append(row)

    return {
        'available': True,
        'n_emiten': data['n_emiten'], 'n_dibuang': data['n_dibuang'],
        'n_event_total': len(events),
        'as_of': events['date'].max().strftime('%Y-%m-%d'),
        'from_cache': data.get('from_cache', False),
        'stale': data.get('stale', False),
        'summary': _summarize(data['bt']),
        'kalibrasi': data['kalibrasi'],
        'candidates': rows,
        'config': {'SKOR_MIN': data['config']['SKOR_MIN'],
                   'MIN_ADV_juta': data['config']['MIN_ADV'] / 1e6,
                   'MIN_NAIK_pct': data['config']['MIN_NAIK'] * 100,
                   'MAX_NAIK_pct': data['config']['MAX_NAIK'] * 100,
                   'COOLDOWN': data['config']['COOLDOWN']},
    }
