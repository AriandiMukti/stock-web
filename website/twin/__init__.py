"""
Generative Market Digital Twin -- klon digital beberapa saham BEI yang
dijalankan ribuan agen berpersona (ritel, institusi lokal, asing, bandar,
pedagang cepat), untuk menjawab "bagaimana JIKA ...", bukan "akan ke mana".

Isi paket:
    aturan.py     fraksi harga, ARA/ARB, lot -- aturan BEI yang berlaku
    buku.py       lelang batch: harga kliring + alokasi isi order
    kalibrasi.py  profil saham & persona dari data project (+ IHSG Yahoo)
    agen.py       populasi agen dan cara tiap persona mengambil keputusan
    skenario.py   jadwal guncangan + preset skenario
    simulasi.py   satu dunia: hari demi hari, tick demi tick
    validasi.py   rapor realisme: twin vs pasar asli
    jalan.py      Monte Carlo baseline-vs-skenario, ringkasan, registrasi riset
    llm.py        lapisan opsional Claude (penerjemah skenario, agen pemimpin)
    uji_mundur.py uji mundur: twin vs patokan naif pada event dividen & BI rate

SEBERAPA MIRIP (rapor realisme, baseline 6 run x 60 hari, 7 Okt 2026)
  Perilaku yang TIDAK pernah disetel -- ekor gemuk, gejolak mengumpul,
  autokorelasi ~0, volume membesar saat harga bergerak, spread, arah arus
  ritel/asing/lokal terhadap return hari itu & 5 hari sebelumnya:
    8 saham kalibrasi (BBCA BBRI TLKM ASII ANTM BUMI DEWA RAJA)   88/104
    8 saham yang tak pernah dipakai menyetel (BRIS UNTR CPIN PGAS
      MEDC CTRA ACES ESSA)                                        88/104
  Semesta kedua (BMRI BBNI ICBP UNVR ADRO MDKA HRUM ERAA) memberi 87/104,
  lalu 91/104 setelah mekanisme "perhatian -> informasi" ditambah -- jadi
  semesta itu sudah tidak bersih. Kelemahan konsisten: gejolak mengumpul
  pada return sisa (1/8 di semesta uji).

KENAPA "TWIN", BUKAN PREDIKTOR
Hampir semua klaim ARAH di app ini runtuh di luar sampel. Twin ini tidak
membuat klaim arah tentang pasar asli sama sekali: ia membandingkan dua
dunia buatan yang identik kecuali satu hal (skenarionya), lalu melaporkan
selisihnya. Yang bisa dinilai cuma seberapa mirip dunia buatannya dengan
pasar asli -- itu tugas validasi.py.

Uji mundur (uji_mundur.py, 9 Okt 2026) memastikan batas itu: diberi event
nyata (633 dividen, 38 perubahan BI rate), twin paling banter menyamai
aritmetika "harga turun sebesar dividen", arah BI rate-nya terbalik dari
data, dan perbedaan antar saham hasil dinamika agen tidak menebak apa-apa.
"""
