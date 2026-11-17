"""
Buku order twin: LELANG BATCH (frequent batch auction).

KENAPA BATCH, BUKAN CONTINUOUS
BEI di jam perdagangan memang continuous (prioritas harga lalu waktu).
Tapi mencocokkan order satu per satu untuk ribuan agen x ratusan hari x
belasan run Monte Carlo berarti jutaan iterasi Python -- terlalu lambat
untuk dijalankan dari halaman web. Lelang batch mengumpulkan semua order
dalam satu irisan waktu lalu mengkliringnya di SATU harga, sehingga bisa
dihitung penuh dengan numpy.

Bedanya dengan continuous kecil untuk tujuan twin: harga tetap ditentukan
oleh ketidakseimbangan beli-jual terhadap kedalaman buku, order pasar
tetap "makan" antrean lawan, dan pra-pembukaan / pra-penutupan BEI memang
lelang dengan aturan yang sama persis (volume maksimum, lalu selisih
minimum, lalu terdekat dengan harga sebelumnya).

Yang hilang: urutan waktu DI DALAM satu irisan, jadi order besar yang
menyapu beberapa level membayar harga level terakhir untuk seluruhnya
(harga seragam), bukan rata-rata level-level yang disapu.

ALOKASI DETERMINISTIK
Di level marjinal (yang tidak bisa terisi penuh) isi dibagi pro-rata
dengan pembulatan sisa-terbesar, seri dipecah oleh urutan order. Sengaja
tanpa angka acak: baseline dan skenario dengan seed yang sama harus
menghasilkan dunia yang identik selama skenarionya belum berbuat apa-apa.
"""
import numpy as np


def _isi_marjinal(q, perlu):
    """Bagi `perlu` lot pro-rata ke order-order `q` (int64), sisa pembulatan
    ke pecahan terbesar. Hasilnya integer, sum == perlu, tiap isi <= q."""
    tot = int(q.sum())
    if perlu <= 0 or tot <= 0:
        return np.zeros_like(q)
    if perlu >= tot:
        return q.copy()
    kali = q * np.int64(perlu)
    dasar = kali // tot
    sisa_bagi = kali % tot
    kurang = int(perlu - dasar.sum())
    if kurang > 0:
        # pecahan terbesar dulu; seri -> indeks lebih kecil dulu (stabil)
        urut = np.argsort(-sisa_bagi, kind='stable')[:kurang]
        dasar[urut] += 1
    return dasar


def lelang(lvl_b, q_b, lvl_s, q_s, n_level, acuan):
    """
    Kliring satu irisan waktu untuk satu saham.

    lvl_b, lvl_s : indeks level harga limit (0 = ARB, n_level-1 = ARA)
    q_b, q_s     : jumlah lot (int64, > 0)
    acuan        : indeks level harga terakhir (pemecah seri)

    Return dict:
      idx    indeks level harga kliring, atau None kalau tidak ada transaksi
      vol    lot yang berpindah tangan
      isi_b, isi_s   lot terisi per order (urutan sama dengan input)
    """
    isi_b = np.zeros(len(q_b), dtype=np.int64)
    isi_s = np.zeros(len(q_s), dtype=np.int64)
    if len(q_b) == 0 or len(q_s) == 0:
        return {'idx': None, 'vol': 0, 'isi_b': isi_b, 'isi_s': isi_s}

    nb = np.bincount(lvl_b, weights=q_b, minlength=n_level)
    ns = np.bincount(lvl_s, weights=q_s, minlength=n_level)
    permintaan = nb[::-1].cumsum()[::-1]        # beli dengan limit >= harga
    penawaran = ns.cumsum()                     # jual dengan limit <= harga
    vol = np.minimum(permintaan, penawaran)
    vmax = vol.max()
    if vmax <= 0:
        return {'idx': None, 'vol': 0, 'isi_b': isi_b, 'isi_s': isi_s}

    calon = np.flatnonzero(vol == vmax)
    if len(calon) > 1:
        selisih = np.abs(permintaan[calon] - penawaran[calon])
        calon = calon[selisih == selisih.min()]
    if len(calon) > 1:
        calon = calon[np.abs(calon - acuan) == np.abs(calon - acuan).min()]
    p = int(calon[0])
    vmax = int(round(vmax))

    # Tiap sisi diisi menurut prioritas harga sampai `vmax`, dan dibagi
    # pro-rata di level MARJINAL-nya sendiri -- yang belum tentu sama dengan
    # level harga kliring p. Contoh yang dulu salah: tidak ada order sama
    # sekali di level p, penjual di bawah p berjumlah lebih dari vmax.
    # Menganggap "semua jual di bawah p terisi penuh" membuat saham lenyap.
    # Level marjinal beli m_b >= p dan jual m_s <= p selalu berlaku (karena
    # permintaan[p] >= vmax dan penawaran[p] >= vmax), jadi semua yang terisi
    # sah di harga p.

    # -- beli: level tertinggi dengan permintaan kumulatif >= vmax
    m_b = n_level - 1 - int(np.searchsorted(permintaan[::-1], vmax - 0.5))
    atas = lvl_b > m_b
    isi_b[atas] = q_b[atas]
    perlu = vmax - int(isi_b.sum())
    di_m = np.flatnonzero(lvl_b == m_b)
    if perlu > 0 and len(di_m):
        isi_b[di_m] = _isi_marjinal(q_b[di_m], perlu)

    # -- jual: level terendah dengan penawaran kumulatif >= vmax
    m_s = int(np.searchsorted(penawaran, vmax - 0.5))
    bawah = lvl_s < m_s
    isi_s[bawah] = q_s[bawah]
    perlu = vmax - int(isi_s.sum())
    di_m = np.flatnonzero(lvl_s == m_s)
    if perlu > 0 and len(di_m):
        isi_s[di_m] = _isi_marjinal(q_s[di_m], perlu)

    return {'idx': p, 'vol': vmax, 'isi_b': isi_b, 'isi_s': isi_s}


def sisa_buku(lvl_b, q_b, isi_b, lvl_s, q_s, isi_s, n_level):
    """Antrean yang tersisa setelah kliring, dijumlah per level:
    (bid[n_level], offer[n_level]) dalam lot."""
    bid = np.bincount(lvl_b, weights=(q_b - isi_b), minlength=n_level)
    offer = np.bincount(lvl_s, weights=(q_s - isi_s), minlength=n_level)
    return bid, offer
