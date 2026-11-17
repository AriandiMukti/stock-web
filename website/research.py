"""
Kerangka riset: menjalankan eksperimen berat di latar belakang, dengan log
langsung, status berjalan, dan riwayat hasil yang tersimpan.

KENAPA INI TERPISAH DARI POLA MODUL LAIN
Semua halaman lain di app ini memakai pola yang sama: satu endpoint POST
memanggil satu fungsi, fungsi itu selesai dalam ~20-60 detik, hasilnya
disimpan di satu file cache pickle. Pola itu tidak muat untuk riset:

  1. Latihan RL memakan MENIT sampai PULUHAN MENIT, bukan detik. Request
     HTTP akan timeout jauh sebelum selesai.
  2. Yang ingin dilihat justru PROSESNYA (reward naik/tidak, fold mana yang
     rugi), bukan cuma hasil akhir. Cache pickle tidak punya konsep "log".
  3. Hasilnya perlu DIBANDINGKAN antar-run (seed lain, biaya lain, universe
     lain), jadi tiap run harus tersimpan sendiri-sendiri, bukan saling
     menimpa satu file cache.

Maka modul ini menaruh pekerjaan di thread latar belakang (server sudah
threaded=True, lihat .claude/launch.json), menampung barisan log di memori
untuk di-poll halaman, dan menulis hasil akhir ke research_runs/<id>.json.

SATU RUN DALAM SATU WAKTU
Sengaja. Latihannya CPU-bound; dua run bersamaan hanya membuat keduanya
lambat dan membuat halaman lain (yang berbagi proses Flask yang sama) ikut
tersendat. Permintaan kedua ditolak dengan pesan jelas, bukan diantre
diam-diam.

CATATAN RELOADER
Dengan debug=True + reloader Werkzeug, proses child restart saat file .py
berubah -- run yang sedang jalan IKUT MATI karena threadnya daemon. Ini
disengaja (alternatifnya thread zombie yang menulis file setelah kodenya
berubah). Run yang mati begitu terlihat sebagai 'berjalan' yang tidak
pernah maju dan tidak punya file hasil.
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import json
import os
import threading
import time
import traceback
import uuid

RUNS_DIR = str(_runtime_file('', 'research_runs'))
MAX_LOG_LINES = 4000       # log dipangkas supaya run panjang tidak memakan RAM
MAX_HISTORY = 100          # jumlah file hasil yang disimpan di disk (semua halaman)

_lock = threading.Lock()
_runs = {}                 # run_id -> dict (state hidup, termasuk baris log)


# --------------------------------------------------------------------------
# Registry eksperimen
# --------------------------------------------------------------------------
# Diisi lewat register() oleh modul eksperimen (rl_trading.py). Halaman
# Research membangun formulirnya dari sini, jadi menambah eksperimen baru
# tidak perlu menyentuh template atau endpoint sama sekali.
REGISTRY = {}
_dimuat = False

# `halaman` = halaman mana yang merender hasil eksperimen itu. Halaman
# Research hanya tahu cara menggambar hasil RL; Market Digital Twin punya
# halaman sendiri (/digital-twin) tapi memakai mesin latar belakang yang
# sama -- termasuk aturan satu-run-dalam-satu-waktu, karena keduanya
# berebut CPU yang sama.
HALAMAN_BAWAAN = 'research'


def register(key, label, ringkas, runner, fields, defaults, halaman=HALAMAN_BAWAAN):
    REGISTRY[key] = {
        'key': key,
        'label': label,
        'ringkas': ringkas,
        'runner': runner,
        'fields': fields,
        'defaults': defaults,
        'halaman': halaman,
    }


def _load_experiments():
    """Impor modul eksperimen sekali (mereka memanggil register() saat diimpor).

    Pakai bendera, bukan `if REGISTRY`: twin bisa sudah terdaftar duluan
    (diimpor halaman /digital-twin) dan RL belum -- dulu itu membuat halaman
    Research kehilangan eksperimennya tanpa galat."""
    global _dimuat
    if _dimuat:
        return
    _dimuat = True
    from . import rl_trading  # noqa: F401  -- efek sampingnya register()
    try:
        from .twin import jalan  # noqa: F401
    except Exception:
        traceback.print_exc()


def halaman_dari_key(key):
    e = REGISTRY.get(key)
    return e['halaman'] if e else HALAMAN_BAWAAN


def daftar_eksperimen(halaman=HALAMAN_BAWAAN):
    _load_experiments()
    return [{
        'key': e['key'], 'label': e['label'], 'ringkas': e['ringkas'],
        'fields': e['fields'], 'defaults': e['defaults'],
    } for e in REGISTRY.values() if e['halaman'] == halaman]


# --------------------------------------------------------------------------
# Kanal log yang dipakai eksperimen
# --------------------------------------------------------------------------
class Kanal:
    """
    Satu-satunya cara eksperimen berbicara dengan halaman: log(), tahap(),
    maju(), dan berhenti().

    Sengaja objek kecil, bukan logging biasa: eksperimen harus bisa ditulis
    tanpa tahu apa pun soal Flask, thread, atau JSON -- ia cuma memanggil
    kanal.log('...') dan mengecek kanal.berhenti() sesekali.
    """

    def __init__(self, run_id):
        self.run_id = run_id
        self._t0 = time.time()

    def log(self, pesan, level='info'):
        stamp = time.time() - self._t0
        baris = {'t': round(stamp, 1), 'pesan': str(pesan), 'level': level}
        with _lock:
            run = _runs.get(self.run_id)
            if run is None:
                return
            run['log'].append(baris)
            if len(run['log']) > MAX_LOG_LINES:
                # Buang bagian TENGAH, bukan awal: baris pertama berisi
                # konfigurasi run (yang selalu ingin dilihat lagi) dan baris
                # terakhir berisi kemajuan terkini.
                run['log'] = (run['log'][:200]
                              + [{'t': stamp, 'pesan': '... (log dipangkas) ...',
                                  'level': 'dim'}]
                              + run['log'][-(MAX_LOG_LINES - 400):])

    def tahap(self, nama):
        with _lock:
            run = _runs.get(self.run_id)
            if run is not None:
                run['tahap'] = nama
        self.log('== %s ==' % nama, 'tahap')

    def maju(self, frac):
        with _lock:
            run = _runs.get(self.run_id)
            if run is not None:
                run['progress'] = max(0.0, min(1.0, float(frac)))

    def berhenti(self):
        """True kalau user menekan Hentikan. Eksperimen WAJIB mengeceknya di
        dalam loop panjangnya, kalau tidak tombolnya tidak berefek."""
        with _lock:
            run = _runs.get(self.run_id)
            return bool(run and run.get('minta_berhenti'))


# --------------------------------------------------------------------------
# Siklus hidup run
# --------------------------------------------------------------------------
def mulai(key, config):
    _load_experiments()
    if key not in REGISTRY:
        raise ValueError('Eksperimen tidak dikenal: %s' % key)

    with _lock:
        for r in _runs.values():
            if r['status'] == 'berjalan':
                raise RuntimeError(
                    'Masih ada riset berjalan (%s, mulai %s). Tunggu selesai '
                    'atau hentikan dulu.' % (r['label'], r['mulai_str']))

    exp = REGISTRY[key]
    run_id = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:4]
    run = {
        'id': run_id,
        'key': key,
        'label': exp['label'],
        'config': config,
        'status': 'berjalan',
        'tahap': 'Menyiapkan',
        'progress': 0.0,
        'mulai': time.time(),
        'mulai_str': time.strftime('%d %b %Y %H:%M'),
        'selesai': None,
        'durasi': None,
        'log': [],
        'hasil': None,
        'error': None,
        'minta_berhenti': False,
    }
    with _lock:
        _runs[run_id] = run

    kanal = Kanal(run_id)
    t = threading.Thread(target=_jalankan, args=(run_id, exp, config, kanal),
                         name='research-%s' % run_id, daemon=True)
    t.start()
    return run_id


def _jalankan(run_id, exp, config, kanal):
    kanal.log('Riset "%s" dimulai.' % exp['label'])
    kanal.log('Konfigurasi: %s' % json.dumps(config, ensure_ascii=False))
    try:
        hasil = exp['runner'](config, kanal)
        status = 'dihentikan' if kanal.berhenti() else 'selesai'
        with _lock:
            run = _runs.get(run_id)
            if run is not None:
                run['status'] = status
                run['hasil'] = hasil
                if status == 'selesai':
                    run['progress'] = 1.0
                run['selesai'] = time.time()
                run['durasi'] = run['selesai'] - run['mulai']
                run['tahap'] = 'Selesai' if status == 'selesai' else 'Dihentikan'
        kanal.log('Selesai dalam %.1f detik.' % (time.time() - kanal._t0), 'ok')
        _simpan(run_id)
    except Exception as exc:
        jejak = traceback.format_exc()
        with _lock:
            run = _runs.get(run_id)
            if run is not None:
                run['status'] = 'gagal'
                run['error'] = '%s: %s' % (type(exc).__name__, exc)
                run['selesai'] = time.time()
                run['durasi'] = run['selesai'] - run['mulai']
                run['tahap'] = 'Gagal'
        kanal.log('GAGAL: %s' % exc, 'error')
        for baris in jejak.strip().splitlines()[-12:]:
            kanal.log(baris, 'dim')
        _simpan(run_id)


def hentikan(run_id):
    with _lock:
        run = _runs.get(run_id)
        if run is None or run['status'] != 'berjalan':
            return False
        run['minta_berhenti'] = True
        run['tahap'] = 'Menghentikan (menunggu iterasi berjalan selesai)'
    return True


def poll(run_id, sejak=0):
    """Status + baris log baru sejak indeks `sejak`. Dipanggil tiap ~1,5 detik
    oleh halaman, jadi sengaja hanya mengirim selisihnya."""
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            tersimpan = _baca(run_id)
            if tersimpan:
                tersimpan['baris_baru'] = tersimpan.get('log', [])[int(sejak or 0):]
                tersimpan['total_baris'] = len(tersimpan.get('log', []))
                return tersimpan
            return None
        sejak = max(0, int(sejak))
        return {
            'id': run['id'], 'key': run['key'], 'label': run['label'],
            'status': run['status'], 'tahap': run['tahap'],
            'progress': run['progress'], 'config': run['config'],
            'mulai_str': run['mulai_str'],
            'durasi': run['durasi'] if run['durasi'] else time.time() - run['mulai'],
            'error': run['error'], 'hasil': run['hasil'],
            'baris_baru': run['log'][sejak:], 'total_baris': len(run['log']),
        }


def run_aktif(halaman=None):
    """Run yang sedang berjalan; kalau `halaman` diisi, hanya yang milik
    halaman itu (halaman lain tidak boleh menyambung ke run yang tidak bisa
    ia gambar)."""
    _load_experiments()
    with _lock:
        for r in _runs.values():
            if r['status'] == 'berjalan' and (halaman is None or halaman_dari_key(r['key']) == halaman):
                return r['id']
    return None


# --------------------------------------------------------------------------
# Penyimpanan hasil
# --------------------------------------------------------------------------
def _path(run_id):
    return str(_runtime_file('research_runs', '%s.json' % run_id))


def _simpan(run_id):
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            return
        salinan = {k: v for k, v in run.items() if k != 'minta_berhenti'}
    try:
        os.makedirs(RUNS_DIR, exist_ok=True)
        with open(_path(run_id), 'w', encoding='utf-8') as f:
            json.dump(salinan, f, ensure_ascii=False, default=str)
    except Exception:
        pass
    _pangkas_riwayat()


def _baca(run_id):
    try:
        with open(_path(run_id), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _pangkas_riwayat():
    try:
        berkas = sorted(
            (f for f in os.listdir(RUNS_DIR) if f.endswith('.json')),
            key=lambda f: os.path.getmtime(str(_runtime_file('research_runs', f))),
            reverse=True)
        for f in berkas[MAX_HISTORY:]:
            os.remove(str(_runtime_file('research_runs', f)))
    except Exception:
        pass


def riwayat(batas=40, halaman=None):
    """Ringkasan run yang pernah jalan -- yang masih di memori maupun yang
    sudah di disk. Yang di memori menang (statusnya lebih mutakhir).
    Kalau `halaman` diisi, hanya run milik halaman itu."""
    _load_experiments()
    keluar = {}
    try:
        berkas = sorted(
            (f for f in os.listdir(RUNS_DIR) if f.endswith('.json')),
            key=lambda f: os.path.getmtime(str(_runtime_file('research_runs', f))),
            reverse=True)
        for f in berkas:
            d = _baca(f[:-5])
            if d and (halaman is None or halaman_dari_key(d.get('key')) == halaman):
                keluar[d['id']] = _ringkas(d)
            if len(keluar) >= batas:
                break
    except Exception:
        pass
    with _lock:
        for r in _runs.values():
            if halaman is None or halaman_dari_key(r['key']) == halaman:
                keluar[r['id']] = _ringkas(r)
    return sorted(keluar.values(), key=lambda r: r['id'], reverse=True)[:batas]


def _ringkas(run):
    hasil = run.get('hasil') or {}
    return {
        'id': run['id'],
        'key': run.get('key'),
        'label': run.get('label'),
        'status': run.get('status'),
        'mulai_str': run.get('mulai_str'),
        'durasi': run.get('durasi'),
        'judul_config': hasil.get('judul_config') or _judul_config(run.get('config') or {}),
        'metrik': hasil.get('ringkas') or {},
    }


def _judul_config(config):
    bagian = []
    for k in ('universe', 'mulai_tahun', 'metode', 'seed'):
        if k in config:
            bagian.append('%s=%s' % (k, config[k]))
    return ' · '.join(bagian)


def ambil(run_id):
    with _lock:
        run = _runs.get(run_id)
        if run is not None:
            return {k: v for k, v in run.items() if k != 'minta_berhenti'}
    return _baca(run_id)
