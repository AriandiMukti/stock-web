"""
Skenario = jadwal guncangan yang disuntikkan ke lingkungan twin.

Satu event:
    {'hari': 10, 'jenis': 'suku_bunga', 'target': 'semua', 'besar': 50, 'durasi': 20}

`hari` dihitung dari hari pertama yang direkam (sesudah masa pemanasan).
`target`: 'semua', 'sektor:<nama sektor IDX>', satu kode ('BBCA'), daftar
kode, atau penanda preset '@besar' (kapitalisasi terbesar di pilihan),
'@kecil' (terkecil), '@lapis' (terkecil yang bukan big cap).

SETIAP JENIS MENYENTUH APA
Guncangan tidak pernah langsung "menurunkan harga". Ia mengubah apa yang
DILIHAT agen -- nilai wajar, sentimen, selera risiko, pasokan -- lalu harga
terbentuk dari reaksi mereka di buku order. Itu inti twin: kalau BI rate
naik, siapa yang menjual, siapa yang menampung, dan berapa dalam harga
harus turun sampai keduanya bertemu.

Besaran penerjemahan (mis. "50 bp ~ faktor pasar -1,2%") adalah ASUMSI
yang ditulis terang di sini, bukan hasil estimasi. Ubah kalau punya acuan
lebih baik.
"""
import copy

import numpy as np

JENIS = {
    'sentimen': {
        'label': 'Sentimen / berita',
        'besar': 'skala -3..+3 (1 = berita kuat)',
        'arti': 'Mengubah sentimen saham target. Paling dirasakan ritel; institusi hampir tidak peduli.',
    },
    'nilai_wajar': {
        'label': 'Perubahan fundamental',
        'besar': 'proporsi, mis. 0,10 = nilai wajar +10%',
        'arti': 'Kejutan laba / kontrak / aset: nilai wajar bergeser permanen, plus riak sentimen.',
    },
    'suku_bunga': {
        'label': 'Suku bunga BI',
        'besar': 'basis poin, mis. 50 = naik 50 bp, -25 = turun',
        'arti': 'Faktor pasar -1,2% per +50 bp di hari pengumuman, selera risiko institusi lokal '
                'dan asing turun selama durasi, sentimen pasar ritel turun; properti -3% tambahan.',
    },
    'arus_asing': {
        'label': 'Arus asing',
        'besar': '-1 = keluar besar-besaran, +1 = masuk besar-besaran',
        'arti': 'Selera risiko asing digeser selama durasi. Target "semua": seluruh pasar, dan sisa '
                'pasar ikut tertekan/terangkat 0,2% per hari per satuan besar. Target saham/sektor: '
                'hanya selera asing di saham itu yang bergeser.',
    },
    'msci': {
        'label': 'Pengumuman MSCI',
        'besar': 'pola "asumsi": -1 = konsultasi reklasifikasi ke Frontier, -0,5 = bobot dipangkas, '
                 '+0,5 = status aman, +1 = bobot naik. Pola putar ulang: -1 = persis episode asli, '
                 '-1,5 = 50% lebih parah, positif = cerminnya (asumsi)',
        'arti': 'Hari pengumuman: faktor IHSG 3% x besar dan sentimen pasar bergeser. Selama durasi '
                '(isi sampai tanggal efektif): selera asing di saham target bergeser 1,5 x besar, di saham '
                'lain 0,3 x besar, sisa pasar 0,15%/hari x besar; di hari terakhir dorongannya dua kali '
                'lipat (dana pasif menyesuaikan di penutupan sebelum efektif). Target bawaan @msci = '
                'perkiraan anggota MSCI Standard. Pola "Putar ulang Jan/Jun 2026" memakai jalur IHSG '
                'dan arus asing per saham yang benar-benar terjadi di episode MSCI itu (10 hari, target '
                'dan durasi diabaikan).',
    },
    'rumor_akuisisi': {
        'label': 'Rumor akuisisi',
        'besar': '1 = rumor kuat (premi 15% sebagian dipercaya institusi)',
        'arti': 'Sentimen target melonjak, nilai wajar naik sebagian; kalau `bantah_hari` diisi, '
                'beberapa hari kemudian dibantah dan semuanya dibalik.',
    },
    'bandar_masuk': {
        'label': 'Bandar masuk',
        'besar': '1 = modal ~15x nilai transaksi harian saham itu',
        'arti': 'Satu bandar baru mulai fase akumulasi di saham target, lalu markup dan distribusi.',
    },
    'panik': {
        'label': 'Panik pasar',
        'besar': 'guncangan faktor IHSG hari itu, mis. -0,07',
        'arti': 'Faktor pasar anjlok, sentimen pasar & selera risiko asing jatuh, ritel jauh lebih '
                'mudah panik selama durasi.',
    },
    'pasokan': {
        'label': 'Pasokan baru (unlock / divestasi)',
        'besar': 'porsi saham beredar, mis. 0,05 = 5%',
        'arti': 'Pemegang lama yang terkunci mulai menjual bertahap selama durasi.',
    },
    'likuiditas': {
        'label': 'Likuiditas',
        'besar': 'pengali aktivitas, mis. 0,5 = sepi separuh',
        'arti': 'Aktivitas order & kedalaman antrean diskalakan selama durasi (libur panjang, '
                'window dressing, suspensi parsial).',
    },
    'guncangan_ihsg': {
        'label': 'Guncangan IHSG murni',
        'besar': 'return faktor IHSG hari itu, mis. -0,03',
        'arti': 'Hanya faktor pasar yang bergerak; reaksi lain dibiarkan muncul sendiri.',
    },
    'dividen': {
        'label': 'Dividen (cum / ex)',
        'besar': 'dividend yield, mis. 0,05 = 5% dari harga di hari pengumuman',
        'arti': 'Hari = pengumuman, durasi = jumlah hari sampai ex-date (ex = hari + durasi). Selama periode cum '
                'sentimen target naik 0,3 per 5% yield dan institusi lokal ikut berburu (selera +0,5 per 5%). '
                'Di ex-date nilai wajar turun sebesar dividen dan kas dibayar ke semua pemegang (asumsi: dibayar '
                'di ex-date). BEI tidak menyesuaikan harga otomatis, jadi gap ex-date terbentuk dari reaksi agen.',
    },
    'suspensi': {
        'label': 'Suspensi / UMA',
        'besar': 'diabaikan',
        'arti': 'Saham target tidak diperdagangkan selama durasi (BEI menghentikan perdagangan, mis. sesudah '
                'UMA). Nilai wajar tetap bergerak; di hari dibuka lagi seluruh perubahan selama suspensi masuk '
                'ke acuan pra-pembukaan, dibatasi ARA/ARB dari penutupan terakhir.',
    },
    'minat_lokal': {
        'label': 'Minat institusi lokal',
        'besar': '-1 = MI/dapen lokal keluar dari saham itu, +1 = masuk besar-besaran',
        'arti': 'Selera risiko institusi lokal di saham target digeser 1,5 x besar selama durasi -- pasangan '
                '"arus asing" per saham. Untuk rebalancing indeks lokal (LQ45/IDX30), window dressing, '
                'atau pemburu dividen.',
    },
}

PRESET = {
    'normal': {
        'kelompok': 'Makro',
        'judul': 'Kondisi normal (tanpa guncangan)',
        'deskripsi': 'Baseline melawan dirinya sendiri: selisihnya harus nol. Berguna untuk '
                     'melihat perilaku twin dan rapor realismenya.',
        'events': [],
    },
    'bi_rate_naik': {
        'kelompok': 'Makro',
        'judul': 'BI rate naik 50 bp mendadak',
        'deskripsi': 'Kenaikan tak terduga di hari ke-10. Siapa yang menjual duluan, siapa yang '
                     'menampung, dan berapa lama tekanannya bertahan.',
        'events': [{'hari': 10, 'jenis': 'suku_bunga', 'target': 'semua', 'besar': 50, 'durasi': 20}],
    },
    'asing_keluar': {
        'kelompok': 'Makro',
        'judul': 'Asing keluar besar-besaran 3 minggu',
        'deskripsi': 'Arus keluar asing selama 15 hari bursa (mis. rebalancing indeks global). '
                     'Big cap milik asing paling terpukul; lihat apakah ritel menampung.',
        'events': [{'hari': 10, 'jenis': 'arus_asing', 'target': 'semua', 'besar': -1.0, 'durasi': 15}],
    },
    'crash': {
        'kelompok': 'Makro',
        'judul': 'Crash ala April 2025',
        'deskripsi': 'Faktor IHSG -7% dalam sehari, tiga hari panik, lalu dibiarkan pulih sendiri.',
        'events': [{'hari': 10, 'jenis': 'panik', 'target': 'semua', 'besar': -0.07, 'durasi': 3}],
    },
    'bi_rate_turun': {
        'kelompok': 'Makro',
        'judul': 'BI rate turun 25 bp',
        'deskripsi': 'Pelonggaran di hari ke-10 (cermin "BI rate naik", setengah besarnya). Apakah kabar '
                     'baik makro langsung terserap, atau dicicil institusi selama berminggu-minggu.',
        'events': [{'hari': 10, 'jenis': 'suku_bunga', 'target': 'semua', 'besar': -25, 'durasi': 20}],
    },
    'fed_hawkish': {
        'kelompok': 'Makro',
        'judul': 'Fed hawkish: gap down pagi + asing jual seminggu',
        'deskripsi': 'Wall Street anjlok semalam: faktor IHSG -2% di hari ke-10, lalu asing menjual pelan '
                     '5 hari bursa. Pola harian yang paling sering: buka merah, siapa yang serok bawah.',
        'events': [{'hari': 10, 'jenis': 'guncangan_ihsg', 'target': 'semua', 'besar': -0.02},
                   {'hari': 10, 'jenis': 'arus_asing', 'target': 'semua', 'besar': -0.5, 'durasi': 5}],
    },
    'rupiah_melemah': {
        'kelompok': 'Makro',
        'judul': 'Rupiah melemah tajam',
        'deskripsi': 'Asing keluar 2 minggu; nilai wajar bank -3% (biaya dana & kredit valas), eksportir '
                     'energi +4% dan bahan baku +3% (pendapatan dolar). Besaran ASUMSI.',
        'events': [{'hari': 10, 'jenis': 'arus_asing', 'target': 'semua', 'besar': -0.6, 'durasi': 10},
                   {'hari': 10, 'jenis': 'nilai_wajar', 'target': 'sektor:Keuangan', 'besar': -0.03},
                   {'hari': 10, 'jenis': 'nilai_wajar', 'target': 'sektor:Energi', 'besar': 0.04},
                   {'hari': 10, 'jenis': 'nilai_wajar', 'target': 'sektor:Barang Baku', 'besar': 0.03}],
    },
    'asing_masuk': {
        'kelompok': 'Makro',
        'judul': 'Asing masuk besar-besaran 3 minggu',
        'deskripsi': 'Cermin "asing keluar": arus masuk 15 hari bursa. Big cap milik asing naik duluan; '
                     'lihat apakah ritel ikut mengejar atau justru jualan ke asing.',
        'events': [{'hari': 10, 'jenis': 'arus_asing', 'target': 'semua', 'besar': 1.0, 'durasi': 15}],
    },
    'libur_lebaran': {
        'kelompok': 'Makro',
        'judul': 'Libur panjang Lebaran',
        'deskripsi': 'Tiga hari menjelang libur pasar sepi separuh, lalu dibuka dengan gap -1,5% (pasar '
                     'global bergerak selama libur; ARAH ASUMSI, ganti tanda untuk gap naik).',
        'events': [{'hari': 8, 'jenis': 'likuiditas', 'target': 'semua', 'besar': 0.5, 'durasi': 3},
                   {'hari': 11, 'jenis': 'guncangan_ihsg', 'target': 'semua', 'besar': -0.015}],
    },
    'komoditas_naik': {
        'kelompok': 'Sektor & komoditas',
        'judul': 'Harga batubara & nikel melonjak',
        'deskripsi': 'Nilai wajar sektor Energi +8% dan Barang Baku +6%, plus cerita "supercycle" seminggu '
                     'di Energi. Saham komoditas lapis bawah biasanya lari paling kencang.',
        'events': [{'hari': 10, 'jenis': 'nilai_wajar', 'target': 'sektor:Energi', 'besar': 0.08},
                   {'hari': 10, 'jenis': 'nilai_wajar', 'target': 'sektor:Barang Baku', 'besar': 0.06},
                   {'hari': 10, 'jenis': 'sentimen', 'target': 'sektor:Energi', 'besar': 1.0, 'durasi': 5}],
    },
    'rotasi_sektor': {
        'kelompok': 'Sektor & komoditas',
        'judul': 'Rotasi asing: bank keluar, energi masuk',
        'deskripsi': 'Asing menjual sektor Keuangan dan membeli sektor Energi selama 2 minggu, IHSG '
                     'secara keseluruhan tidak didorong. Siapa yang menampung bank yang dilepas.',
        'events': [{'hari': 10, 'jenis': 'arus_asing', 'target': 'sektor:Keuangan', 'besar': -1.0, 'durasi': 10},
                   {'hari': 10, 'jenis': 'arus_asing', 'target': 'sektor:Energi', 'besar': 1.0, 'durasi': 10}],
    },
    'rumor_akuisisi': {
        'kelompok': 'Emiten',
        'judul': 'Rumor akuisisi lalu dibantah',
        'deskripsi': 'Rumor kuat di saham lapis bawah, dibantah 5 hari kemudian. Siapa yang '
                     'untung, siapa yang tersangkut.',
        'events': [{'hari': 10, 'jenis': 'rumor_akuisisi', 'target': '@lapis', 'besar': 1.0,
                    'bantah_hari': 5}],
    },
    'bandar_masuk': {
        'kelompok': 'Mikrostruktur',
        'judul': 'Bandar masuk saham tidur',
        'deskripsi': 'Bandar bermodal besar mulai akumulasi di saham lapis bawah. Ikuti siklus '
                     'akumulasi - markup - distribusi dan siapa yang membeli di pucuk.',
        'events': [{'hari': 5, 'jenis': 'bandar_masuk', 'target': '@lapis', 'besar': 1.0}],
    },
    'msci_ulang_jan': {
        'kelompok': 'Indeks & aliran dana',
        'judul': 'MSCI: putar ulang episode Jan 2026',
        'deskripsi': 'Jalur IHSG dan arus asing per saham yang benar-benar terjadi setelah MSCI membekukan '
                     'rebalancing Indonesia (28 Jan 2026), diputar mulai hari 24 (~11 Nov).',
        'events': [{'hari': 24, 'jenis': 'msci', 'target': 'semua', 'besar': -1.0, 'durasi': 10, 'pola': 'jan2026'}],
    },
    'msci_ulang_jun': {
        'kelompok': 'Indeks & aliran dana',
        'judul': 'MSCI: putar ulang episode Jun 2026',
        'deskripsi': 'Jalur IHSG dan arus asing per saham setelah MSCI menunda review status (24 Jun 2026), '
                     'diputar mulai hari 24.',
        'events': [{'hari': 24, 'jenis': 'msci', 'target': 'semua', 'besar': -1.0, 'durasi': 10, 'pola': 'jun2026'}],
    },
    'msci_frontier': {
        'kelompok': 'Indeks & aliran dana',
        'judul': 'MSCI: konsultasi ke Frontier (1,5x episode Jan, asumsi)',
        'deskripsi': 'Episode Jan 2026 diputar 50% lebih keras -- ASUMSI bahwa konsultasi reklasifikasi lebih '
                     'parah daripada pembekuan rebalancing. Tidak ada episode Frontier nyata untuk Indonesia.',
        'events': [{'hari': 24, 'jenis': 'msci', 'target': 'semua', 'besar': -1.5, 'durasi': 10, 'pola': 'jan2026'}],
    },
    'msci_aman': {
        'kelompok': 'Indeks & aliran dana',
        'judul': 'MSCI: status Indonesia aman',
        'deskripsi': 'Skenario lega pengumuman MSCI 11 Nov 2026: tidak ada reklasifikasi, asing kembali '
                     'masuk pelan ke perkiraan anggota MSCI sampai tanggal efektif.',
        'events': [{'hari': 24, 'jenis': 'msci', 'target': '@msci', 'besar': 0.5, 'durasi': 13}],
    },
    'laba_kejutan': {
        'kelompok': 'Emiten',
        'judul': 'Laba big cap jauh di atas ekspektasi',
        'deskripsi': 'Nilai wajar saham terbesar naik 10%. Seberapa cepat harga menyusul dan '
                     'siapa yang memimpin.',
        'events': [{'hari': 10, 'jenis': 'nilai_wajar', 'target': '@besar', 'besar': 0.10}],
    },
    'unlock': {
        'kelompok': 'Emiten',
        'judul': 'Lock-up berakhir: 5% saham dilepas',
        'deskripsi': 'Pemegang lama menjual 5% saham beredar dalam 10 hari di saham lapis bawah.',
        'events': [{'hari': 10, 'jenis': 'pasokan', 'target': '@lapis', 'besar': 0.05, 'durasi': 10}],
    },
    'laba_meleset': {
        'kelompok': 'Emiten',
        'judul': 'Laba big cap di bawah ekspektasi',
        'deskripsi': 'Cermin "laba kejutan": nilai wajar saham terbesar turun 10%. Apakah harga langsung '
                     'gap down atau ditahan antrean bid ritel yang "serok".',
        'events': [{'hari': 10, 'jenis': 'nilai_wajar', 'target': '@besar', 'besar': -0.10}],
    },
    'kabar_buruk': {
        'kelompok': 'Emiten',
        'judul': 'Kabar buruk lapis bawah (gagal bayar / kasus)',
        'deskripsi': 'Nilai wajar saham lapis bawah -30% dan sentimen jatuh 3 hari: ARB beruntun, antrean '
                     'offer menumpuk. Berapa hari sampai ada yang mau menampung.',
        'events': [{'hari': 10, 'jenis': 'nilai_wajar', 'target': '@lapis', 'besar': -0.30},
                   {'hari': 10, 'jenis': 'sentimen', 'target': '@lapis', 'besar': -3.0, 'durasi': 3}],
    },
    'placement_diskon': {
        'kelompok': 'Emiten',
        'judul': 'Private placement / jual blok di diskon',
        'deskripsi': 'Pemegang besar melepas 3% saham beredar dalam 3 hari di saham lapis bawah, ceritanya '
                     'negatif ("ada yang buang"). Lebih cepat dan lebih padat daripada unlock.',
        'events': [{'hari': 10, 'jenis': 'pasokan', 'target': '@lapis', 'besar': 0.03, 'durasi': 3},
                   {'hari': 10, 'jenis': 'sentimen', 'target': '@lapis', 'besar': -1.0, 'durasi': 1}],
    },
    'dividen_jumbo': {
        'kelompok': 'Emiten',
        'judul': 'Dividen jumbo 6%: cum lalu ex-date',
        'deskripsi': 'Big cap mengumumkan dividen 6% di hari 10, ex-date hari 18. Pemburu dividen masuk '
                     'selama cum; seberapa dalam gap ex-date dan siapa yang "kena jebakan dividen".',
        'events': [{'hari': 10, 'jenis': 'dividen', 'target': '@besar', 'besar': 0.06, 'durasi': 8}],
    },
    'uma_suspensi': {
        'kelompok': 'Mikrostruktur',
        'judul': 'Saham digoreng, kena UMA, suspensi 2 hari',
        'deskripsi': 'Cerita kencang 5 hari di saham lapis bawah, BEI menyuspensi 2 hari di hari 15, dibuka '
                     'lagi dengan sentimen dingin. Siapa yang tersangkut di dalam saat suspensi.',
        'events': [{'hari': 10, 'jenis': 'sentimen', 'target': '@lapis', 'besar': 2.0, 'durasi': 5},
                   {'hari': 15, 'jenis': 'suspensi', 'target': '@lapis', 'besar': 1, 'durasi': 2},
                   {'hari': 17, 'jenis': 'sentimen', 'target': '@lapis', 'besar': -1.5, 'durasi': 1}],
    },
    'margin_call': {
        'kelompok': 'Mikrostruktur',
        'judul': 'Margin call: jual paksa sesudah pasar jatuh',
        'deskripsi': 'IHSG -4% dua hari panik, lalu rekening margin di saham lapis bawah dilikuidasi: 2% '
                     'saham beredar dijual paksa dalam 2 hari tanpa peduli harga.',
        'events': [{'hari': 10, 'jenis': 'panik', 'target': 'semua', 'besar': -0.04, 'durasi': 2},
                   {'hari': 11, 'jenis': 'pasokan', 'target': '@lapis', 'besar': 0.02, 'durasi': 2}],
    },
    'masuk_indeks': {
        'kelompok': 'Indeks & aliran dana',
        'judul': 'Masuk LQ45 / IDX30',
        'deskripsi': 'Diumumkan hari 10, efektif hari 20: MI lokal & dana indeks membeli sampai efektif, lalu '
                     '"sell the news" 3 hari. Saham lapis bawah sebagai kandidat. Besaran ASUMSI.',
        'events': [{'hari': 10, 'jenis': 'sentimen', 'target': '@lapis', 'besar': 0.5, 'durasi': 1},
                   {'hari': 10, 'jenis': 'minat_lokal', 'target': '@lapis', 'besar': 1.0, 'durasi': 10},
                   {'hari': 10, 'jenis': 'arus_asing', 'target': '@lapis', 'besar': 0.5, 'durasi': 10},
                   {'hari': 20, 'jenis': 'minat_lokal', 'target': '@lapis', 'besar': -0.5, 'durasi': 3}],
    },
    'keluar_indeks': {
        'kelompok': 'Indeks & aliran dana',
        'judul': 'Keluar dari LQ45 / IDX30',
        'deskripsi': 'Cermin "masuk indeks": dana indeks menjual sampai tanggal efektif, lalu ada pembeli '
                     'yang merasa sudah murah. Siapa yang menampung barang yang dibuang.',
        'events': [{'hari': 10, 'jenis': 'sentimen', 'target': '@lapis', 'besar': -0.5, 'durasi': 1},
                   {'hari': 10, 'jenis': 'minat_lokal', 'target': '@lapis', 'besar': -1.0, 'durasi': 10},
                   {'hari': 10, 'jenis': 'arus_asing', 'target': '@lapis', 'besar': -0.5, 'durasi': 10},
                   {'hari': 20, 'jenis': 'minat_lokal', 'target': '@lapis', 'besar': 0.5, 'durasi': 3}],
    },
    'window_dressing': {
        'kelompok': 'Indeks & aliran dana',
        'judul': 'Window dressing akhir tahun',
        'deskripsi': 'Institusi lokal mengangkat portofolio 5 hari terakhir sebelum tutup buku, lalu '
                     'melepas sebagian 5 hari sesudahnya. Apakah "rally Desember" bertahan.',
        'events': [{'hari': 15, 'jenis': 'minat_lokal', 'target': 'semua', 'besar': 0.8, 'durasi': 5},
                   {'hari': 20, 'jenis': 'minat_lokal', 'target': 'semua', 'besar': -0.4, 'durasi': 5}],
    },
}

KELOMPOK = ('Makro', 'Sektor & komoditas', 'Emiten', 'Indeks & aliran dana', 'Mikrostruktur')


MCAP_MSCI = 40e12   # ambang perkiraan anggota MSCI Standard (Rp)
POLA_MSCI = ('jan2026', 'jun2026')   # episode nyata yang bisa diputar ulang (kalibrasi.EPISODE_MSCI)
KAPPA_MSCI = 1.0    # pengali arus asing asli yang diputar ulang (1 = persis data)
THETA_MSCI = 1.0    # kepanikan ritel di hari pengumuman
# Kalibrasi (7 Okt 2026, 8 saham bawaan, 3 seed): grid kappa {0..1,5} x theta
# {0..2} di episode Jan, diuji di Jun. GALAT RETURN per saham (h0/h4/h9) twin
# 5,8 pp (Jan) dan 3,6 pp (Jun) -- SAMA dengan patokan naif beta x IHSG (5,7 &
# 3,6). Saham kecil (ARB beruntun) cocok; big cap twin turun lebih dalam dan
# tidak pulih secepat aslinya, karena agen asing lain di twin membeli saat
# program asing menjual -- arus asing kelompok jadi beli, aslinya jual.


def daftar_preset():
    urut = sorted(PRESET.items(), key=lambda kv: KELOMPOK.index(kv[1].get('kelompok', KELOMPOK[0])))
    return [{'kunci': k, 'judul': v['judul'], 'deskripsi': v['deskripsi'], 'events': v['events'],
             'kelompok': v.get('kelompok', KELOMPOK[0])}
            for k, v in urut]


def _mcap(prof, k):
    return ((prof['saham'][k].get('pemilik') or {}).get('mcap')) or prof['saham'][k]['adv_nilai'] * 300


def selesaikan_target(target, prof, kodes):
    """Penanda preset & sektor -> daftar kode."""
    if isinstance(target, (list, tuple)):
        hasil = []
        for t in target:
            hasil.extend(selesaikan_target(t, prof, kodes))
        return list(dict.fromkeys(hasil))
    t = str(target or 'semua').strip()
    if t.lower() == 'semua':
        return list(kodes)
    urut = sorted(kodes, key=lambda k: _mcap(prof, k))
    if t == '@besar':
        return [urut[-1]]
    if t == '@kecil':
        return [urut[0]]
    if t == '@msci':
        # Perkiraan anggota MSCI Standard Indonesia: data keanggotaan resmi
        # tidak ada di project, jadi dipakai ambang kapitalisasi KSEI.
        anggota = [k for k in kodes if _mcap(prof, k) >= MCAP_MSCI]
        return anggota or [urut[-1]]
    if t == '@lapis':
        kecil = [k for k in urut if _mcap(prof, k) < 30e12]
        return [kecil[0] if kecil else urut[0]]
    if t.lower().startswith('sektor:'):
        nama = t.split(':', 1)[1].strip().lower()
        return [k for k in kodes if (prof['saham'][k].get('sektor') or '').lower() == nama]
    t = t.upper()
    return [t] if t in kodes else []


def siapkan(events, prof, kodes, hari):
    """Validasi + selesaikan target. Return (events_bersih, peringatan)."""
    bersih, peringatan = [], []
    for i, ev in enumerate(events or []):
        ev = copy.deepcopy(ev)
        jenis = ev.get('jenis')
        if jenis not in JENIS:
            peringatan.append('Event #%d: jenis "%s" tidak dikenal, dilewati.' % (i + 1, jenis))
            continue
        try:
            ev['hari'] = int(ev.get('hari', 0))
            ev['besar'] = float(ev.get('besar', 0))
            ev['durasi'] = max(1, int(ev.get('durasi', 1) or 1))
            if ev.get('bantah_hari') not in (None, '', 0, '0'):
                ev['bantah_hari'] = int(ev['bantah_hari'])
            else:
                ev.pop('bantah_hari', None)
        except (TypeError, ValueError):
            peringatan.append('Event #%d: angka tidak sah, dilewati.' % (i + 1))
            continue
        if not 0 <= ev['hari'] < hari:
            peringatan.append('Event #%d (%s) di hari %d, di luar rentang 0-%d: dilewati.'
                              % (i + 1, JENIS[jenis]['label'], ev['hari'], hari - 1))
            continue
        kode = selesaikan_target(ev.get('target', 'semua'), prof, kodes)
        if not kode:
            peringatan.append('Event #%d: target "%s" tidak ada di saham pilihan, dilewati.'
                              % (i + 1, ev.get('target')))
            continue
        if jenis == 'dividen':
            if not 0 < ev['besar'] < 0.5:
                peringatan.append('Event #%d: yield dividen %s di luar 0-0,5, dilewati.' % (i + 1, ev['besar']))
                continue
            if ev['hari'] + ev['durasi'] >= hari:
                peringatan.append('Event #%d: ex-date dividen (hari %d) di luar rentang simulasi -- hanya periode '
                                  'cum yang tersimulasi.' % (i + 1, ev['hari'] + ev['durasi']))
        if jenis == 'msci':
            ev['pola'] = ev.get('pola') or 'asumsi'
            if ev['pola'] not in POLA_MSCI + ('asumsi',):
                peringatan.append('Event #%d: pola MSCI "%s" tidak dikenal, dipakai asumsi.' % (i + 1, ev['pola']))
                ev['pola'] = 'asumsi'
            if ev['pola'] in POLA_MSCI:
                ev['durasi'] = 10
                kode = list(kodes)     # arus asing asli per saham sudah memuat siapa yang kena
        ev['target_kode'] = kode
        ev['id'] = i
        bersih.append(ev)
    return bersih, peringatan


def butuh_cadangan(events):
    """Slot agen cadangan yang harus disiapkan di KEDUA dunia (supaya jumlah
    agen -- dan karena itu urutan angka acak -- sama persis)."""
    return sum(len(ev.get('target_kode', [1])) for ev in events
               if ev['jenis'] in ('bandar_masuk', 'pasokan')
               or (ev['jenis'] == 'msci' and ev.get('pola') in POLA_MSCI))


def terapkan(w, ev, h):
    """Dipanggil tiap pagi untuk tiap event. `h` = hari rekam (bisa negatif
    selama pemanasan -- event tidak pernah aktif di sana)."""
    mulai, durasi, besar = ev['hari'], ev['durasi'], ev['besar']
    if h < mulai:
        return
    aktif = h < mulai + durasi
    pertama = h == mulai
    j = np.array([w.kodes.index(k) for k in ev['target_kode']], dtype=np.int64)
    jenis = ev['jenis']
    sudah = w.efek.setdefault(ev['id'], {})

    if jenis == 'sentimen':
        if pertama:
            w.offset_sent[j] += besar
        elif aktif:
            w.offset_sent[j] += 0.15 * besar          # menahan level melawan peluruhan 15%/hari

    elif jenis == 'nilai_wajar':
        if pertama:
            w.kejut_V[j] += np.log1p(besar)
            w.offset_sent[j] += np.sign(besar) * min(1.0, abs(besar) * 5) * 0.8

    elif jenis == 'suku_bunga':
        skala = besar / 50.0
        if pertama:
            w.efek_m += -0.012 * skala
            w.offset_sent_pasar += -0.8 * skala
            prop = [i for i, k in enumerate(w.kodes) if w.sektor[i] == 'Properti & Real Estat']
            if prop:
                w.kejut_V[np.array(prop)] += -0.03 * skala
        if aktif:
            w.offset_lokal += -0.6 * skala
            w.offset_R += -0.4 * skala
            w.drift_m += -0.0005 * skala

    elif jenis == 'arus_asing':
        if aktif:
            if str(ev.get('target', 'semua')).lower() == 'semua':
                w.offset_R += 1.5 * besar
                w.drift_m += 0.002 * besar
            else:
                w.offset_R_saham[j] += 1.5 * besar

    elif jenis == 'msci' and ev.get('pola', 'asumsi') in POLA_MSCI:
        # PUTAR ULANG episode nyata: jalur IHSG asli hari demi hari, arus asing
        # asli per saham (dalam kelipatan nilai transaksi harian) x KAPPA,
        # kepanikan ritel THETA. Besar -1 = persis episode, -1,5 = 50% lebih
        # parah, besar positif = cerminnya (asumsi, tidak ada episode lega).
        epi = (w.prof.get('episode_msci') or {}).get(ev['pola'])
        t = h - mulai
        if epi and 0 <= t < len(epi['ihsg_r']):
            skala = -besar
            w.efek_m += skala * epi['ihsg_r'][t]
            if t == 0 and not sudah.get('dipasang'):
                # arus netto asing asli per hari (kelipatan nilai transaksi harian)
                # diputar oleh agen program asing di tiap saham yang punya datanya
                for jj, k in enumerate(w.kodes):
                    a = (epi['saham'].get(k) or {}).get('arus', {}).get('asing')
                    if a and any(abs(x) > 0.01 for x in a):
                        nilai_harian = w.ps[jj]['adv_nilai']
                        w._pasang_program_asing(jj, [KAPPA_MSCI * skala * x * nilai_harian for x in a])
                sudah['dipasang'] = True
            if t == 0:
                w.offset_sent_pasar += -THETA_MSCI * skala
            if t < 3 and skala > 0:
                w.panik_mult = max(w.panik_mult, 1.0 + THETA_MSCI * skala)

    elif jenis == 'msci':
        if pertama:
            w.efek_m += 0.03 * besar
            w.offset_sent_pasar += 1.0 * besar
        if aktif:
            akhir = h == mulai + durasi - 1
            w.offset_R += 0.3 * besar
            w.offset_R_saham[j] += (3.0 if akhir else 1.5) * besar
            w.drift_m += 0.0015 * besar

    elif jenis == 'rumor_akuisisi':
        premi = np.log1p(0.15 * besar)
        if pertama:
            w.offset_sent[j] += 2.0 * besar
            w.kejut_V[j] += premi
            w.buzz[j] += 2.0
        b = ev.get('bantah_hari')
        if b and h == mulai + b:
            w.offset_sent[j] += -2.5 * besar
            w.kejut_V[j] += -premi
            w.buzz[j] += 1.0

    elif jenis == 'bandar_masuk':
        if pertama and not sudah.get('dipasang'):
            for jj in j:
                if w.cadangan:
                    a = w.cadangan.pop(0)
                    w._pasang_bandar(a, int(jj), besar=max(besar, 0.1), fase='akumulasi', otomatis=False)
            sudah['dipasang'] = True

    elif jenis == 'panik':
        if pertama:
            w.efek_m += besar
            w.offset_sent_pasar += -2.0
            w.offset_R += -1.5
        if aktif:
            w.panik_mult = max(w.panik_mult, 2.0)
            w.offset_lokal += -0.5
            w.offset_R += -0.8

    elif jenis == 'pasokan':
        if pertama and not sudah.get('dipasang'):
            for jj in j:
                w._pasang_penjual(int(jj), max(besar, 0.0), durasi)
            sudah['dipasang'] = True

    elif jenis == 'likuiditas':
        if aktif:
            w.likuid[j] *= max(besar, 0.05)

    elif jenis == 'guncangan_ihsg':
        if pertama:
            w.efek_m += besar

    elif jenis == 'dividen':
        # Periode cum = [hari, hari + durasi), ex-date = hari + durasi. DPS
        # dikunci dari harga di hari pengumuman. Pembayaran kas ke pemegang
        # dicatat di ex-date (aslinya ~2 minggu kemudian, ke pemegang per
        # tanggal pencatatan = pemegang di akhir cum) -- bukan setoran,
        # karena ini memang hasil investasi pemegang.
        skala = min(besar / 0.05, 2.0)
        if pertama:
            sudah['dps'] = besar * w.tutup_kemarin[j]
        if aktif:
            w.offset_sent[j] += (1.0 if pertama else 0.15) * 0.3 * skala
            w.offset_lokal_saham[j] += 0.5 * skala
        if h == mulai + durasi and not sudah.get('dibayar'):
            dps = sudah['dps']
            w.kejut_V[j] += np.log(np.maximum(1.0 - dps / w.V[j], 0.05))
            from .aturan import LOT
            for jj, d_ in zip(j, dps):
                w.pop.kas += w.pop.pos[:, jj] * d_ * LOT
            sudah['dibayar'] = True

    elif jenis == 'suspensi':
        if pertama:
            sudah['V'] = w.V[j].copy()     # nilai wajar saat terakhir diperdagangkan
        if aktif:
            w.suspen[j] = True
        elif h == mulai + durasi:
            for jj, v in zip(j, sudah['V']):
                w.buka_suspensi[int(jj)] = v

    elif jenis == 'minat_lokal':
        if aktif:
            w.offset_lokal_saham[j] += 1.5 * besar
