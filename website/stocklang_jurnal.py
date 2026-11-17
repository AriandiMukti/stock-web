"""
Jurnal maju untuk skrip StockLang yang disimpan dengan centang "jurnal harian".

Tiap hari bursa (lewat kesehatan.py, sesudah Summary harian masuk) setiap
skrip itu dijalankan sekali dan saham yang lolos screen()-nya dicatat
dengan tanggal data terakhir. Yang dicatat cuma HARI INI -- tidak ada
pengisian mundur, karena mengisi mundur sama dengan backtest in-sample
lagi. Hari yang terlewat tidak bisa dikejar.

Penilaian (evaluasi) dihitung ulang tiap dibaca dari data harga:
masuk di OPEN hari bursa sesudah tanggal sinyal (sama seperti backtester
StockLang), keluar di CLOSE hari ke-1/5/20 sejak masuk, dipotong fee
0,4% pulang-pergi. Pembandingnya rata-rata semua saham di jendela yang
sama (masuk open & keluar close di tanggal yang sama), tanpa fee.

Sinyal yang dicatat SETELAH pasar buka di hari masuknya ditandai telat
dan tidak ikut dihitung: hasilnya sudah sebagian kelihatan saat dicatat.

    python -m website.stocklang_jurnal          # catat hari ini
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

try:
    from . import stocklang_web as web
    from .stocklang import data
except ImportError:
    import stocklang_web as web
    from stocklang import data

HERE = os.path.dirname(os.path.abspath(__file__))
JURNAL_FILE = str(_runtime_file('', 'stocklang_jurnal.csv'))        # satu baris per saham yang lolos
HARI_FILE = str(_runtime_file('', 'stocklang_jurnal_hari.csv'))     # satu baris per skrip per hari, termasuk hari kosong
KOLOM_JURNAL = ['tanggal', 'skrip', 'versi', 'kode', 'dicatat', 'nilai']
KOLOM_HARI = ['tanggal', 'skrip', 'versi', 'jumlah', 'status', 'dicatat']
HORIZON = (1, 5, 20)
FEE = 0.0015 + 0.0025
JAM_BUKA = 9                       # sesi I BEI buka 09:00 WIB


def _baca(path, kolom):
    if not os.path.exists(path):
        return pd.DataFrame(columns=kolom)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _tambah(path, kolom, rows):
    if not rows:
        return
    df = pd.DataFrame(rows, columns=kolom)
    df.to_csv(path, mode='a', header=not os.path.exists(path), index=False, encoding='utf-8')


def catat():
    """
    Jalankan semua skrip berjurnal sekali, catat hasil screen() hari data
    terakhir. Aman dipanggil berkali-kali: (tanggal, skrip, versi) yang
    sudah ada tidak dicatat dua kali. Kembalikan ringkasan per skrip.
    """
    sudah = _baca(HARI_FILE, KOLOM_HARI)
    sudah = set(zip(sudah['tanggal'], sudah['skrip'], sudah['versi']))
    ringkas, baris_jurnal, baris_hari = [], [], []
    for s in web.daftar_skrip():
        if not s['jurnal']:
            continue
        isi = web.muat_skrip(s['nama'])
        if isi is None:
            continue
        sekarang = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        hasil = web.jalankan(isi['src'])
        layar = hasil.get('screen')
        if hasil.get('error') or not layar:
            status = ('error: ' + hasil['error']['text'].splitlines()[0]) if hasil.get('error') else 'tanpa screen()'
            ringkas.append({'skrip': s['nama'], 'status': status})
            continue
        kunci = (layar['tanggal'], s['nama'], isi['versi'])
        if kunci in sudah:
            ringkas.append({'skrip': s['nama'], 'status': 'sudah dicatat', 'tanggal': layar['tanggal'],
                            'jumlah': len(layar['hits'])})
            continue
        sudah.add(kunci)
        for h in layar['hits']:
            baris_jurnal.append([layar['tanggal'], s['nama'], isi['versi'], h['kode'], sekarang,
                                 json.dumps(h['nilai'], ensure_ascii=False)])
        baris_hari.append([layar['tanggal'], s['nama'], isi['versi'], len(layar['hits']), 'ok', sekarang])
        ringkas.append({'skrip': s['nama'], 'status': 'dicatat', 'tanggal': layar['tanggal'],
                        'jumlah': len(layar['hits'])})
    _tambah(JURNAL_FILE, KOLOM_JURNAL, baris_jurnal)
    _tambah(HARI_FILE, KOLOM_HARI, baris_hari)
    return ringkas


def _harga():
    """Open & close semua saham, baris = tanggal bursa, kolom = kode."""
    syms = data.all_symbols()
    frames = dict(zip(syms, data.load_many(syms)))
    frames = {k: v for k, v in frames.items() if v is not None}
    opens = pd.DataFrame({k: v['open'] for k, v in frames.items()})
    closes = pd.DataFrame({k: v['close'] for k, v in frames.items()})
    opens = opens.where(opens.notna(), closes)
    return opens.sort_index(), closes.sort_index()


def evaluasi():
    """
    Ringkasan per (skrip, versi): jumlah hari & sinyal, lalu per horizon
    berapa yang sudah matang, rata-rata/median return bersih fee, win
    rate, dan selisih rata-rata terhadap semua saham di jendela yang sama.
    """
    j = _baca(JURNAL_FILE, KOLOM_JURNAL)
    h = _baca(HARI_FILE, KOLOM_HARI)
    aktif = {s['nama']: s for s in web.daftar_skrip()}
    if h.empty:
        return {'skrip': [], 'data_sampai': None}

    opens, closes = _harga()
    kal = closes.index
    hasil = []
    for (skrip, ver), hari in h.groupby(['skrip', 'versi'], sort=False):
        sinyal = j[(j['skrip'] == skrip) & (j['versi'] == ver)]
        per_h = {k: {'ret': [], 'lebih': []} for k in HORIZON}
        telat = 0
        for _, row in sinyal.iterrows():
            d = pd.Timestamp(row['tanggal'])
            pos = int(kal.searchsorted(d, side='right'))         # hari bursa pertama SESUDAH sinyal
            if pos >= len(kal):
                continue                                        # belum ada hari masuk
            masuk = kal[pos]
            if pd.Timestamp(row['dicatat']) >= masuk + pd.Timedelta(hours=JAM_BUKA):
                telat += 1
                continue
            kode = row['kode']
            if kode not in closes.columns:
                continue
            o = opens.at[masuk, kode]
            if not o or np.isnan(o):
                continue
            for k in HORIZON:
                if pos + k - 1 >= len(kal):
                    continue
                keluar = kal[pos + k - 1]
                c = closes.at[keluar, kode]
                if np.isnan(c):
                    continue
                kotor = c / o - 1
                pasar = float(np.nanmean(closes.loc[keluar].to_numpy() / opens.loc[masuk].to_numpy() - 1))
                per_h[k]['ret'].append(kotor - FEE)
                per_h[k]['lebih'].append(kotor - pasar)

        horizon = {}
        for k in HORIZON:
            r = np.array(per_h[k]['ret'])
            horizon[k] = {
                'matang': int(len(r)),
                'rata': float(r.mean() * 100) if len(r) else None,
                'median': float(np.median(r) * 100) if len(r) else None,
                'win': float((r > 0).mean() * 100) if len(r) else None,
                'lebih': float(np.mean(per_h[k]['lebih']) * 100) if len(r) else None,
            }
        terakhir = hari['tanggal'].max()
        kode_terakhir = sinyal[sinyal['tanggal'] == terakhir]['kode'].tolist()
        hasil.append({
            'skrip': skrip, 'versi': ver,
            'status': ('aktif' if skrip in aktif and aktif[skrip]['versi'] == ver and aktif[skrip]['jurnal']
                       else 'dihapus' if skrip not in aktif
                       else 'versi lama' if aktif[skrip]['versi'] != ver else 'jurnal dimatikan'),
            'hari': int(len(hari)), 'sinyal': int(len(sinyal)), 'telat': telat,
            'mulai': hari['tanggal'].min(), 'terakhir': terakhir, 'kode_terakhir': kode_terakhir,
            'horizon': {str(k): v for k, v in horizon.items()},
        })
    urut = {'aktif': 0, 'jurnal dimatikan': 1, 'versi lama': 2, 'dihapus': 3}
    hasil.sort(key=lambda x: (urut[x['status']], x['skrip']))
    return {'skrip': hasil, 'data_sampai': str(kal[-1])[:10] if len(kal) else None}


if __name__ == '__main__':
    for r in catat():
        print(r)
