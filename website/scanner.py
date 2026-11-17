"""
Scanner Lab -- menyatukan hasil script riset sinyal yang selama ini cuma
mengendap sebagai CSV di folder project, lalu memperkayanya dengan data
kepemilikan (KSEI) dan data broker harian (Summary).

DELAPAN SCANNER, SATU FORMAT
Tiap script menulis kolom yang beda-beda; loader di sini menormalkannya
jadi satu bentuk: stock, signal_date, scanner, fwd20 (kalau ada), plus
kolom asli yang khas tiap scanner disimpan di `detail`.

TEMUAN YANG MENDASARI SKOR
Modul ini tidak sekadar menampilkan sinyal -- dia memberi skor, dan
skornya berasal dari backtest terhadap 6.871 sinyal historis (Jan-Sep
2026) yang dipasangkan dengan data kepemilikan dan harian TANPA lookahead
(sinyal tanggal D hanya boleh memakai snapshot KSEI yang tanggal
potongnya sudah lewat sebelum D). Baseline pasar periode itu -1,33% per
20 hari, jadi semua perbandingan relatif terhadap angka itu.

Faktor terkuat, dan arahnya berlawanan dengan intuisi kebanyakan orang:

    Volume hari sinyal    n      rata2 20d   win rate
    < 1x (sepi)          3.849    -1,12%      41,0%
    1-2x                 1.320    -2,34%      37,9%
    2-5x                   898    -4,57%      34,3%
    > 5x (lonjakan)        804    -9,03%      23,8%

Makin ramai volume saat sinyal muncul, makin buruk hasilnya -- monoton di
keempat kelompok. Sudah diuji terhadap dua confound yang bisa memalsukan
temuan ini:

  * Komposisi scanner. Sebagian scanner (big_jump, breakout) memang
    menyala HANYA saat volume melonjak, jadi "volume tinggi jelek" bisa
    saja cuma "scanner itu jelek". Ternyata efeknya bertahan DI DALAM
    scanner yang sama sekali tidak berbasis volume: slope_turn -1,95pp
    (n=5.178) dan divergence -7,20pp (n=1.126), keduanya monoton.
  * Rezim pasar. Arahnya konsisten di ketiga kuartal, termasuk Q3 2026
    saat pasar naik (sepi +8,49% vs ramai +5,91%). Yang berubah cuma
    level absolutnya, bukan urutannya.

Faktor kepemilikan sendiri LEMAH (selisih kuartil cuma 1-2pp dan tidak
monoton), jadi bobotnya kecil. Kombinasi terbaik yang ditemukan --
volume sepi + basis ritel tinggi + arus ritel mendingin -- mencapai
+2,59pp di atas baseline (n=492, win 45,1%).

BATASNYA, DAN INI PENTING
Win rate kombinasi terbaik pun masih di bawah 50%, dan median-nya masih
negatif -- rata-rata positif ditarik segelintir pemenang besar, bukan
konsistensi. Periodenya cuma ~8 bulan dan didominasi pasar turun. Skor di
sini adalah ringkasan pola historis, BUKAN prediksi dan bukan saran beli.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import os
import re
from datetime import datetime

import pandas as pd
import numpy as np

from .config import DAILY_PATH
from .ownership import load_ksei_months, build_month_metrics, ksei_signature
from .live_scan import cached_scan, FORWARD_NEEDED
from .flow_health import check as flow_check

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
SCANNER_DIR = os.path.dirname(__file__)

# Rata-rata return 20 hari SELURUH pasar pada periode data (116.522
# pengamatan). Semua penilaian relatif terhadap angka ini -- tanpa
# pembanding, "-7%" tidak berarti apa-apa saat pasarnya sendiri turun.
MARKET_BASELINE_20D = -1.33

# Definisi tiap scanner: file, label, kolom forward-return, dan kolom
# khas yang menarik ditampilkan di tabel.
SCANNERS = {
    'divergence': {
        'file': 'divergence_signals.csv',
        'label': 'Divergensi Domestik vs Asing',
        'desc': 'Top5 domestik borong agresif saat asing justru melepas di hari yang sama.',
        'fwd': 'fwd_return_20d',
        'detail': ['domestic_z', 'foreign_z'],
    },
    'big_jump': {
        'file': 'big_jump_days.csv',
        'label': 'Lompatan Harian Besar',
        'desc': 'Satu hari harga melonjak besar disertai lonjakan volume.',
        'fwd': 'fwd_return_20d',
        'detail': ['day_jump_pct', 'vol_mult', 'sideways_range_pct'],
    },
    'slow_accum': {
        'file': 'slow_accumulation_signals.csv',
        'label': 'Akumulasi Senyap 60 Hari',
        'desc': 'Akumulasi bertahap 60 hari, sengaja mengecualikan yang didominasi satu hari lonjakan.',
        'fwd': 'fwd_return_20d',
        'detail': ['net_top5_60d_sum', 'retail_60d_sum', 'price_drift_60d_pct'],
    },
    'top_winners': {
        'file': 'top_winners_precursors.csv',
        'label': 'Prekursor Pemenang Besar',
        'desc': 'Rally 20 hari terbesar, dilihat mundur apa yang mendahuluinya.',
        'fwd': 'fwd_return_20d',
        'detail': ['day_jump_pct', 'vol_mult', 'net_mult'],
        # Scanner ini MENDEFINISIKAN dirinya sebagai "rally terbesar", jadi
        # forward return positif adalah konsekuensi definisi, bukan
        # prediksi. Win rate-nya 100% -- tanda selection bias, bukan
        # sinyal bagus. Dikecualikan dari statistik & skor.
        'retrospective': True,
    },
    'breakout': {
        'file': 'breakout_signals.csv',
        'label': 'Breakout dari Sideways',
        'desc': 'Keluar dari rentang sempit dengan volume di atas normal.',
        'long_format': True,
        'detail': ['vol_mult', 'sideways_range_pct'],
    },
    'slope_turn': {
        'file': 'slope_turn_results.csv',
        'label': 'Pembalikan Slope Net Top5',
        'desc': 'Slope akumulasi Top5 berbalik arah dari negatif ke positif.',
        'long_format': True,
        'detail': ['group'],
    },
}


def _read_csv(name):
    path = str(_runtime_file('', name))
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def load_signals(scanner=None):
    """
    Semua sinyal dari semua scanner dalam satu DataFrame ternormalisasi.

    Dua bentuk file harus ditangani: sebagian satu baris per sinyal
    (punya kolom fwd_return_20d langsung), sebagian lagi format panjang
    satu baris per HARI setelah sinyal -- untuk yang itu, baris hari ke-20
    diambil sebagai forward return dan baris hari ke-1 sebagai identitas
    sinyalnya.
    """
    frames = []
    for key, cfg in SCANNERS.items():
        if scanner and key != scanner:
            continue
        df = _read_csv(cfg['file'])
        if df is None or 'stock' not in df.columns:
            continue

        if cfg.get('long_format'):
            if not {'day', 'return_pct'}.issubset(df.columns):
                continue
            base_cols = ['stock', 'signal_date', 'entry_close']
            base_cols += [c for c in cfg.get('detail', []) if c in df.columns]
            first = df[df['day'] == 1][base_cols].drop_duplicates(
                subset=['stock', 'signal_date'])
            d20 = df[df['day'] == 20][['stock', 'signal_date', 'return_pct']]
            d20 = d20.rename(columns={'return_pct': 'fwd20'})
            out = first.merge(d20, on=['stock', 'signal_date'], how='left')
        else:
            fwd = cfg.get('fwd')
            keep = ['stock', 'signal_date']
            if 'entry_close' in df.columns:
                keep.append('entry_close')
            keep += [c for c in cfg.get('detail', []) if c in df.columns]
            out = df[keep + ([fwd] if fwd in df.columns else [])].copy()
            if fwd in df.columns:
                out = out.rename(columns={fwd: 'fwd20'})
            else:
                out['fwd20'] = np.nan

        out['scanner'] = key
        out['scanner_label'] = cfg['label']
        out['retrospective'] = bool(cfg.get('retrospective'))
        frames.append(out)

    if not frames:
        return pd.DataFrame()

    allsig = pd.concat(frames, ignore_index=True, sort=False)
    allsig['signal_date'] = pd.to_datetime(allsig['signal_date'], errors='coerce')
    allsig = allsig.dropna(subset=['signal_date'])
    allsig['stock'] = allsig['stock'].astype(str).str.upper().str.strip()
    return allsig.sort_values('signal_date', ascending=False).reset_index(drop=True)


_PANEL_MEM = {'sig': None, 'df': None}


def ownership_panel():
    """
    Panel kepemilikan per (emiten, bulan) + perubahan bulan-ke-bulan.
    Dipakai untuk menempelkan konteks kepemilikan ke tiap sinyal.

    Disimpan di memori selama berkas KSEI tidak berubah: enrich() memanggil
    ini di tiap pembukaan Halaman Saham, dan membangunnya ulang (~900
    emiten x 12 bulan) makan ~0,3 detik untuk hasil yang sama persis.
    """
    sig = ksei_signature()
    if sig and sig == _PANEL_MEM['sig']:
        return _PANEL_MEM['df']
    df = _build_ownership_panel()
    _PANEL_MEM.update(sig=sig, df=df)
    return df


def _build_ownership_panel():
    rows = []
    prev = {}
    for payload in load_ksei_months():
        as_of = pd.to_datetime(payload['as_of'])
        for ticker, rec in payload.get('securities', {}).items():
            m = build_month_metrics(rec)
            if not m['scripless']:
                continue
            before = prev.get(ticker)
            rows.append({
                'stock': ticker,
                'as_of': as_of,
                'own_pct_foreign': round(m['pct_foreign'], 2),
                # PERHATIAN: ini bucket "Individu" KSEI MENTAH (local['ID'] /
                # scripless), BUKAN ritel. KSEI memilah per tipe investor, jadi
                # pengendali yang memegang sahamnya atas nama pribadi masuk ke
                # sini juga. PSAB 92,96% "individu" ternyata 90% satu nama
                # (Jimmy Budiarto); ritel sesungguhnya 0,46%. IOTF 98,85% -> 0%,
                # DEWI 91,89% -> 0%. Dari 45 emiten yang punya data pemegang
                # saham bernama, 14 berselisih.
                #
                # ownership.build_ownership() menyaring ini lewat split_retail()
                # dan itu yang dipakai halaman Kepemilikan Saham. TIDAK bisa
                # dipakai di sini: carve-out butuh registry per emiten, dan itu
                # cuma ada untuk 45 dari 1010 emiten -- memangkas 45 saja
                # membuat retail_median membandingkan dua besaran berbeda.
                # Jadi angkanya dibiarkan mentah, tapi namanya jangan bohong.
                'own_pct_individu': round(m['pct_retail'], 2),
                'own_pct_local_non_retail': round(m['pct_local_non_retail'], 2),
                'own_scripless_pct': round(m['scripless_pct_of_listed'], 2),
                'own_d_foreign': round(m['pct_foreign'] - before['pct_foreign'], 2) if before else None,
                'own_d_individu': round(m['pct_retail'] - before['pct_retail'], 2) if before else None,
            })
            prev[ticker] = m
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(['stock', 'as_of']).reset_index(drop=True)


def summary_features(stocks):
    """
    Fitur harian dari {stock}_Summary.csv: volume relatif dan arus 20 hari.

    vol_mult (volume hari itu dibanding rata-rata 20 hari SEBELUMNYA)
    adalah faktor terkuat di backtest, jadi ini inti dari fungsi ini.
    Rata-ratanya di-shift(1) supaya hari yang sedang dinilai tidak ikut
    masuk ke rata-ratanya sendiri.
    """
    frames = []
    for stock in sorted(set(stocks)):
        path = os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock)
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if 'Date' not in df.columns:
            continue
        df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
        df = df.dropna(subset=['Date']).sort_values('Date')
        for col in ['Net Top5 All Lot', 'Retail', 'Volume', 'Close', 'Open']:
            df[col] = pd.to_numeric(df.get(col), errors='coerce')

        vol_avg = df['Volume'].rolling(20, min_periods=5).mean().shift(1)
        # Nilai transaksi harian = (Open+Close)/2 x Volume, rata-rata 20
        # hari -- rumus yang sama dipakai screen_eval.py/stock_hub.py.
        # Ditambahkan supaya Scanner Lab bisa dibaca berdampingan dengan
        # temuan screen_eval.py sendiri: nilai transaksi besar berkorelasi
        # dengan hasil yang lebih buruk, persis seperti lonjakan volume.
        nilai = (df['Open'] + df['Close']) / 2 * df['Volume']
        frames.append(pd.DataFrame({
            'stock': stock,
            'Date': df['Date'],
            'day_close': df['Close'],
            'vol_mult': (df['Volume'] / vol_avg).round(2),
            'net5_cum20': df['Net Top5 All Lot'].rolling(20, min_periods=5).sum(),
            'retail_cum20': df['Retail'].rolling(20, min_periods=5).sum(),
            'adv_juta': (nilai.rolling(20, min_periods=5).mean() / 1e6).round(1),
        }))
    if not frames:
        return pd.DataFrame(columns=['stock', 'Date', 'day_close', 'vol_mult',
                                     'net5_cum20', 'retail_cum20', 'adv_juta'])
    return pd.concat(frames, ignore_index=True)


def enrich(signals):
    """
    Tempelkan konteks kepemilikan + harian ke tiap sinyal.

    Penempelan kepemilikan memakai merge_asof arah 'backward' dengan
    allow_exact_matches=False: sinyal tanggal D hanya boleh dipasangkan
    dengan snapshot KSEI yang tanggal potongnya SUDAH LEWAT sebelum D.
    Tanpa disiplin ini, skor akan memakai informasi yang belum terbit saat
    sinyal muncul, dan semua statistiknya jadi palsu.
    """
    if signals.empty:
        return signals

    panel = ownership_panel()
    if not panel.empty:
        signals = pd.merge_asof(
            signals.sort_values('signal_date'),
            panel.sort_values('as_of'),
            left_on='signal_date', right_on='as_of', by='stock',
            direction='backward', allow_exact_matches=False)
    else:
        for col in ['own_pct_foreign', 'own_pct_individu', 'own_pct_local_non_retail',
                    'own_scripless_pct', 'own_d_foreign', 'own_d_individu']:
            signals[col] = None

    # big_jump dan breakout sudah punya kolom 'vol_mult' versi mereka
    # sendiri. Diberi nama lain supaya tidak bentrok saat merge -- yang
    # dipakai untuk skor adalah versi yang dihitung seragam dari Summary
    # di bawah, karena itu tersedia untuk SEMUA scanner, bukan cuma dua
    # itu, jadi skornya bisa dibandingkan antar scanner.
    if 'vol_mult' in signals.columns:
        signals = signals.rename(columns={'vol_mult': 'scanner_vol_mult'})

    daily = summary_features(signals['stock'].unique())
    if not daily.empty:
        signals = signals.merge(daily, left_on=['stock', 'signal_date'],
                                right_on=['stock', 'Date'], how='left')
    else:
        for col in ['vol_mult', 'net5_cum20', 'retail_cum20', 'day_close', 'adv_juta']:
            signals[col] = None

    return signals.sort_values('signal_date', ascending=False).reset_index(drop=True)


def score_signal(row, retail_median=None):
    """
    Skor 0-100 dari pola yang terbukti di backtest, plus alasannya.

    Bobotnya sengaja timpang: volume dapat porsi terbesar karena itu satu-
    satunya faktor yang efeknya besar (selisih 7,9pp antar kelompok),
    monoton, dan bertahan di dalam scanner non-volume maupun di ketiga
    kuartal. Faktor kepemilikan dapat bobot kecil karena selisih
    kuartilnya cuma 1-2pp dan tidak monoton -- memberi mereka bobot besar
    berarti berpura-pura tahu lebih banyak daripada yang ditunjukkan data.
    """
    score = 50.0
    reasons = []

    vol = row.get('vol_mult')
    if vol is not None and not pd.isna(vol):
        if vol < 1:
            score += 22
            reasons.append(('baik', 'Volume sepi (%.1fx) — kelompok terbaik di backtest (-1,12%%, menang 41%%)' % vol))
        elif vol < 2:
            score += 8
            reasons.append(('netral', 'Volume normal (%.1fx)' % vol))
        elif vol < 5:
            score -= 12
            reasons.append(('buruk', 'Volume ramai (%.1fx) — kelompok ini rata-rata -4,57%%' % vol))
        else:
            score -= 25
            reasons.append(('buruk', 'Volume melonjak (%.1fx) — kelompok terburuk (-9,03%%, menang cuma 24%%)' % vol))

    # Bucket "Individu" KSEI, bukan ritel -- lihat catatan panjang di
    # ownership_panel(). Disebut apa adanya supaya pembaca halaman tidak
    # menyimpulkan "banyak ritel" dari emiten yang sebenarnya dikuasai satu
    # pemegang perorangan.
    individu_own = row.get('own_pct_individu')
    if individu_own is not None and not pd.isna(individu_own) and retail_median is not None:
        if individu_own > retail_median:
            score += 8
            reasons.append(('baik', 'Bucket individu KSEI tebal (%.1f%%) — ada di semua kombinasi '
                                    'terbaik. Belum tentu ritel: pemegang perorangan besar ikut '
                                    'terhitung di sini.' % individu_own))
        else:
            reasons.append(('netral', 'Bucket individu KSEI tipis (%.1f%%)' % individu_own))

    retail_flow = row.get('retail_cum20')
    if retail_flow is not None and not pd.isna(retail_flow):
        if retail_flow <= 0:
            score += 8
            reasons.append(('baik', 'Arus ritel 20 hari mendingin — muncul di kombinasi terbaik'))
        else:
            score -= 6
            reasons.append(('buruk', 'Ritel masih memborong 20 hari terakhir — ciri kombinasi terburuk'))

    d_ret = row.get('own_d_individu')
    if d_ret is not None and not pd.isna(d_ret) and d_ret <= 0:
        score += 4
        # Nol persis berarti tidak bergerak, bukan turun -- menyebutnya
        # "turun" akan salah walau nilainya lolos syarat <= 0.
        reasons.append(('baik', 'Porsi individu KSEI %s bulan lalu (%+.2fpp)' % (
            'turun' if d_ret < 0 else 'tidak naik', d_ret)))

    if row.get('retrospective'):
        reasons.append(('buruk', 'Scanner retrospektif — hasil positifnya konsekuensi definisi, bukan prediksi'))

    return max(0, min(100, round(score))), reasons


def build_scanner_view(scanner=None, limit=300, min_date=None):
    """Data siap-pakai untuk halaman: sinyal terbaru + konteks + skor."""
    signals = load_signals(scanner)
    if signals.empty:
        return {'available': False, 'message': 'Belum ada file hasil scanner.'}

    if min_date is not None:
        signals = signals[signals['signal_date'] >= pd.Timestamp(min_date)]
    signals = signals.head(limit * 3)
    signals = enrich(signals)

    retail_median = None
    if 'own_pct_individu' in signals.columns:
        vals = pd.to_numeric(signals['own_pct_individu'], errors='coerce').dropna()
        retail_median = float(vals.median()) if len(vals) else None

    rows = []
    for _, row in signals.head(limit).iterrows():
        score, reasons = score_signal(row, retail_median)

        def clean(value):
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return None
            if isinstance(value, (np.integer, np.floating)):
                value = float(value)
                return None if pd.isna(value) else round(value, 2)
            return value

        signal_date_str = row['signal_date'].strftime('%Y-%m-%d')
        try:
            fh = flow_check(row['stock'], signal_date_str)
            flow = fh['checkpoints'] if fh.get('available') else []
        except Exception:
            flow = []

        rows.append({
            'stock': row['stock'],
            'signal_date': signal_date_str,
            'scanner': row['scanner'],
            'scanner_label': row['scanner_label'],
            'retrospective': bool(row.get('retrospective')),
            'entry_close': clean(row.get('entry_close')),
            'fwd20': clean(row.get('fwd20')),
            'vol_mult': clean(row.get('vol_mult')),
            'adv_juta': clean(row.get('adv_juta')),
            'net5_cum20': clean(row.get('net5_cum20')),
            'retail_cum20': clean(row.get('retail_cum20')),
            'own_pct_foreign': clean(row.get('own_pct_foreign')),
            'own_pct_individu': clean(row.get('own_pct_individu')),
            'own_d_foreign': clean(row.get('own_d_foreign')),
            'own_d_individu': clean(row.get('own_d_individu')),
            'own_as_of': row['as_of'].strftime('%Y-%m-%d') if pd.notna(row.get('as_of')) else None,
            'score': score,
            'reasons': [{'kind': k, 'text': t} for k, t in reasons],
            'flow': flow,
        })

    return {
        'available': True,
        'baseline': MARKET_BASELINE_20D,
        'rows': rows,
        'scanners': [{'key': k, 'label': v['label'], 'desc': v['desc'],
                      'retrospective': bool(v.get('retrospective'))}
                     for k, v in SCANNERS.items()],
    }


def scanner_stats():
    """
    Statistik historis tiap scanner, untuk ditampilkan apa adanya di
    halaman -- termasuk yang hasilnya buruk. Menyembunyikan scanner yang
    kalah dari baseline akan membuat halaman ini menyesatkan.
    """
    signals = load_signals()
    if signals.empty:
        return {'available': False}

    signals = enrich(signals)
    out = []
    for key, cfg in SCANNERS.items():
        sub = signals[(signals['scanner'] == key) & signals['fwd20'].notna()]
        if sub.empty:
            continue
        mean = float(sub['fwd20'].mean())
        out.append({
            'key': key,
            'label': cfg['label'],
            'desc': cfg['desc'],
            'retrospective': bool(cfg.get('retrospective')),
            'n': int(len(sub)),
            'mean': round(mean, 2),
            'median': round(float(sub['fwd20'].median()), 2),
            'win_rate': round(float((sub['fwd20'] > 0).mean() * 100), 1),
            'vs_baseline': round(mean - MARKET_BASELINE_20D, 2),
        })
    out.sort(key=lambda r: r['vs_baseline'], reverse=True)

    # Tabel efek volume, temuan utama yang mendasari skor.
    vol = signals[signals['fwd20'].notna() & signals['vol_mult'].notna()]
    vol = vol[~vol['retrospective']]
    buckets = []
    for label, lo, hi in [('< 1x (sepi)', 0, 1), ('1 - 2x', 1, 2),
                          ('2 - 5x', 2, 5), ('> 5x (lonjakan)', 5, 1e9)]:
        sel = vol[(vol['vol_mult'] >= lo) & (vol['vol_mult'] < hi)]
        if sel.empty:
            continue
        buckets.append({
            'label': label,
            'n': int(len(sel)),
            'mean': round(float(sel['fwd20'].mean()), 2),
            'win_rate': round(float((sel['fwd20'] > 0).mean() * 100), 1),
        })

    return {'available': True, 'baseline': MARKET_BASELINE_20D,
            'scanners': out, 'volume_buckets': buckets}


def build_live_view(scanner=None, limit=300, days_back=60, force=False):
    """
    Sinyal yang MASIH BERJALAN -- hasil live_scan, bukan CSV backtest.

    Bedanya dengan build_scanner_view(): di sini sinyal terbaru ikut
    keluar, termasuk yang forward return-nya belum ada. Justru itu yang
    dibutuhkan untuk memantau kandidat, karena CSV backtest secara desain
    berhenti 1-3 bulan di belakang.
    """
    payload = cached_scan(days_back=days_back, force=force)
    df = payload.get('df')
    if df is None or df.empty:
        return {'available': False, 'message': 'Tidak ada sinyal pada rentang ini.'}

    if scanner:
        df = df[df['scanner'] == scanner]
        if df.empty:
            return {'available': False, 'message': 'Tidak ada sinyal untuk scanner itu.'}

    df = df.head(limit * 2).copy()
    df['scanner_label'] = df['scanner'].map(
        lambda k: SCANNERS.get(k, {}).get('label', k))
    df['retrospective'] = False
    df['fwd20'] = np.nan
    df = enrich(df)

    retail_median = None
    if 'own_pct_individu' in df.columns:
        vals = pd.to_numeric(df['own_pct_individu'], errors='coerce').dropna()
        retail_median = float(vals.median()) if len(vals) else None

    def clean(value):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, (np.integer, np.floating)):
            value = float(value)
            return None if pd.isna(value) else round(value, 2)
        return value

    rows = []
    for _, row in df.head(limit).iterrows():
        score, reasons = score_signal(row, retail_median)
        signal_date_str = row['signal_date'].strftime('%Y-%m-%d')
        try:
            fh = flow_check(row['stock'], signal_date_str)
            flow = fh['checkpoints'] if fh.get('available') else []
        except Exception:
            flow = []

        rows.append({
            'stock': row['stock'],
            'signal_date': signal_date_str,
            'scanner': row['scanner'],
            'scanner_label': row['scanner_label'],
            'pending': bool(row.get('pending')),
            'forward_needed': FORWARD_NEEDED.get(row['scanner'], 20),
            'retrospective': False,
            'entry_close': clean(row.get('entry_close')),
            'fwd20': None,
            'vol_mult': clean(row.get('vol_mult')),
            'adv_juta': clean(row.get('adv_juta')),
            'net5_cum20': clean(row.get('net5_cum20')),
            'retail_cum20': clean(row.get('retail_cum20')),
            'own_pct_foreign': clean(row.get('own_pct_foreign')),
            'own_pct_individu': clean(row.get('own_pct_individu')),
            'own_d_foreign': clean(row.get('own_d_foreign')),
            'own_d_individu': clean(row.get('own_d_individu')),
            'score': score,
            'reasons': [{'kind': k, 'text': t} for k, t in reasons],
            'flow': flow,
        })

    last_date = payload.get('last_data_date')
    return {
        'available': True,
        'mode': 'live',
        'baseline': MARKET_BASELINE_20D,
        'last_data_date': last_date.strftime('%Y-%m-%d') if last_date is not None else None,
        'from_cache': bool(payload.get('from_cache')),
        'days_back': days_back,
        'rows': rows,
        'scanners': [{'key': k, 'label': v['label'], 'desc': v['desc'],
                      'retrospective': bool(v.get('retrospective'))}
                     for k, v in SCANNERS.items() if not v.get('retrospective')],
    }
