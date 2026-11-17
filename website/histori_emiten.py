"""Ringkasan arsip lokal untuk Musiman Saham dan Perubahan Kepemilikan."""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
from datetime import date
from functools import lru_cache
from pathlib import Path
import math

import numpy as np
import pandas as pd

from . import ownership
from .config import DAILY_PATH

MUSIM = _runtime_file('', 'research_cache', 'musiman_saham.pkl')


def musiman():
    try:
        stat = MUSIM.stat()
    except FileNotFoundError:
        return dict(available=False, message='Arsip riset Musiman Saham belum tersedia.')
    return _musiman(stat.st_mtime_ns, stat.st_size, date.today().strftime('%Y-%m'))


@lru_cache(maxsize=1)
def _musiman(mtime, size, bulan_ini):
    archive = pd.read_pickle(MUSIM)
    data = archive['bulanan'].copy()
    # Arsip bisa berhenti di tengah bulan. Abaikan bulan terakhir arsip.
    batas = min(bulan_ini, archive['harian'].index.max().strftime('%Y-%m'))
    period = data['tahun'].astype(str) + '-' + data['bulan'].astype(str).str.zfill(2)
    data = data.loc[(period < batas) & data['likuid'] & np.isfinite(data['lr'])].copy()
    if data.empty:
        return dict(available=False, message='Tidak ada bulan dengan data yang memenuhi syarat riset.')
    data['return'] = np.expm1(data['lr']) * 100
    data['naik'] = data['return'] > 0
    stats = data.groupby(['ticker', 'bulan']).agg(
        sampel=('return', 'size'), median=('return', 'median'),
        rata=('return', 'mean'), naik=('naik', 'sum')).reset_index()
    stats = stats.loc[stats.sampel >= 3]
    saham = {ticker: group.drop(columns='ticker').to_dict('records')
             for ticker, group in stats.groupby('ticker')}
    return dict(available=bool(saham), as_of=str(period.loc[data.index].max()), saham=saham,
                message='Statistik bulan kalender dari arsip riset harga Yahoo yang disesuaikan. '
                        'Minimum 3 observasi per saham dan bulan. Persentase naik = jumlah bulan '
                        'positif dibagi jumlah sampel. Bulan terakhir arsip, bulan berjalan, dan observasi yang gagal '
                        'saringan riset dikeluarkan. Hasil riset lokal tidak menemukan pola '
                        'bulanan per emiten yang konsisten di luar sampel.')


def _angka(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def _holder_map(snapshot):
    result = {}
    duplicates = set()
    for holder in snapshot.get('holders') or []:
        name = ' '.join((holder.get('Nama') or '').split())
        category = (holder.get('Kategori') or '').strip()
        if not name or name.casefold().startswith(('masyarakat', 'saham treasury')):
            continue
        key = name.casefold()
        if key in result:
            duplicates.add(key)
        result[key] = dict(nama=name, kategori=category, pengendali=bool(holder.get('Pengendali')),
                           lembar=_angka(holder.get('Jumlah')), persen=_angka(holder.get('Persentase')))
    return result, duplicates


def banding_registri(ticker, previous, current):
    before, before_duplicates = _holder_map(previous)
    after, after_duplicates = _holder_map(current)
    comparable = (before.keys() | after.keys()) - before_duplicates - after_duplicates
    rows = []
    for key in sorted(comparable):
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        row = new or old
        delta = None
        if old and new and old['lembar'] is not None and new['lembar'] is not None:
            delta = new['lembar'] - old['lembar']
        rows.append(dict(ticker=ticker, nama=row['nama'], kategori=row['kategori'],
                         pengendali=row['pengendali'], sebelum=old, sesudah=new, delta=delta,
                         awal=previous['month'], akhir=current['month']))
    return rows


def value_rata5(ticker):
    if not ticker or not ticker.isalnum():
        return None
    path = Path(DAILY_PATH) / 'Summary' / (ticker + '_Summary.csv')
    try:
        stat = path.stat()
        return _value_rata5(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, pd.errors.ParserError):
        return None


@lru_cache(maxsize=2048)
def _value_rata5(path, mtime, size):
    daily = pd.read_csv(path, usecols=['Date', 'Avg Price', 'Volume'])
    daily['Date'] = pd.to_datetime(daily['Date'], format='%d-%b-%y', errors='coerce')
    recent = (daily.dropna(subset=['Date']).sort_values('Date')
              .drop_duplicates('Date', keep='last').tail(5))
    if len(recent) < 5:
        return None
    price = pd.to_numeric(recent['Avg Price'], errors='coerce')
    volume = pd.to_numeric(recent['Volume'], errors='coerce')
    if not (np.isfinite(price) & np.isfinite(volume) & (price >= 0) & (volume >= 0)).all():
        return None
    return _angka((price * volume).mean() / 1e9)


def perubahan():
    months = ownership.load_ksei_months()
    ksei = []
    period = []
    if len(months) >= 2:
        old, new = months[-2:]
        period = [old['as_of'], new['as_of']]
        old_sec, new_sec = old['securities'], new['securities']
        for ticker in sorted(old_sec.keys() & new_sec.keys()):
            a, b = [ownership.build_month_metrics(x[ticker]) for x in (old_sec, new_sec)]
            if min(a['scripless'], b['scripless']) <= 0:
                continue
            ksei.append(dict(ticker=ticker, asing_awal=a['pct_foreign'], asing=b['pct_foreign'],
                             asing_delta=b['pct_foreign']-a['pct_foreign'],
                             asing_lembar_delta=b['foreign_total']-a['foreign_total'],
                             individu_awal=a['pct_retail'], individu=b['pct_retail'],
                             individu_delta=b['pct_retail']-a['pct_retail'],
                             modal_berubah=a['sec_num'] != b['sec_num']))
        ksei.sort(key=lambda row: abs(row['asing_delta']), reverse=True)

    tickers = {path.stem for path in Path(ownership.IDX_DIR).glob('*/*.json')}
    registry = []
    compared = 0
    for ticker in sorted(tickers):
        snapshots = [x for x in ownership.load_idx_registries(ticker) if x.get('holders')]
        if len(snapshots) >= 2:
            compared += 1
            registry.extend(banding_registri(ticker, *snapshots[-2:]))
    values = {ticker: value_rata5(ticker) for ticker in {row['ticker'] for row in ksei + registry}}
    for row in ksei + registry:
        row['value_rata5'] = values[row['ticker']]
    return dict(available=bool(ksei or compared), periode_ksei=period, ksei=ksei,
                registri=registry, n_registri=compared,
                message='KSEI membandingkan dua arsip bulanan terakhir. Persentase dihitung atas '
                        'saham elektronik. Registri IDX membandingkan dua snapshot terakhir tiap emiten. '
                        'Nama yang muncul atau hilang hanya menunjukkan perubahan keterlihatan di laporan. '
                        'Perbedaan jumlah saham dapat dipengaruhi aksi korporasi atau perubahan pelaporan. '
                        'Value rata-rata 5 hari (Rp miliar) = rata-rata Avg Price × Volume dari '
                        '5 sesi terakhir yang tersedia di Summary lokal; bukan periode bulanan KSEI. '
                        'Tanda - berarti data tidak lengkap.')
