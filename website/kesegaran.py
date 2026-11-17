"""
Aturan kesegaran cache, dipakai bersama.

KENAPA MODUL INI ADA

App ini punya belasan cache mahal, dan hampir semuanya dulu memakai TTL
jam-jaman: 6 jam, 12 jam, 24 jam. Umur bukan ukuran yang benar untuk data
di sini. Datanya berubah SEKALI sehari -- saat unduhan pagi selesai -- dan
tidak berubah lagi sampai besok. TTL punya dua sisi yang sama-sama salah:

  terlalu pendek  cache yang dibangun RUN_KESEHATAN.bat pukul 20.24
                  kedaluwarsa pukul 02.24 atau 08.24, di tengah hari kerja
                  dan di luar jendela batch. Pengguna pertama sesudah itu
                  yang membayar pembangunan ulangnya. Terukur: Kepercayaan
                  Data 70 detik, Ringkasan Watchlist 59 detik, Halaman
                  Saham 57 detik.

  terlalu panjang cache tetap dianggap sah walau unduhan pagi sudah masuk,
                  jadi halaman menampilkan angka kemarin dengan tampilan
                  hari ini -- kegagalan yang paling sulit terlihat karena
                  tidak ada yang rusak dan tidak ada yang lambat.

Aturan yang benar tidak melihat jam dinding sama sekali: cache basi begitu
ada berkas SUMBER yang lebih baru daripada cache-nya. Kalau sumbernya tidak
berubah, cache tetap sah berapa pun umurnya; begitu unduhan pagi menyentuh
Summary, seluruh cache yang bergantung padanya basi seketika.

Pola ini pertama kali dipakai di live_scan.cached_scan(), lalu ditiru satu
per satu. Modul ini menyatukannya supaya tidak ada lima salinan logika
pemindaian mtime yang bisa saling menyimpang.

ONGKOS
Memindai direktori, bukan membaca isinya. ~0,02 detik untuk 881 berkas
Summary, ~0,03 detik untuk 939 berkas kepemilikan. Diabaikan dibanding
pembangunan ulang yang dicegahnya.

PEMAKAIAN
    from .kesegaran import summary_terbaru, kepemilikan_terbaru, paling_baru

    if cached.get('ts', 0) >= paling_baru(summary_terbaru(), berkas_terbaru(LEDGER)):
        return cached['result']
"""
import os

from .config import DAILY_PATH

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')


def summary_terbaru():
    """mtime paling baru di antara berkas *_Summary.csv."""
    terbaru = 0.0
    try:
        for nama in os.listdir(SUMMARY_DIR):
            if not nama.endswith('_Summary.csv'):
                continue
            try:
                m = os.path.getmtime(os.path.join(SUMMARY_DIR, nama))
            except OSError:
                continue
            if m > terbaru:
                terbaru = m
    except OSError:
        pass
    return terbaru


def kepemilikan_terbaru():
    """
    mtime paling baru di seluruh pohon kepemilikan: bulanan KSEI, registri
    IDX, LBRPE, dan overrides.json.

    Seluruh pohon, bukan satu berkas: carve-out ritel membaca ketiganya,
    dan menariknya satu emiten saja (tombol Sync) sudah cukup mengubah
    angka yang keluar.
    """
    terbaru = 0.0
    try:
        from .config import OWNERSHIP_PATH
        for akar, _dirs, berkas in os.walk(OWNERSHIP_PATH):
            for nama in berkas:
                try:
                    m = os.path.getmtime(os.path.join(akar, nama))
                except OSError:
                    continue
                if m > terbaru:
                    terbaru = m
    except Exception:
        pass
    return terbaru


def berkas_terbaru(*paths):
    """
    mtime paling baru di antara berkas yang disebut. Berkas yang tidak ada
    dilewati -- kalau SEMUANYA tidak ada hasilnya 0,0, artinya cache apa
    pun dianggap segar. Itu disengaja: induk yang belum pernah dibangun
    bukan alasan membangun ulang anaknya terus-menerus.
    """
    terbaru = 0.0
    for p in paths:
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if m > terbaru:
            terbaru = m
    return terbaru


def paling_baru(*nilai):
    """max() yang aman terhadap None."""
    bersih = [v for v in nilai if v]
    return max(bersih) if bersih else 0.0
