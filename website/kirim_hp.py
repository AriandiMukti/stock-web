r"""
Kirim data olahan (dan APK-nya) ke aplikasi Android "BDM Saku" lewat WiFi
-- tanpa internet, cukup laptop dan HP di jaringan WiFi yang sama.

Ini BUKAN server Flask. Yang dilayani cuma dua file: hasil ekspor_hp.py
(wajib kode pasangan) dan BDM-Saku.apk (tanpa kode -- APK tidak berisi data,
dan browser HP tidak bisa mengirim header kode untuk pemasangan pertama).
Jadi aman dinyalakan di WiFi tanpa membuka halaman web/login ke jaringan.

Dua cara menyalakan:
  - tombol Sync di topbar web (mulai_dari_web) -- ekspor jalan di proses
    terpisah, server siaga SIAGA_MENIT lalu mati sendiri;
  - jendela konsol:
        python -X utf8 -m website.kirim_hp                (ekspor dulu, lalu siaga)
        python -X utf8 -m website.kirim_hp --tanpa-ekspor (kirim file yang ada)

Cara HP menemukan laptop: HP menyiarkan "BDM-CARI" (UDP 8766) ke seluruh
jaringan, laptop menjawab dengan port-nya. Kalau router memblok siaran
(AP isolation), alamat IP yang ditampilkan bisa diketik manual di HP.
"""
import json
import os
import random
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .ekspor_hp import FILE_DATA, FOLDER_HP

PORT_HTTP = 8765
PORT_CARI = 8766
FOLDER_HP_ROOT = os.path.dirname(FOLDER_HP)
FILE_KODE = os.path.join(FOLDER_HP_ROOT, 'kode.txt')
FILE_APK = os.path.join(FOLDER_HP_ROOT, 'BDM-Saku.apk')
FILE_APK_VERSI = os.path.join(FOLDER_HP_ROOT, 'BDM-Saku.versi')   # ditulis build_apk.ps1
NAMA_APK = 'BDM-Saku.apk'
FILE_TAHAN_APK = os.path.join(FOLDER_HP_ROOT, 'apk-ditahan.txt')
PESAN_TAHAN_APK = 'Pengiriman APK dijeda sementara karena peringatan Play Protect. Sync data tetap tersedia.'

# Mode web: server mati sendiri kalau tidak ada yang mengunduh selama ini.
SIAGA_MENIT = 15

# Kode 6 angka cuma sejuta kemungkinan -- di WiFi bersama (kost, kantor)
# orang lain bisa menebaknya beruntun. Alamat yang salah kode sebanyak ini
# diblok sampai server dimatikan.
MAKS_SALAH = 5


def kode_pasangan():
    """Kode 6 angka, dibuat sekali lalu disimpan -- HP cukup memasukkannya
    sekali saat pertama sinkron."""
    if os.path.exists(FILE_KODE):
        kode = open(FILE_KODE, encoding='utf-8').read().strip()
        if kode:
            return kode
    kode = '%06d' % random.SystemRandom().randint(0, 999999)
    os.makedirs(os.path.dirname(FILE_KODE), exist_ok=True)
    with open(FILE_KODE, 'w', encoding='utf-8') as f:
        f.write(kode)
    return kode


def _versi_apk():
    try:
        return int(open(FILE_APK_VERSI, encoding='utf-8').read().strip())
    except (OSError, ValueError):
        return None


def _apk_tersedia():
    return not os.path.exists(FILE_TAHAN_APK) and os.path.isfile(FILE_APK)


def _info():
    if not os.path.exists(FILE_DATA):
        return None
    st = os.stat(FILE_DATA)
    info = {
        'laptop': socket.gethostname(),
        'ukuran': st.st_size,
        'diubah': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M'),
    }
    versi = _versi_apk() if _apk_tersedia() else None
    if versi:
        info['apk_versi'] = versi
    return info


def _ip_lokal():
    """IP antarmuka yang dipakai ke jaringan sungguhan (WiFi). Sengaja tidak
    mendaftar semua antarmuka: adaptor virtual (VirtualBox 192.168.56.1)
    ikut muncul dan tidak bisa dicapai HP. Caranya "menyambungkan" soket UDP
    ke luar -- tidak ada paket yang benar-benar dikirim."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return [ip]
    except OSError:
        return []


def _jam():
    return datetime.now().strftime('%H:%M:%S')


# ---------------------------------------------------------------- status bersama

_kunci = threading.RLock()
_status = {'tahap': 'mati', 'pesan': '', 'log': [], 'terkirim': []}
_server = None
_udp = None
_pengawas = None


def _log(teks):
    print(teks, flush=True)
    with _kunci:
        _status['log'] = (_status['log'] + [teks.strip()])[-40:]


def _catat_kirim(ip, jenis, ukuran):
    _log('  [%s] %s terkirim ke %s (%.1f MB)' % (_jam(), jenis, ip, ukuran / 1e6))
    with _kunci:
        _status['terkirim'].append({'jam': _jam(), 'ip': ip, 'jenis': jenis})
        # Ada yang mengunduh = masih dipakai: siaga diperpanjang.
        if _status.get('siaga_sampai'):
            _status['siaga_sampai'] = time.time() + SIAGA_MENIT * 60


# ---------------------------------------------------------------- server

class _Penjawab(BaseHTTPRequestHandler):
    kode = ''
    salah = {}

    def log_message(self, fmt, *args):
        pass

    def _kirim_json(self, status, obj):
        b = json.dumps(obj).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _kirim_file(self, path, jenis_konten, nama_unduh=None):
        with open(path, 'rb') as f:
            b = f.read()
        self.send_response(200)
        self.send_header('Content-Type', jenis_konten)
        self.send_header('Content-Length', str(len(b)))
        if nama_unduh:
            self.send_header('Content-Disposition', 'attachment; filename="%s"' % nama_unduh)
        self.end_headers()
        self.wfile.write(b)
        return len(b)

    def do_GET(self):
        ip = self.client_address[0]
        jalur = self.path.split('?')[0]

        # APK untuk browser HP (pemasangan pertama): tanpa kode, tidak ada data di dalamnya.
        if jalur == '/' + NAMA_APK:
            if os.path.exists(FILE_TAHAN_APK):
                return self._kirim_json(404, {'galat': PESAN_TAHAN_APK})
            if not _apk_tersedia():
                return self._kirim_json(404, {'galat': 'APK belum di-build'})
            n = self._kirim_file(FILE_APK, 'application/vnd.android.package-archive', NAMA_APK)
            return _catat_kirim(ip, 'APK (browser)', n)

        if self.salah.get(ip, 0) >= MAKS_SALAH:
            return self._kirim_json(403, {'galat': 'diblok'})
        if self.headers.get('X-BDM-Kode', '') != self.kode:
            self.salah[ip] = self.salah.get(ip, 0) + 1
            _log('  [%s] ditolak: kode salah dari %s (%d/%d)%s' % (
                _jam(), ip, self.salah[ip], MAKS_SALAH, ' -- DIBLOK' if self.salah[ip] >= MAKS_SALAH else ''))
            return self._kirim_json(403, {'galat': 'kode salah'})

        info = _info()
        if not info:
            return self._kirim_json(404, {'galat': 'belum ada ekspor'})
        if jalur == '/info':
            return self._kirim_json(200, info)
        if jalur == '/data':
            return _catat_kirim(ip, 'Data', self._kirim_file(FILE_DATA, 'application/gzip'))
        if jalur == '/apk' and _apk_tersedia():
            return _catat_kirim(ip, 'APK (pembaruan)', self._kirim_file(FILE_APK, 'application/vnd.android.package-archive'))
        self._kirim_json(404, {'galat': 'tidak ada'})


def _layani_cari(s):
    while True:
        try:
            pesan, asal = s.recvfrom(64)
        except OSError:
            if s.fileno() == -1:
                return          # soket ditutup: server dimatikan
            continue            # Windows: ICMP "port unreachable" dari jawaban sebelumnya
        if pesan.strip() == b'BDM-CARI':
            try:
                s.sendto(('BDM-ADA %d %s' % (PORT_HTTP, socket.gethostname())).encode('utf-8'), asal)
            except OSError:
                pass


def nyalakan():
    """Nyalakan server HTTP + penjawab UDP (kalau belum). OSError kalau port
    sudah dipakai -- biasanya jendela KIRIM_KE_HP masih terbuka."""
    global _server, _udp
    with _kunci:
        if _server:
            return
        _Penjawab.kode = kode_pasangan()
        _Penjawab.salah = {}
        server = ThreadingHTTPServer(('0.0.0.0', PORT_HTTP), _Penjawab)
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(('', PORT_CARI))
        _server, _udp = server, udp
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=_layani_cari, args=(udp,), daemon=True).start()


def matikan():
    global _server, _udp
    with _kunci:
        server, udp, _server, _udp = _server, _udp, None, None
    if server:
        server.shutdown()
        server.server_close()
    if udp:
        udp.close()


# ---------------------------------------------------------------- mode web (tombol Sync)

def _ringkas_status():
    with _kunci:
        s = dict(_status)
        s['log'] = list(_status['log'])
        s['terkirim'] = list(_status['terkirim'])
    if s.get('siaga_sampai'):
        s['sisa_detik'] = max(0, int(s['siaga_sampai'] - time.time()))
    s['apk_ada'] = _apk_tersedia()
    s['port'] = PORT_HTTP
    s['nama_apk'] = NAMA_APK
    return s


def status():
    return _ringkas_status()


def mulai_dari_web(tanpa_ekspor=False):
    """Mulai ekspor + siaga di thread latar. Kalau sudah berjalan, status
    yang ada dikembalikan apa adanya (klik Sync dua kali tidak mengekspor dua kali)."""
    with _kunci:
        if _status['tahap'] == 'ekspor' or (_status['tahap'] == 'siap' and tanpa_ekspor):
            return _ringkas_status()
        _status.update(tahap='ekspor', pesan='Mengekspor data terbaru…', log=[], terkirim=[],
                       mulai=_jam(), siaga_sampai=None, kode=None, alamat=[], data=None)
    threading.Thread(target=_kerja_web, args=(tanpa_ekspor,), daemon=True).start()
    return _ringkas_status()


def berhenti():
    matikan()
    with _kunci:
        _status.update(tahap='mati', pesan='Server dimatikan.', siaga_sampai=None)
    return _ringkas_status()


def _siapkan_apk(cetak=print):
    """Build otomatis hanya jika sumber aplikasi berubah dan distribusi dibuka."""
    if os.path.exists(FILE_TAHAN_APK):
        cetak(PESAN_TAHAN_APK)
        return
    from pathlib import Path
    import hashlib
    root = Path(FOLDER_HP_ROOT) / 'android'
    sources = [root / 'AndroidManifest.xml', root / 'build_apk.ps1']
    for folder in ('assets', 'src', 'res'):
        sources.extend(p for p in (root / folder).rglob('*') if p.is_file())
    digest = hashlib.sha256()
    for path in sorted(sources):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    signature = digest.hexdigest()
    stamp = root / 'build-source.sha256'
    if Path(FILE_APK).exists() and stamp.exists() and stamp.read_text() == signature:
        return
    cetak('Menyiapkan pembaruan aplikasi Android…')
    run = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                          '-File', str(root / 'build_apk.ps1')],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding='utf-8', errors='replace',
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=300)
    if run.returncode:
        cetak(run.stdout[-4000:])
        raise RuntimeError('Pembaruan Android gagal dibuat. Periksa log Sync dan instalasi Android SDK/JDK.')
    stamp.write_text(signature)
    cetak('Pembaruan Android siap; ketuk Pasang di HP setelah Sinkron.')


def _kerja_web(tanpa_ekspor):
    global _pengawas
    try:
        _siapkan_apk(_log)
        if not tanpa_ekspor:
            # Proses terpisah, bukan memanggil ekspor() di sini: ekspor memakai
            # test client dengan CSRF dimatikan, dan itu tidak boleh menyentuh
            # aplikasi Flask yang sedang melayani browser.
            p = subprocess.Popen(
                [sys.executable, '-X', 'utf8', '-u', '-m', 'website.ekspor_hp'],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            for baris in p.stdout:
                if baris.startswith('  ') or baris.startswith('Selesai'):
                    _log(baris.rstrip())
            if p.wait() != 0:
                raise RuntimeError('Ekspor gagal (kode %s). Lihat log di bawah.' % p.returncode)
        elif not os.path.exists(FILE_DATA):
            raise RuntimeError('Belum ada file ekspor.')

        try:
            nyalakan()
        except OSError:
            raise RuntimeError('Port %d sudah dipakai -- tutup jendela KIRIM_KE_HP kalau masih terbuka.' % PORT_HTTP)

        with _kunci:
            _status.update(tahap='siap', pesan='Siap — buka BDM Saku di HP lalu ketuk Sinkron.',
                           kode=_Penjawab.kode, alamat=_ip_lokal(), data=_info(),
                           siaga_sampai=time.time() + SIAGA_MENIT * 60)
        if not _pengawas or not _pengawas.is_alive():
            _pengawas = threading.Thread(target=_awasi_siaga, daemon=True)
            _pengawas.start()
    except Exception as exc:
        with _kunci:
            _status.update(tahap='galat', pesan=str(exc))


def _awasi_siaga():
    while True:
        time.sleep(5)
        with _kunci:
            if _status['tahap'] != 'siap':
                return
            habis = _status.get('siaga_sampai') and time.time() > _status['siaga_sampai']
        if habis:
            matikan()
            with _kunci:
                _status.update(tahap='mati', siaga_sampai=None,
                               pesan='Server dimatikan otomatis setelah %d menit tanpa unduhan.' % SIAGA_MENIT)
            return


# ---------------------------------------------------------------- mode konsol

def main(argv):
    _siapkan_apk()
    if '--tanpa-ekspor' not in argv:
        print('Mengekspor data terbaru...')
        from .ekspor_hp import ekspor
        ekspor()
    elif not os.path.exists(FILE_DATA):
        print('Belum ada file ekspor -- jalankan tanpa --tanpa-ekspor dulu.')
        return 1

    nyalakan()
    info = _info()
    ip = (_ip_lokal() or ['-'])[0]
    print()
    print('=' * 52)
    print(' BDM Saku siap disinkron lewat WiFi')
    print('   Data       : %s (%.1f MB)' % (info['diubah'], info['ukuran'] / 1e6))
    print('   Kode       : %s' % _Penjawab.kode)
    print('   Alamat     : %s' % ip)
    if _apk_tersedia():
        print('   Pasang APK : http://%s:%d/%s (buka di browser HP)' % (ip, PORT_HTTP, NAMA_APK))
    print(' Di HP: buka BDM Saku -> Sinkron. Tutup jendela ini kalau sudah.')
    print('=' * 52)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
