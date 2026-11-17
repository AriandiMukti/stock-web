"""
Audit kebalikan: apa yang DILEWATKAN screener, bukan apa yang ditandainya.

KENAPA INI ADA
Semua evaluasi screener di app ini bertanya "dari yang ditandai, berapa
yang benar?" (presisi). Tidak ada satu pun yang bertanya "dari semua
kenaikan besar yang benar-benar terjadi, berapa yang tertangkap?" (recall).
Dua pertanyaan itu bisa berjawab sangat berbeda: screener yang cuma
menandai 3 saham setahun bisa saja presisinya 100% sambil melewatkan 97%
peluang.

Modul ini mengambil semua rally besar yang SUDAH terjadi, lalu memutar
ulang kriteria Kering Screener (bdm_screener_v2.saring) pada hari-hari
SEBELUM rally itu mulai, dan menghitung:

  1. Recall  -- berapa persen rally besar yang sempat ditandai lebih dulu.
  2. Terdakwa -- untuk yang terlewat, KRITERIA MANA yang paling sering
     menggagalkannya. Ini yang membuat hasilnya bisa ditindaklanjuti:
     kalau ternyata 90% kandidat mati di satu kriteria, kriteria itulah
     yang perlu ditinjau, bukan seluruh screener.

BEDA DENGAN big_winner_scan.py / top_winners_scan.py
Dua script itu juga mencari rally besar, tapi mereka MENGKARAKTERISASI
kondisi sebelum rally (volume, net top5, ritel) untuk mencari pola baru.
Modul ini tidak mencari pola baru -- ia menguji screener yang sudah
dipakai app ini terhadap kenyataan.

BATASNYA
- Data harian app ini hanya ~8 bulan (Jan-Sep 2026), jadi jumlah rally
  besar terbatas dan jendela lihat-ke-belakang sebelum tiap rally pendek.
  Recall di sini indikatif, bukan angka final.
- "Rally" didefinisikan murni dari harga. Sebagian di antaranya adalah
  saham gorengan yang memang tidak ingin ditangkap screener akumulasi --
  itu bukan kegagalan screener, jadi kolom likuiditas ikut ditampilkan
  supaya bisa dibedakan sendiri.
- Kriteria diputar ulang memakai data yang ada SEKARANG. Kalau file
  Summary pernah direvisi ke belakang, hasilnya ikut berubah.
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

from .kering_screener import SUMMARY_DIR, _import_v2

# Auditnya ~21 detik untuk 875 emiten (baca + skor + saring ulang semuanya),
# jadi selalu lewat cache. Datanya harian, TTL 6 jam sudah cukup.
CACHE_FILE = str(_runtime_file('', 'signal_recall_cache.pkl'))
def _sumber_terbaru():
    """Hanya berkas Summary -- modul ini tidak membaca sumber lain."""
    from .kesegaran import summary_terbaru
    return summary_terbaru()

C = {
    'RALLY_PCT': 30.0,     # kenaikan minimal supaya dihitung "rally besar"
    'RALLY_WINDOW': 20,    # dalam berapa hari bursa kenaikan itu tercapai
    'LEAD_DAYS': 20,       # jendela sebelum rally tempat sinyal dicari
    'COOLDOWN': 20,        # lompati sekian hari setelah satu rally terdeteksi
}

KRITERIA_LABEL = {
    'akumulasi_kuat': 'Skor akumulasi < 0,75',
    'naik_cukup': 'Belum naik 5% dalam 5 hari',
    'belum_meledak': 'Sudah naik > 20%',
    'tanpa_lonjakan': 'Ada lonjakan harian > 15%',
    'likuid': 'Di luar rentang likuiditas',
}

# Tidak semua "terlewat" berarti screener gagal, dan menyamakan semuanya
# membuat daftarnya jadi tumpukan mentah yang tidak bisa dibaca. Diukur
# dari data: 66% rally yang terlewat justru punya skor akumulasi NEGATIF --
# artinya saham itu sedang terukur DISTRIBUSI saat rally-nya dimulai, jadi
# memang di luar tesis screener, bukan kegagalannya. Yang benar-benar layak
# ditinjau cuma yang skornya sudah mendekati/melewati ambang.
SEBAB_LABEL = {
    'nyaris': 'Nyaris kena',
    'lemah': 'Akumulasi lemah',
    'di_luar_tesis': 'Di luar tesis (justru distribusi)',
    'tanpa_data': 'Riwayat terlalu pendek',
}

SEBAB_PENJELASAN = {
    'nyaris': 'Skor akumulasi sudah >= 0,60 -- screener nyaris menangkapnya. '
              'Inilah yang sungguh mengukur "peluang yang hilang".',
    'lemah': 'Skor 0,30-0,60. Ada jejak akumulasi tapi tipis; melonggarkan '
             'ambang sampai ke sini akan menambah tangkapan sekaligus banyak sampah.',
    'di_luar_tesis': 'Skor di bawah 0,30 (sebagian besar negatif -- justru terukur '
                     'distribusi). Rally-nya tidak didahului akumulasi yang bisa diukur, '
                     'jadi ini bukan kegagalan screener melainkan batas pendekatannya.',
    'tanpa_data': 'Riwayat harganya terlalu pendek untuk dihitung skornya saat itu.',
}

SEBAB_VERDICT = {
    'nyaris': 'merah',       # paling menyakitkan: benar-benar peluang hilang
    'lemah': 'kuning',
    'di_luar_tesis': 'netral',
    'tanpa_data': 'netral',
}


def _sebab(skor, gagal):
    """Kenapa satu rally terlewat -- dipisah supaya daftarnya bisa dibaca."""
    if skor is None:
        return 'tanpa_data'
    if skor >= 0.60:
        return 'nyaris'
    if skor >= 0.30:
        return 'lemah'
    return 'di_luar_tesis'


def _find_rallies(close):
    """Titik awal rally: harga naik >= RALLY_PCT dalam <= RALLY_WINDOW hari."""
    n = len(close)
    vals = close.values.astype(float)
    out = []
    i = C['LEAD_DAYS']
    while i < n - 1:
        base = vals[i]
        if not np.isfinite(base) or base <= 0:
            i += 1
            continue
        hi = np.nanmax(vals[i + 1:i + 1 + C['RALLY_WINDOW']]) if i + 1 < n else np.nan
        if np.isfinite(hi) and (hi - base) / base * 100.0 >= C['RALLY_PCT']:
            out.append((i, (hi - base) / base * 100.0))
            i += C['COOLDOWN']
        else:
            i += 1
    return out


def audit(force=False):
    """
    Putar ulang kriteria Kering Screener terhadap semua rally besar.

    Mengembalikan dict siap-render: ringkasan recall, tabel terdakwa
    (kriteria yang paling sering menggagalkan), dan daftar rally terlewat
    terbesar.
    """
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'rb') as fh:
                cached = pickle.load(fh)
            if cached.get('ts', 0) >= _sumber_terbaru():
                result = dict(cached['result'])
                result['from_cache'] = True
                return result
        except Exception:
            pass

    v2, _sk = _import_v2()
    frames, _buang = v2.baca_v2(SUMMARY_DIR)

    n_rally = 0
    n_caught = 0
    blame = {k: 0 for k in KRITERIA_LABEL}
    blame_sole = {k: 0 for k in KRITERIA_LABEL}   # satu-satunya kriteria yang gagal
    missed = []
    caught = []

    for ticker, g in frames.items():
        try:
            m = v2.metrik(g)
            mask, kriteria = v2.saring(m)
        except Exception:
            continue
        if 'close' not in m.columns:
            continue

        close = m['close']
        mask_vals = mask.fillna(False).values
        for idx, gain in _find_rallies(close):
            lo = max(0, idx - C['LEAD_DAYS'])
            n_rally += 1
            window_flagged = bool(mask_vals[lo:idx].any())

            date = m.index[idx]
            row = {
                'stock': ticker,
                'date': str(getattr(date, 'date', lambda: date)()),
                'gain_pct': round(float(gain), 1),
                'close': round(float(close.iloc[idx]), 2) if np.isfinite(close.iloc[idx]) else None,
                'adv_juta': (round(float(m['adv'].iloc[idx]) / 1e6, 1)
                             if 'adv' in m.columns and np.isfinite(m['adv'].iloc[idx]) else None),
                'skor': (round(float(m['skor'].iloc[idx]), 3)
                         if 'skor' in m.columns and np.isfinite(m['skor'].iloc[idx]) else None),
                'naik_pct': (round(float(m['naik'].iloc[idx]) * 100, 1)
                             if 'naik' in m.columns and np.isfinite(m['naik'].iloc[idx]) else None),
            }

            if window_flagged:
                n_caught += 1
                caught.append(row)
                continue

            # Terlewat -- cari kriteria mana yang tidak pernah terpenuhi
            # sepanjang jendela sebelum rally.
            gagal = []
            for name, series in kriteria.items():
                if name not in blame:
                    continue
                vals = series.fillna(False).values[lo:idx]
                if not vals.any():
                    gagal.append(name)
                    blame[name] += 1
            if len(gagal) == 1:
                blame_sole[gagal[0]] += 1
            row['gagal'] = gagal
            row['gagal_label'] = [KRITERIA_LABEL[g_] for g_ in gagal]
            sebab = _sebab(row['skor'], gagal)
            row['sebab'] = sebab
            row['sebab_label'] = SEBAB_LABEL[sebab]
            row['sebab_verdict'] = SEBAB_VERDICT[sebab]
            # Ditandai terpisah: tersaring likuiditas itu keputusan desain
            # yang disengaja, bukan kegagalan menangkap pola.
            row['disaring_likuiditas'] = 'likuid' in gagal
            missed.append(row)

    missed.sort(key=lambda r: -r['gain_pct'])
    caught.sort(key=lambda r: -r['gain_pct'])

    recall = (n_caught / n_rally * 100.0) if n_rally else 0.0
    blame_rows = []
    for name, label in KRITERIA_LABEL.items():
        blame_rows.append({
            'kriteria': name,
            'label': label,
            'menggagalkan': blame[name],
            'pct': round(blame[name] / len(missed) * 100.0, 1) if missed else 0.0,
            'sendirian': blame_sole[name],
        })
    blame_rows.sort(key=lambda r: -r['menggagalkan'])

    # Ringkasan sebab -- ini yang mengubah daftar terlewat dari tumpukan
    # mentah jadi indikator: berapa yang benar-benar peluang hilang, dan
    # berapa yang sebenarnya di luar jangkauan tesis screener.
    sebab_counts = {}
    for r in missed:
        sebab_counts[r['sebab']] = sebab_counts.get(r['sebab'], 0) + 1
    sebab_rows = []
    for key in ('nyaris', 'lemah', 'di_luar_tesis', 'tanpa_data'):
        n = sebab_counts.get(key, 0)
        sebab_rows.append({
            'sebab': key,
            'label': SEBAB_LABEL[key],
            'penjelasan': SEBAB_PENJELASAN[key],
            'verdict': SEBAB_VERDICT[key],
            'n': n,
            'pct': round(n / len(missed) * 100.0, 1) if missed else 0.0,
        })

    n_nyaris = sebab_counts.get('nyaris', 0)
    # Recall "yang adil": rally di luar tesis tidak dihitung sebagai
    # kegagalan, karena screener ini memang tidak dirancang menangkapnya.
    n_dalam_tesis = n_rally - sebab_counts.get('di_luar_tesis', 0) - sebab_counts.get('tanpa_data', 0)
    recall_tesis = (n_caught / n_dalam_tesis * 100.0) if n_dalam_tesis > 0 else 0.0

    result = {
        'available': True,
        'n_emiten': len(frames),
        'n_rally': n_rally,
        'n_caught': n_caught,
        'n_missed': len(missed),
        'recall': round(recall, 1),
        'n_nyaris': n_nyaris,
        'n_dalam_tesis': n_dalam_tesis,
        'recall_tesis': round(recall_tesis, 1),
        'sebab': sebab_rows,
        'blame': blame_rows,
        'missed': missed,
        'caught': caught,
        'config': dict(C),
        'as_of': time.strftime('%Y-%m-%d %H:%M'),
        'from_cache': False,
    }

    try:
        with open(CACHE_FILE, 'wb') as fh:
            pickle.dump({'ts': time.time(), 'result': result}, fh)
    except Exception:
        pass

    return result
