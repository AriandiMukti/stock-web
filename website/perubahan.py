"""
Apa Berubah Hari Ini: emiten mana yang MASUK dan KELUAR dari tiap layar,
dibanding hari bursa sebelumnya.

KENAPA MODUL INI ADA
Membaca app ini tiap pagi berarti membuka sembilan belas menu dan
mengingat sendiri isi kemarin. Sebagian besar isinya tidak berubah --
emiten yang kemarin ada di Jatuh Dalam kemungkinan besar masih di sana
hari ini. Yang benar-benar membawa informasi baru cuma selisihnya.

Modul ini tidak menghitung sinyal apa pun. Dia memanggil fungsi scan yang
SUDAH ADA di tiap modul, menyimpan daftar anggotanya per hari bursa, lalu
menyelisihkan hari terakhir terhadap hari sebelumnya.

KENAPA DICATAT KE DISK, BUKAN DIHITUNG ULANG
Keanggotaan kemarin tidak bisa direkonstruksi dari data hari ini untuk
sebagian layar: Kering Screener dan Scanner Lab memakai jendela bergulir
yang ikut bergeser, dan ambang di beberapa modul dihitung dari populasi
hari itu. Begitu ambangnya digeser atau modulnya diperbaiki, "kemarin"
versi hitung-ulang jadi beda dengan kemarin yang sesungguhnya
ditampilkan. Satu-satunya cara jujur adalah menuliskannya saat hari itu
berlangsung -- alasan yang sama dengan pola_jurnal.py.

BEDA DENGAN pola_jurnal.py
pola_jurnal mencatat KEADAAN tiap emiten (harga, arus, volume) supaya
pola apa pun bisa diuji belakangan tanpa terikat definisi keranjang hari
ini. Modul ini mencatat KEANGGOTAAN layar -- justru hal yang sengaja
TIDAK dicatat pola_jurnal, karena keanggotaan menua buruk sebagai bahan
uji. Untuk pertanyaan "apa yang berubah sejak kemarin" keanggotaan itulah
yang dibutuhkan, dan menuanya tidak masalah karena umurnya cuma sehari.

BATASNYA
- Baris pertama tiap layar tidak punya pembanding, jadi hari pertama
  setelah modul ini dipasang tidak menghasilkan selisih apa pun.
- Layar yang gagal dimuat dilewati DAN dilaporkan, tidak dicatat sebagai
  "kosong" -- kalau tidak, satu kegagalan sesaat akan terbaca sebagai
  "semua emiten keluar hari ini".
- Masuk/keluar bukan sinyal beli/jual. Emiten keluar dari Jatuh Dalam
  bisa berarti harganya pulih ATAU berhenti diperdagangkan.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import logging
import os
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

JURNAL = str(_runtime_file('', 'perubahan_jurnal.csv'))
KOLOM = ['tanggal', 'layar', 'stock']


def _tickers(hasil, kunci=('rows', 'baris')):
    """Ambil daftar kode dari hasil scan apa pun di app ini."""
    if not isinstance(hasil, dict) or not hasil.get('available', True):
        return None
    for k in kunci:
        baris = hasil.get(k)
        if isinstance(baris, list):
            out = {str(r.get('stock', '')).upper() for r in baris
                   if isinstance(r, dict) and r.get('stock')}
            return out or None
    return None


# Tiap entri dibungkus sendiri: satu layar yang gagal tidak boleh
# menjatuhkan seluruh rekaman. Konvensi yang sama dipakai stock_hub.py.
def _jatuh_dalam():
    from .jatuh_dalam import scan
    return _tickers(scan())


def _serapan_float():
    from .float_squeeze import scan
    return _tickers(scan())


def _akumulasi_palsu():
    from .fake_accumulation import scan
    return _tickers(scan())


def _risiko_peluang():
    """Kelompok peluang lonjakan tertinggi (kelipatan >= 2x)."""
    from .risiko import scan
    h = scan()
    baris = h.get('baris') or []
    return {r['stock'] for r in baris if (r.get('x_naik') or 0) >= 2.0} or None


def _risiko_tenang():
    """Kelompok paling tenang (kelipatan risiko <= 0,6x)."""
    from .risiko import scan
    h = scan()
    baris = h.get('baris') or []
    return {r['stock'] for r in baris if (r.get('x_rugi') or 9) <= 0.60} or None


def _emiten_hilang():
    from .survivorship import scan
    h = scan()
    return {r['stock'] for r in (h.get('hilang') or [])} or None


LAYAR = [
    ('Jatuh Dalam', _jatuh_dalam),
    ('Serapan Float', _serapan_float),
    ('Akumulasi Palsu', _akumulasi_palsu),
    ('Risiko: peluang tinggi', _risiko_peluang),
    ('Risiko: paling tenang', _risiko_tenang),
    ('Emiten Hilang', _emiten_hilang),
]


def _hari_bursa_terakhir():
    from .kesegaran import summary_terbaru  # noqa: F401  (menjaga urutan impor)
    from .survivorship import scan as surv
    try:
        h = surv()
        if h.get('terakhir_bursa'):
            return h['terakhir_bursa']
    except Exception:
        logger.exception('Gagal membaca hari bursa terakhir')
    return datetime.now().strftime('%Y-%m-%d')


def _baca():
    if not os.path.exists(JURNAL):
        return pd.DataFrame(columns=KOLOM)
    try:
        d = pd.read_csv(JURNAL, dtype=str)
        return d[KOLOM] if set(KOLOM) <= set(d.columns) else pd.DataFrame(columns=KOLOM)
    except Exception:
        logger.exception('Jurnal perubahan tidak terbaca')
        return pd.DataFrame(columns=KOLOM)


def rekam(force=False):
    """
    Catat keanggotaan tiap layar untuk hari bursa terakhir.

    Idempoten: kalau tanggal itu sudah tercatat, tidak menulis apa-apa
    kecuali force=True. Ini dipanggil kesehatan.py setelah cache lain
    dibangun, jadi bisa saja dijalankan beberapa kali sehari.
    """
    tanggal = _hari_bursa_terakhir()
    lama = _baca()
    sudah = set(lama[lama['tanggal'] == tanggal]['layar']) if len(lama) else set()

    baris, gagal = [], []
    for nama, fn in LAYAR:
        if nama in sudah and not force:
            continue
        try:
            kode = fn()
        except Exception as exc:
            logger.exception('Layar %s gagal saat merekam', nama)
            gagal.append({'layar': nama, 'sebab': str(exc)})
            continue
        if not kode:
            gagal.append({'layar': nama, 'sebab': 'kosong atau tidak tersedia'})
            continue
        for s in sorted(kode):
            baris.append({'tanggal': tanggal, 'layar': nama, 'stock': s})

    if baris:
        if force and len(lama):
            ditulis = {b['layar'] for b in baris}
            lama = lama[~((lama['tanggal'] == tanggal) & (lama['layar'].isin(ditulis)))]
        pd.concat([lama, pd.DataFrame(baris)], ignore_index=True).to_csv(JURNAL, index=False)

    return {'tanggal': tanggal, 'ditulis': len(baris),
            'layar': len({b['layar'] for b in baris}), 'gagal': gagal}


def selisih(rekam_dulu=True):
    """Masuk dan keluar per layar, hari bursa terakhir vs sebelumnya."""
    if rekam_dulu:
        try:
            rekam()
        except Exception:
            logger.exception('Gagal merekam sebelum menyelisihkan')

    d = _baca()
    if d.empty:
        return {'available': False,
                'message': 'Jurnal perubahan masih kosong. Butuh minimal dua hari bursa tercatat.'}

    tanggal = sorted(d['tanggal'].unique())
    if len(tanggal) < 2:
        return {'available': False, 'tanggal': tanggal[-1], 'hari_tercatat': len(tanggal),
                'message': ('Baru %d hari bursa tercatat (%s). Selisih baru bisa dihitung '
                            'setelah ada hari kedua.' % (len(tanggal), tanggal[-1]))}

    kini, lalu = tanggal[-1], tanggal[-2]
    out = []
    for nama, _ in LAYAR:
        a = set(d[(d['tanggal'] == lalu) & (d['layar'] == nama)]['stock'])
        b = set(d[(d['tanggal'] == kini) & (d['layar'] == nama)]['stock'])
        if not a and not b:
            continue
        # Layar yang kemarin tercatat tapi hari ini tidak sama sekali:
        # itu kegagalan pemuatan, bukan "semua keluar".
        if a and not b:
            out.append({'layar': nama, 'masuk': [], 'keluar': [], 'tetap': 0,
                        'kemarin': len(a), 'kini': 0, 'tidak_termuat': True})
            continue
        out.append({'layar': nama,
                    'masuk': sorted(b - a), 'keluar': sorted(a - b),
                    'tetap': len(a & b), 'kemarin': len(a), 'kini': len(b),
                    'tidak_termuat': False})

    return {
        'available': True,
        'kini': kini, 'lalu': lalu,
        'hari_tercatat': len(tanggal),
        'layar': out,
        'total_masuk': sum(len(x['masuk']) for x in out),
        'total_keluar': sum(len(x['keluar']) for x in out),
        'catatan': ('Masuk dan keluar bukan sinyal beli/jual. Emiten keluar dari sebuah layar '
                    'bisa berarti keadaannya membaik ATAU berhenti diperdagangkan -- '
                    'silangkan dengan Emiten Hilang sebelum menyimpulkan.'),
    }
