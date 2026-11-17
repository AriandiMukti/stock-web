"""
Status Bukti: satu tabel yang bilang, untuk tiap menu, seberapa jauh
temuannya pernah diuji.

KENAPA MODUL INI ADA
Tiap modul di app ini punya docstring yang jujur soal batas temuannya --
mana hipotesis yang gagal, mana yang cuma berlaku di kalibrasi, mana yang
bertahan di luar sampel. Masalahnya semua kejujuran itu ada di KODE.
Dari 32 template, cuma 6 yang menyebut hasil uji luar sampel, dan
bentuknya paragraf di tengah halaman.

Akibatnya pembaca yang membuka menu tidak punya cara tahu sekilas bahwa
dari sembilan belas menu, cuma dua yang temuannya selamat di luar sampel
-- dan bahwa beberapa menu yang tampilannya paling meyakinkan justru
yang paling tidak berdasar. Halaman yang penuh angka rapi terasa sama
otoritatifnya entah temuannya lolos atau gagal.

Modul ini tidak menghitung apa pun. Dia memindahkan pengetahuan yang
sudah ada di docstring ke layar, dalam bentuk yang seragam.

KENAPA EMPAT TINGKAT, BUKAN SKOR ANGKA
Skor 0-100 akan mengundang perbandingan yang tidak berarti ("menu ini 72,
itu 65"). Yang penting cuma pertanyaan biner bertingkat: pernah diuji di
luar sampel? lolos? Empat label di bawah menjawab itu tanpa memberi kesan
presisi yang tidak ada.

CARA MENAMBAH ENTRI
Jangan menulis status dari ingatan. Baca docstring modulnya, ambil
kalimat vonisnya, dan kutip angkanya kalau ada. Kalau sebuah modul belum
pernah diuji di luar sampel, statusnya `kalibrasi` -- bukan `teruji`
karena angkanya terlihat bagus.
"""

# Empat tingkat, diurut dari yang paling bisa dipercaya.
TINGKAT = {
    'teruji': {
        'label': 'Teruji luar sampel',
        'warna': 'hijau',
        'arti': 'Diuji di periode DAN semesta yang terpisah dari tempat temuannya lahir, dan lolos.',
    },
    'kalibrasi': {
        'label': 'Kalibrasi saja',
        'warna': 'kuning',
        'arti': 'Angkanya cuma diukur di data tempat temuannya ditemukan. Belum pernah diuji di luar itu.',
    },
    'gagal': {
        'label': 'Gagal luar sampel',
        'warna': 'merah',
        'arti': 'Sudah diuji di luar sampel dan keunggulannya menyusut, hilang, atau berbalik tanda.',
    },
    'alat': {
        'label': 'Alat ukur, bukan sinyal',
        'warna': 'netral',
        'arti': 'Tidak pernah mengaku bisa menebak arah. Gunanya mengukur, mengaudit, atau memberi konteks.',
    },
}

# Urutan daftar mengikuti urutan nav, bukan urutan status -- supaya bisa
# dicocokkan sambil menelusuri menu.
MENU = [
    {'menu': 'Takaran Risiko', 'url': '/takaran-risiko', 'modul': 'risiko.py',
     'status': 'teruji',
     'ringkas': 'Korelasi kelipatan risiko antar sampel +0,90, kelipatan peluang +0,95.',
     'catatan': 'Yang teruji BESARAN ayunan, bukan arah. Modul ini memang tidak menebak arah.'},

    # Turun dari 'teruji' 23 Sep 2026 -- lihat bagian pertama docstring
    # jatuh_dalam.py. Angka lamanya (+36,2pp rally, +9,39pp return) benar
    # untuk 20 emiten folder Test, tapi emiten itu dipilih karena besar HARI
    # INI, jadi kejatuhan lama mereka pasti pulih: bias hindsight.
    {'menu': 'Jatuh Dalam', 'url': '/jatuh-dalam', 'modul': 'jatuh_dalam.py',
     'status': 'gagal',
     'ringkas': 'Diuji ulang di ~750 emiten likuid 2013-2026: kalah dari pasar hari yang sama, '
                '-7,5% per 60 hari (t -5,6), negatif 9 dari 12 tahun. Portofolio -19,1%/tahun.',
     'catatan': 'Status "teruji" sebelumnya datang dari 20 emiten folder Test -- dipilih tahun 2026 '
                'karena besar hari ini, jadi setiap kejatuhan lama mereka pasti pulih. Di 20 emiten '
                'itu replikasinya memang +14,58pp; di semua emiten likuid aturan yang sama -1,56pp vs '
                'pasar hari yang sama, majemuk -2,99%.'},

    {'menu': 'Tembus Basis', 'url': '/tembus-basis', 'modul': 'tembus_basis.py',
     'status': 'teruji',
     'ringkas': 'Tembus basis <20% + volume >2x: +4,7% per 60 hari vs pasar (t 4,7) di separuh emiten '
                'yang tidak dipakai mencari, 2020-2026; positif 13 dari 14 tahun. Puncak 52 minggu + '
                'volume juga 13/14.',
     'catatan': 'Kombinasi keduanya (terkuat, +7,1%) dipilih SETELAH data validasi dilihat -- jurnal '
                'majunya yang menguji. Win per transaksi ~47%: untungnya dari segelintir pemenang '
                'besar. Semesta Yahoo cuma emiten yang masih tercatat (survivorship).'},

    # 23 Sep 2026. "Teruji" untuk PERINGKATNYA (IC). Desil 10 sebagai daftar
    # beli jauh lebih lemah -- lihat catatan.
    {'menu': 'Skor Kecondongan', 'url': '/skor-kecondongan', 'modul': 'kecondongan.py',
     'status': 'teruji',
     'ringkas': 'Dekat puncak 52 mgg + tenang: IC +0,094 (t 3,9) di pencarian, +0,155 (t 6,9) di validasi, '
                'positif di keempat sel. Desil 1 kalah dari pasar di semua sel dan lapis likuiditas '
                '(-2,6% s.d. -13,5% per 60 hari).',
     'catatan': 'IC dua komponen di validasi sudah terlihat (pilot analog.py) sebelum rumusnya ditulis; '
                'rumusnya tanpa bobot atau ambang yang disetel, dan jurnal maju sejak 23 Sep 2026 yang '
                'menguji buta. Desil 10 sebagai daftar beli setara beli-semua (8,5% vs 8,3%/tahun '
                '2020-2026) -- kegunaannya peringkat dan saringan, bukan daftar beli.'},

    {'menu': 'Scanner Lab', 'url': '/scanner-lab', 'modul': 'scanner.py',
     'status': 'kalibrasi',
     'ringkas': 'Skor dari backtest 6.871 sinyal Jan-Sep 2026, baseline pasar -1,33%/20 hari.',
     'catatan': 'Satu rezim pasar, satu periode. Temuan terkuatnya (volume sepi lebih baik '
                'daripada ramai) belum pernah diuji di periode lain.'},

    {'menu': 'Kering Screener', 'url': '/kering-screener', 'modul': 'kering_screener.py',
     'status': 'gagal',
     'ringkas': 'Backtest 529 sinyal dengan ongkos+slippage nyata: tidak menguntungkan.',
     'catatan': 'Skor >=0,75 memang menangkap 5 dari 7 contoh akumulasi sungguhan, tapi itu '
                'akurasi DETEKSI pada kasus yang hasilnya sudah diketahui -- bukan bukti '
                'membeli tiap kali sinyal muncul itu untung.'},

    {'menu': 'Serapan Float', 'url': '/serapan-float', 'modul': 'float_squeeze.py',
     'status': 'kalibrasi',
     'ringkas': 'Hipotesis "float mengering" DIUJI DULU dan ditolak datanya.',
     'catatan': 'Yang tersisa (serapan 0-0,5% paling baik) berasal dari 7.467 pengamatan '
                'Jan-Sep 2026 saja, dan hubungannya tidak monoton -- itu tanda peringatan.'},

    {'menu': 'Akumulasi Palsu', 'url': '/akumulasi-palsu', 'modul': 'fake_accumulation.py',
     'status': 'kalibrasi',
     'ringkas': 'Hipotesis awal (penjual melebar) gagal. Yang ditemukan: harga x arus.',
     'catatan': '12.299 pengamatan, semuanya 2026. Selisih antar selnya besar (42,9% vs 24,3%) '
                'tapi belum pernah diuji di periode lain.'},

    {'menu': 'Radar Insider', 'url': '/radar-insider', 'modul': 'insider_signal.py',
     'status': 'kalibrasi',
     'ringkas': 'Insider BELI polos nol informasi (win 49,5%); disilang Jatuh Dalam/Akumulasi '
                'Palsu jadi win 57-68%. Insider JUAL sbg peringatan dini: +15-34pp risiko '
                'jatuh dalam, bertahan dikontrol ganda level+momentum.',
     'catatan': 'Semua dari SATU periode (Apr-Sep 2026), dan membaca transaksi di hari '
                'transaksinya -- padahal data di sini ditarik sebulan sekali. Pratinjau dengan '
                'jeda nyata (median 17 hari): +11,0pp, bukan +26,7pp (in-sample, n=41). Jurnal '
                'maju (insider_jurnal.py) mencatat sejak 22 Sep 2026 per tanggal TERLIHAT -- '
                'bacaan pertama 40 hari bursa sesudah JUAL baru pertama terlihat.'},

    {'menu': 'Penemu Pola', 'url': '/penemu-pola', 'modul': 'pattern_miner.py',
     'status': 'gagal',
     'ringkas': 'Diuji di 10 tahun data lain: selisih 6-18 poin persen menyusut jadi ~1 poin.',
     'catatan': 'Koreksi Benjamini-Hochberg di dalamnya mengendalikan pengujian berganda di '
                'DALAM satu dataset; ia tidak tahu apa-apa soal kebetulan periode. Jurnal maju '
                '(pola_jurnal.py) bacaan pertamanya awal November 2026.'},

    {'menu': 'Sidik Jari Broker', 'url': '/sidik-jari-broker', 'modul': 'broker_fingerprint.py',
     'status': 'gagal',
     'ringkas': 'Harga modal bandar: kalibrasi edge -10,91; luar sampel +1,16 -- tanda terbalik.',
     'catatan': '"Ikuti broker pintar" juga tidak lolos: diuji di tingkat tipe perilaku, SEMUA '
                'tipe edge-nya negatif terhadap baseline.'},

    {'menu': 'Screens (Consol / Retail Sell)', 'url': '/audit-screener', 'modul': 'screen_eval.py',
     'status': 'gagal',
     'ringkas': 'Rekam jejak menunjukkan sebagian screen KALAH dari pasar (Consol -5,29pp, Retail Sell -3,27pp).',
     'catatan': 'Diukur dengan rekonstruksi keanggotaan tiap hari bursa, bukan dari ingatan.'},

    {'menu': 'Keramaian', 'url': '/saham/BBRI', 'modul': 'crowding.py',
     'status': 'alat',
     'ringkas': 'Matriks dari 98.958 pengamatan populasi umum. Win rate tertinggi pun cuma 45%.',
     'catatan': 'Bukan sinyal beli/jual dan bukan ramalan per emiten -- rata-rata historis '
                'KELOMPOK tempat saham itu berada hari ini.'},

    {'menu': 'Audit Screener', 'url': '/audit-screener', 'modul': 'signal_recall.py',
     'status': 'alat',
     'ringkas': 'Mengukur apa yang DILEWATKAN screener (recall), bukan menghasilkan sinyal.',
     'catatan': 'Justru alat untuk menguji menu lain.'},

    {'menu': 'Rontgen Portofolio', 'url': '/rontgen-portofolio', 'modul': 'portfolio_xray.py',
     'status': 'alat',
     'ringkas': 'Memeriksa posisi yang sudah dipegang, tidak memilihkan posisi baru.'},

    {'menu': 'Kepercayaan Data', 'url': '/kepercayaan-data', 'modul': 'data_confidence.py',
     'status': 'alat',
     'ringkas': 'Menilai kesegaran dan kelengkapan data per emiten.'},

    {'menu': 'Emiten Hilang', 'url': '/emiten-hilang', 'modul': 'survivorship.py',
     'status': 'alat',
     'ringkas': 'Mengukur seberapa besar lubang survivorship di backtest menu lain.',
     'catatan': 'Temuan utamanya: emiten di zona jatuh >40% tujuh kali lebih sering berhenti '
                'mengirim data dibanding emiten biasa.'},

    {'menu': 'Apa Berubah Hari Ini', 'url': '/apa-berubah', 'modul': 'perubahan.py',
     'status': 'alat',
     'ringkas': 'Menyelisihkan keanggotaan screen hari ini terhadap kemarin. Tidak menilai apa pun.'},

    {'menu': 'Market Digital Twin', 'url': '/digital-twin', 'modul': 'twin/',
     'status': 'alat',
     'ringkas': 'Simulasi bagaimana-jika (dua dunia, beda satu skenario), bukan ramalan. Rapor realisme: '
                '88/104 perilaku yang tidak disetel muncul seperti pasar asli di 8 saham kalibrasi, dan '
                '88/104 di 8 saham yang tidak pernah dipakai menyetel.',
     'catatan': 'Kelemahan yang konsisten: gejolak mengumpul pada return sisa cuma muncul di 1 dari 8 '
                'saham semesta uji. Besaran penerjemahan skenario (mis. +50 bp = faktor IHSG -1,2%) '
                'adalah asumsi tertulis, bukan estimasi.'},
]


def ringkasan():
    """Hitungan per tingkat, untuk lencana dan halaman daftar."""
    hitung = {k: 0 for k in TINGKAT}
    for m in MENU:
        hitung[m['status']] = hitung.get(m['status'], 0) + 1
    return {
        'tingkat': TINGKAT,
        'menu': MENU,
        'hitung': hitung,
        'total': len(MENU),
        'catatan': (
            'Status di sini bukan penilaian mutu kode atau mutu halamannya. Dia menjawab satu '
            'pertanyaan saja: temuan di balik menu ini pernah diuji di luar tempat dia lahir '
            'atau belum. Menu ber-status "alat" tidak lebih rendah dari "teruji" -- dia memang '
            'tidak pernah mengaku bisa menebak arah.'),
    }


def untuk(url):
    """Status satu menu, dipakai untuk menempelkan lencana di halamannya."""
    for m in MENU:
        if m['url'] == url:
            return dict(m, **TINGKAT[m['status']])
    return None
