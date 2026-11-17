"""
Riset "pola apa yang paling mungkin membuat saham naik" (23 Sep 2026).

Asal pertanyaannya: "kalau harga sebuah saham tenang 30 hari, apakah ia lebih
mungkin naik?" Jawabannya TIDAK -- lihat tembus_basis.py untuk hasil lengkap
dan halaman /tembus-basis yang lahir dari riset ini.

DATA
- Harga: pickle Yahoo terbesar di research_cache (888 emiten, 2012 s.d.
  8 Sep 2026, auto-adjusted, dibuat rl_trading.py). IHSG dari berkas
  ihsg_2012-*.pkl di folder yang sama.
- Arus broker: New BDM\\Test (21 emiten, 2016-2026) dan Daily\\Summary (2026).

DESAIN UJI -- kenapa angkanya bisa dipercaya sejauh ini, dan tidak lebih
- Semesta likuid saja: median nilai 20 hari >= Rp1 M, harga >= Rp100,
  diperdagangkan >= 90% hari, riwayat >= 260 hari, tanpa loncatan >45%
  dalam 60 hari. Tanpa saringan ini "harga tenang" kebanyakan berarti tidak
  ada yang bertransaksi, atau harga yang tertahan di Rp50.
- Pencarian di separuh emiten (paritas md5 kodenya) 2013-2019; validasi di
  separuh LAIN 2020-2026. Dua sel silang ikut dilaporkan.
- Masuk di close hari SETELAH sinyal (Open Yahoo untuk BEI tidak bisa
  dipercaya: ~40% barisnya sama dengan close kemarin). Satu sinyal per
  emiten per 20 hari.
- Pembanding = emiten likuid lain yang dibeli PADA HARI YANG SAMA, dengan
  return majemuk (rata-rata log). Nilai t dikelompokkan per bulan.
- Semua pola yang dicoba dilaporkan, termasuk yang gagal.

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.uji pola          # ~33 pola x 4 sel
    python -m website.riset_pola_naik.uji ketahanan     # per tahun, likuiditas, rezim, angka absolut
    python -m website.riset_pola_naik.uji penajaman     # varian tembus basis (dipilih SESUDAH validasi)
    python -m website.riset_pola_naik.uji validasi      # tabel utama tembus_basis.BUKTI
    python -m website.riset_pola_naik.uji cek-setara    # tembus_basis.fitur() == rumus riset?
    python -m website.riset_pola_naik.cek_jatuh_dalam   # kenapa Jatuh Dalam "lolos" dulu
    python -m website.riset_pola_naik.arus urai         # urai JSON folder Test (~4,5 menit, sekali)
    python -m website.riset_pola_naik.arus uji          # arus broker menambah sesuatu?
    python -m website.riset_pola_naik.simulasi dasar    # portofolio 10 slot vs beli-semua & IHSG
    python -m website.riset_pola_naik.simulasi stres    # urutan slot acak, ongkos x2, tanpa trade terbaik
    python -m website.riset_pola_naik.keluar            # aturan keluar (trailing, cut loss) + filter IHSG
    python -m website.riset_pola_naik.keluar stres      # idem, 10 urutan pengisian slot acak
    python -m website.riset_pola_naik.kejar             # breakout yang hari itu sudah lari jauh: masih layak?
    python -m website.riset_pola_naik.analog            # chart mirip -> hasil mirip? (analog & klaster bentuk, ~45 dtk)
    python -m website.riset_pola_naik.skor              # Skor Kecondongan: dekat puncak + tenang (kecondongan.py)
    python -m website.riset_pola_naik.sumber_baru ksei  # arsip KSEI bulanan 2012-sekarang ke research_cache
    python -m website.riset_pola_naik.sumber_baru aksi  # dividen & split Yahoo ke research_cache
    python -m website.riset_pola_naik.event             # dividen, split, arus kepemilikan KSEI
    python -m website.riset_pola_naik.delisting         # lubang survivorship lewat harga bulanan KSEI

Panel fiturnya (~2,2 juta baris) dibangun ulang di memori tiap kali, ~20
detik -- sengaja tidak disimpan: sebagai pickle besarnya ~400 MB.

BATAS YANG TIDAK BISA DIPERBAIKI DARI SINI
- Yahoo hanya berisi emiten yang MASIH tercatat. Emiten delisting hilang
  beserta kerugiannya: semua angka agak terlalu optimistis, paling parah
  untuk pola kejatuhan.
- Varian yang dipilih sesudah melihat validasi (uji penajaman) bukti yang
  lebih lemah; jurnal maju tembus_basis.py yang mengujinya.
"""
