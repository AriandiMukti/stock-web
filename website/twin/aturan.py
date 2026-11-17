"""
Aturan perdagangan BEI yang dipakai mesin twin.

Semua angka di sini DIUKUR ULANG dari data, bukan disalin dari ingatan:

  ARA/ARB  -- distribusi return harian harga mentah (research_cache/
              harga_mentah_close.pkl) Mei 2025 s.d. Sep 2026, ~270 ribu
              hari-emiten. Penurunan menumpuk tepat di -14,5..-16% di SEMUA
              rentang harga (ARB 15% rata, berlaku sejak 8 Apr 2025 -- sama
              dengan ARB_JADWAL di riset_pola_naik/ta_lanjutan.py). Kenaikan
              menumpuk di +34..36% (harga <=200), +24..26% (200-5.000) dan
              +19..21% (>5.000). Yang lebih ekstrem dari itu hanya aksi
              korporasi (split/right issue), bukan perdagangan biasa.
  Fraksi   -- sama dengan _tick() di ta_lanjutan.py.

Kalau BEI mengubah aturan, cukup ubah konstanta di sini.
"""
import numpy as np

LOT = 100                  # lembar per lot
HARGA_MIN = 50             # papan utama/pengembangan: tidak bisa di bawah Rp50

# (batas atas EKSKLUSIF, fraksi): harga < 200 -> Rp1, < 500 -> Rp2, dst.
FRAKSI = ((200, 1), (500, 2), (2000, 5), (5000, 10), (float('inf'), 25))

# ARA menurut harga acuan (penutupan kemarin): <=200 35%, <=5.000 25%, >5.000 20%
ARA_TINGKAT = ((200, 0.35), (5000, 0.25), (float('inf'), 0.20))
ARB = 0.15

# Biaya transaksi tipikal (broker + pungutan bursa; jual termasuk PPh final 0,1%).
# Sama dengan riset_pola_naik/simulasi.py.
BIAYA_BELI = 0.0015
BIAYA_JUAL = 0.0025


def fraksi(harga):
    """Fraksi harga untuk skalar atau array."""
    h = np.asarray(harga, dtype=float)
    return np.select([h < 200, h < 500, h < 2000, h < 5000], [1, 2, 5, 10], 25)


def bulat_bawah(harga):
    """Harga sah terdekat yang <= harga."""
    h = float(harga)
    f = float(fraksi(h))
    return max(HARGA_MIN, np.floor(h / f + 1e-9) * f)


def bulat_atas(harga):
    """Harga sah terdekat yang >= harga."""
    h = float(harga)
    f = float(fraksi(h))
    hasil = np.ceil(h / f - 1e-9) * f
    # Membulatkan ke atas bisa menyeberang ke tingkat fraksi berikutnya
    # (mis. 4.995 -> 5.000 sah, 5.003 -> 5.025): ulangi dengan fraksi baru.
    f2 = float(fraksi(hasil))
    if f2 != f:
        hasil = np.ceil(h / f2 - 1e-9) * f2
    return max(HARGA_MIN, hasil)


def bulat_dekat(harga):
    """Harga sah terdekat (dipakai untuk harga awal dari data yang sudah
    disesuaikan Yahoo, yang bisa punya desimal)."""
    bawah, atas = bulat_bawah(harga), bulat_atas(harga)
    return bawah if (harga - bawah) <= (atas - harga) else atas


def persen_ara(acuan):
    for batas, pct in ARA_TINGKAT:
        if acuan <= batas:
            return pct
    return ARA_TINGKAT[-1][1]


def batas_harian(acuan):
    """(harga_terendah, harga_tertinggi) yang boleh terjadi hari ini, dari
    harga acuan (penutupan kemarin). Dibulatkan KE DALAM supaya tidak
    pernah melewati persentase batasnya."""
    atas = bulat_bawah(acuan * (1.0 + persen_ara(acuan)))
    bawah = bulat_atas(acuan * (1.0 - ARB))
    bawah = max(bawah, HARGA_MIN)
    atas = max(atas, bawah)
    return bawah, atas


def tangga(bawah, atas):
    """Semua harga sah dari `bawah` sampai `atas` (inklusif), menyeberangi
    tingkat fraksi kalau perlu. Inilah 'papan harga' satu saham satu hari."""
    harga = []
    h = float(bawah)
    atas = float(atas)
    while h <= atas + 1e-9:
        harga.append(h)
        h = h + float(fraksi(h))
    return np.array(harga, dtype=float)
