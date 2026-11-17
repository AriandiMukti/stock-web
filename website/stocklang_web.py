"""
Menjalankan skrip StockLang dari halaman web (/stocklang).

Tiap run jalan di PROSES TERPISAH (file ini sendiri, dipanggil sebagai
skrip) supaya skrip yang berat atau berputar-putar bisa dibunuh betulan
saat lewat batas waktu -- thread di dalam proses Flask tidak bisa
dihentikan dari luar. Biaya start proses ~1 detik (impor pandas), data
Summary-nya sendiri dibaca dari cache stocklang/.cache/summary.pkl.

Grafik dari plot() ditulis ke folder sementara per run, lalu dikirim balik
sebagai PNG base64 dan foldernya dihapus. Argumen file= di skrip tetap
dihormati namanya, tapi selalu dipaksa masuk folder sementara itu supaya
skrip dari browser tidak bisa menulis ke sembarang tempat di server.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import base64
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES_DIR = os.path.join(HERE, 'stocklang', 'examples')

BATAS_DETIK = 60          # skrip yang lebih lama dari ini dibunuh
BATAS_BARIS = 5000        # keluaran lebih panjang dipotong
BATAS_SKRIP = 50_000      # karakter
_SLOT = threading.BoundedSemaphore(2)   # paling banyak 2 run bersamaan


def contoh():
    """[(nama, isi)] dari stocklang/examples/*.stk, golden_cross duluan."""
    out = []
    for path in sorted(glob.glob(os.path.join(EXAMPLES_DIR, '*.stk'))):
        with open(path, encoding='utf-8') as f:
            out.append((os.path.splitext(os.path.basename(path))[0], f.read()))
    out.sort(key=lambda x: x[0] != 'golden_cross')
    return out


# ---- skrip tersimpan ---------------------------------------------------------
# Satu berkas .stk per skrip di stocklang_skrip/, plus _daftar.json yang
# mencatat mana yang ikut jurnal maju harian (stocklang_jurnal.py).

SKRIP_DIR = str(_runtime_file('', 'stocklang_skrip'))
DAFTAR_FILE = str(_runtime_file('stocklang_skrip', '_daftar.json'))
_NAMA = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$')


def versi(src):
    """Sidik jari isi skrip: entri jurnal dari versi lama tidak dicampur dengan yang baru."""
    return hashlib.sha1(src.strip().replace('\r\n', '\n').encode('utf-8')).hexdigest()[:8]


def _muat_daftar():
    try:
        with open(DAFTAR_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _tulis_daftar(d):
    os.makedirs(SKRIP_DIR, exist_ok=True)
    tmp = DAFTAR_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, DAFTAR_FILE)


def daftar_skrip():
    """[{nama, jurnal, diubah, versi}] urut nama."""
    meta = _muat_daftar()
    out = []
    for path in sorted(glob.glob(os.path.join(SKRIP_DIR, '*.stk'))):
        nama = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding='utf-8') as f:
            src = f.read()
        m = meta.get(nama, {})
        out.append({'nama': nama, 'jurnal': bool(m.get('jurnal')), 'diubah': m.get('diubah'), 'versi': versi(src)})
    return out


def muat_skrip(nama):
    if not _NAMA.match(nama or ''):
        return None
    path = str(_runtime_file('stocklang_skrip', nama + '.stk'))
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        src = f.read()
    return {'nama': nama, 'src': src, 'jurnal': bool(_muat_daftar().get(nama, {}).get('jurnal')),
            'versi': versi(src)}


def punya_screen(src):
    """Skripnya memanggil screen()? (baris komentar diabaikan)"""
    tanpa_komentar = re.sub(r'(#|//).*', '', src)
    return re.search(r'\bscreen\s*\(', tanpa_komentar) is not None


def simpan_skrip(nama, src, jurnal=False):
    """Kembalikan (ok, pesan)."""
    if not _NAMA.match(nama or ''):
        return False, 'Nama 1-40 karakter: huruf, angka, - atau _ (tanpa spasi).'
    if len(src) > BATAS_SKRIP:
        return False, f'Skrip terlalu panjang (maks {BATAS_SKRIP:,} karakter).'
    if jurnal:
        try:
            from .stocklang import StockLangError, parse
        except ImportError:                 # diimpor sebagai modul lepas, bukan website.*
            from stocklang import StockLangError, parse
        try:
            parse(src)
        except StockLangError as e:
            return False, 'Skrip masih error, belum bisa masuk jurnal:\n' + e.render(src)
        if not punya_screen(src):
            return False, 'Jurnal harian butuh skrip yang memanggil screen() -- itu yang dicatat tiap hari.'
    os.makedirs(SKRIP_DIR, exist_ok=True)
    with open(str(_runtime_file('stocklang_skrip', nama + '.stk')), 'w', encoding='utf-8', newline='\n') as f:
        f.write(src.replace('\r\n', '\n'))
    meta = _muat_daftar()
    meta[nama] = {'jurnal': bool(jurnal), 'diubah': time.strftime('%Y-%m-%d %H:%M')}
    _tulis_daftar(meta)
    return True, 'Tersimpan' + (' dan masuk jurnal harian.' if jurnal else '.')


def hapus_skrip(nama):
    """Berkas skripnya dihapus; entri jurnalnya tetap (riwayat tidak ditulis ulang)."""
    if not _NAMA.match(nama or ''):
        return False
    path = str(_runtime_file('stocklang_skrip', nama + '.stk'))
    if not os.path.exists(path):
        return False
    os.remove(path)
    meta = _muat_daftar()
    meta.pop(nama, None)
    _tulis_daftar(meta)
    return True


def jalankan(src):
    """Jalankan satu skrip, kembalikan dict siap-JSON untuk halaman."""
    if len(src) > BATAS_SKRIP:
        return {'output': [], 'images': [], 'error': {
            'text': f"error: script too long ({len(src):,} characters, max {BATAS_SKRIP:,})"}}
    if not _SLOT.acquire(blocking=False):
        return {'output': [], 'images': [], 'error': {
            'text': 'Server sedang menjalankan skrip lain. Coba lagi sebentar.'}}
    folder = tempfile.mkdtemp(prefix='stocklang_web_')
    t0 = time.perf_counter()
    try:
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        try:
            p = subprocess.run([sys.executable, '-X', 'utf8', os.path.abspath(__file__), folder],
                               input=src.encode('utf-8'), capture_output=True,
                               timeout=BATAS_DETIK, cwd=folder, creationflags=flags)
        except subprocess.TimeoutExpired:
            return {'output': [], 'images': [], 'elapsed': round(time.perf_counter() - t0, 2),
                    'error': {'text': f"error: script stopped after {BATAS_DETIK} seconds (time limit)"}}
        try:
            hasil = json.loads(p.stdout.decode('utf-8'))
        except ValueError:
            pesan = p.stderr.decode('utf-8', 'replace').strip().splitlines()
            return {'output': [], 'images': [], 'error': {
                'text': 'internal error: ' + (pesan[-1] if pesan else f'worker exited with code {p.returncode}')}}
        hasil['elapsed'] = round(time.perf_counter() - t0, 2)
        return hasil
    finally:
        _SLOT.release()
        shutil.rmtree(folder, ignore_errors=True)


# ---- tulis skrip dari bahasa biasa (Claude) ----------------------------------
# Permintaan bebas -> skrip StockLang, lewat twin/llm.py (model, fallback,
# penanganan galat yang sama dengan Digital Twin). Skripnya langsung dicoba
# jalan; kalau error, pesan errornya dikirim balik untuk diperbaiki. Tiap
# percobaan = satu panggilan Claude yang berbayar.

BATAS_PERMINTAAN = 2000
MAKS_PERCOBAAN = 3

SKEMA_TULIS = {
    'type': 'object',
    'properties': {
        'skrip': {'type': 'string', 'description': 'Skrip StockLang lengkap, siap dijalankan.'},
        'penjelasan': {'type': 'string', 'description': 'Dua-tiga kalimat: apa yang dihitung skrip ini.'},
        'asumsi': {'type': 'array', 'items': {'type': 'string'},
                   'description': 'Hal yang terpaksa ditebak karena permintaannya tidak menyebutkan.'},
    },
    'required': ['skrip', 'penjelasan', 'asumsi'],
    'additionalProperties': False,
}


def _system_tulis():
    try:
        from .stocklang import Interpreter, data
    except ImportError:
        from stocklang import Interpreter, data
    with open(os.path.join(HERE, 'stocklang', 'README.md'), encoding='utf-8') as f:
        readme = f.read()
    bantuan = []
    Interpreter(out=bantuan.append).cmd_help(None, [], {})
    try:
        with open(os.path.join(data.SUMMARY_DIR, 'BBCA_Summary.csv'), encoding='utf-8') as f:
            f.readline()
            mulai = f.readline().split(',')[0]
        rentang = f'Data harian dimulai {mulai}, jadi hanya sekitar satu tahun berjalan.'
    except OSError:
        rentang = 'Riwayat datanya pendek (sekitar satu tahun berjalan).'
    return (
        'Kamu menulis skrip StockLang, bahasa kecil untuk analisis saham BEI (IDX). Ini dokumentasinya:\n\n'
        + readme + '\n\nDaftar lengkap dari help():\n' + bantuan[0] + '\n\n'
        'Aturan:\n'
        '- Tulis HANYA StockLang yang ada di dokumentasi; jangan mengarang kolom, fungsi, atau opsi.\n'
        '- "Cari/saham apa hari ini" -> universe all + screen(). "Apakah X berhasil / apa yang terjadi '
        'sesudah X" -> study(). Strategi beli-jual -> backtest(), pakai split= supaya ada uji luar sampel. '
        'Kalau permintaannya menyebut satu kode saham, pakai stock KODE.\n'
        f'- {rentang} Jangan pakai jendela indikator lebih dari ~60 bar.\n'
        '- plot() hanya untuk satu saham, dan cuma kalau diminta.\n'
        '- Beri komentar # singkat dalam bahasa permintaannya. Penjelasan dan asumsi dalam bahasa Indonesia.\n'
        '- Ini alat riset, bukan saran investasi: jangan menjanjikan hasil.'
    )


def tulis(permintaan):
    """Permintaan bebas -> {'skrip','penjelasan','asumsi','percobaan', + hasil jalankan()} atau {'galat'}."""
    try:
        from .twin.llm import GalatLLM, panggil_json
    except ImportError:
        from twin.llm import GalatLLM, panggil_json
    teks = (permintaan or '').strip()
    if not teks:
        return {'galat': 'Tulis dulu apa yang mau dicari.'}
    if len(teks) > BATAS_PERMINTAAN:
        return {'galat': f'Permintaan terlalu panjang (maks {BATAS_PERMINTAAN:,} karakter).'}
    system = _system_tulis()
    pengguna = f'Permintaan:\n"""{teks}"""'
    hasil = run = None
    for percobaan in range(1, MAKS_PERCOBAAN + 1):
        try:
            hasil = panggil_json(system, pengguna, SKEMA_TULIS, effort='medium', max_tokens=8000)
        except GalatLLM as exc:
            return {'galat': str(exc)}
        run = jalankan(hasil['skrip'])
        if not run.get('error'):
            break
        pengguna = (f'Permintaan:\n"""{teks}"""\n\nSkrip ini gagal:\n```\n{hasil["skrip"]}\n```\n'
                    f'Errornya:\n{run["error"]["text"]}\n\nPerbaiki skripnya.')
    return dict(run, skrip=hasil['skrip'], penjelasan=hasil['penjelasan'], asumsi=hasil['asumsi'],
                percobaan=percobaan)


# ---- sisi pekerja (proses anak) ---------------------------------------------

def _pekerja(folder):
    src = sys.stdin.buffer.read().decode('utf-8')
    # stdout milik JSON hasil; print() nyasar selama run dibelokkan ke stderr.
    stdout, sys.stdout = sys.stdout, sys.stderr
    lines, images = [], []
    terpotong = [False]

    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    asli = Figure.savefig

    def savefig_aman(self, fname, *a, **kw):
        nama = os.path.basename(str(fname)) or 'chart.png'
        if not nama.lower().endswith('.png'):
            nama += '.png'
        tujuan = os.path.join(folder, nama)
        kw.pop('format', None)
        asli(self, tujuan, *a, format='png', **kw)
        images.append(tujuan)

    Figure.savefig = savefig_aman

    def out(text=''):
        for baris in str(text).split('\n'):
            if len(lines) >= BATAS_BARIS:
                terpotong[0] = True
                return
            if baris.startswith('Chart saved: '):
                baris = 'Chart saved: ' + os.path.basename(baris[len('Chart saved: '):].strip())
            lines.append(baris)

    from stocklang import StockLangError, run_source
    error = None
    interp = None
    try:
        interp = run_source(src, filename='<script>', out=out, script_path=os.path.join(folder, 'script.stk'))
    except StockLangError as e:
        error = {'text': e.render(src), 'line': e.line, 'col': e.col}
    except RecursionError:
        error = {'text': 'error: too much recursion (a function calling itself without end?)'}
    except Exception as e:  # bug di interpreter, bukan di skrip
        error = {'text': f"internal error: {type(e).__name__}: {e}"}
    if terpotong[0]:
        lines.append(f"... (output cut at {BATAS_BARIS} lines)")

    gambar = []
    for path in dict.fromkeys(images):
        try:
            with open(path, 'rb') as f:
                gambar.append({'name': os.path.basename(path),
                               'data': base64.b64encode(f.read()).decode('ascii')})
        except OSError:
            pass
    stdout.write(json.dumps({'output': lines, 'images': gambar, 'error': error,
                             'screen': _hasil_screen(interp) if error is None else None}))


def _hasil_screen(interp):
    """
    Saham yang lolos screen() di hari data terakhir, untuk jurnal maju:
    {'tanggal': 'YYYY-MM-DD', 'hits': [{'kode', 'nilai'}]}, atau None kalau
    skripnya tidak memanggil screen() sama sekali.
    """
    def bersih(nilai):
        return {k: (v if isinstance(v, (bool, str)) or v is None or v == v else None)
                for k, v in nilai.items()}

    r = interp.results if interp is not None else None
    if r is not None and r.screened:
        return {'tanggal': str(r.latest)[:10],
                'hits': [{'kode': k, 'nilai': bersih(v)} for k, v in r.screens]}
    if interp is not None and interp.single_screens:
        tanggal = str(max(d for _, _, d, _ in interp.single_screens))[:10]
        return {'tanggal': tanggal,
                'hits': [{'kode': k, 'nilai': bersih(v)} for k, hit, d, v in interp.single_screens
                         if hit and str(d)[:10] == tanggal]}
    return None


if __name__ == '__main__':
    _pekerja(sys.argv[1])
