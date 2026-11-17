"""Preset skenario: segmen populasi, parameter, event siap pakai, dan template postingan.

Setiap segmen punya sifat:
  share  - porsi populasi
  bias   - opini dasar sebelum skenario (-1..1)
  sens   - seberapa kuat terpengaruh dampak skenario
  stub   - keras kepala (0 = mudah terpengaruh teman, 1 = tidak berubah)
  act    - peluang dasar memposting per ronde
  eps    - batas toleransi: hanya terpengaruh opini yang jaraknya < eps
  loyal  - menahan diri dari aksi negatif
  hub    - True jika segmen ini menempati node paling populer (influencer/media)
"""


def _seg(key, label, share, bias, sens, stub, act, eps, loyal, hub=False):
    return dict(key=key, label=label, share=share, bias=bias, sens=sens, stub=stub,
                act=act, eps=eps, loyal=loyal, hub=hub)


def _clip(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


AWARENESS = {"key": "awareness", "label": "Yang langsung tahu di awal (%)", "min": 1, "max": 100, "default": 50}


# ---------------------------------------------------------------- Kenaikan harga
def _harga_impact(p):
    return _clip(-min(1.0, p["pct"] / 40) * (1.15 - p["quality"] / 10 * 0.5))


def _harga_recs(s):
    r = []
    hemat = s["seg"].get("hemat")
    if hemat and hemat["neg"] > 0.15:
        r.append(f"Segmen sensitif harga paling banyak kabur ({hemat['neg']:.0%}). Siapkan paket hemat atau tier lebih murah agar mereka tidak pindah ke kompetitor.")
    if s["params"]["pct"] > 20:
        r.append("Kenaikan di atas 20% memicu reaksi tajam. Uji kenaikan bertahap (misalnya dua kali setengahnya) dan bandingkan hasilnya.")
    if not s["has_positive_event"]:
        r.append("Belum ada intervensi positif. Uji event 'Klarifikasi & alasan kenaikan' atau 'Promo loyalitas' di ronde awal.")
    if s["params"]["alt"] >= 7:
        r.append("Alternatif di pasar sangat tersedia, jadi loyalitas mudah pecah. Perkuat pembeda (kualitas/layanan) sebelum menaikkan harga.")
    return r


HARGA = dict(
    key="harga", label="Kenaikan harga", subject_label="Nama produk/brand", subject_default="Produk kami",
    competitor=True, competitor_default="kompetitor",
    params=[
        {"key": "pct", "label": "Besar kenaikan harga (%)", "min": 1, "max": 100, "default": 15},
        {"key": "quality", "label": "Kualitas dibanding kompetitor (0-10)", "min": 0, "max": 10, "default": 6},
        {"key": "alt", "label": "Ketersediaan alternatif (0-10)", "min": 0, "max": 10, "default": 6},
        AWARENESS,
    ],
    impact=_harga_impact,
    controversy=lambda p: min(1.0, p["pct"] / 60),
    neg_mult=lambda p: 0.2 + p["alt"] / 10 * 1.2,
    pos_mult=lambda p: 0.6 + p["quality"] / 10 * 0.6,
    neg_label="Berhenti membeli / pindah", pos_label="Tetap & merekomendasikan",
    segments=[
        _seg("setia", "Pelanggan setia", 0.25, 0.35, 0.5, 0.7, 0.12, 0.6, 0.8),
        _seg("hemat", "Sensitif harga", 0.35, 0.0, 1.3, 0.4, 0.2, 0.7, 0.2),
        _seg("premium", "Pelanggan premium", 0.15, 0.2, 0.4, 0.6, 0.08, 0.5, 0.6),
        _seg("baru", "Pelanggan baru", 0.20, 0.05, 1.0, 0.3, 0.1, 0.8, 0.1),
        _seg("influencer", "Influencer & media", 0.05, 0.0, 0.9, 0.5, 0.5, 0.5, 0.3, hub=True),
    ],
    events=[
        {"name": "Kompetitor menurunkan harga", "effect": -0.3, "target": "hemat", "aw": 0.0},
        {"name": "Promo / diskon loyalitas", "effect": 0.35, "target": "all", "aw": 0.1},
        {"name": "Klarifikasi & alasan kenaikan", "effect": 0.2, "target": "all", "aw": 0.2},
        {"name": "Postingan viral negatif", "effect": -0.35, "target": "all", "aw": 0.3},
        {"name": "Kualitas / layanan ditingkatkan", "effect": 0.25, "target": "all", "aw": 0.05},
        {"name": "Influencer mendukung", "effect": 0.6, "target": "influencer", "aw": 0.15},
    ],
    recs=_harga_recs,
    templates={
        "vneg": ["Naik {pct}%?? Gak masuk akal. Fix pindah ke {kompetitor}.",
                 "{subjek} makin gak ramah kantong. Bye.",
                 "Udah mahal, naik lagi. Kecewa berat sama {subjek}.",
                 "Guys mending cek {kompetitor} deh, harganya lebih waras.",
                 "Stop beli {subjek}. Naik {pct}% tanpa alasan jelas itu keterlaluan."],
        "neg": ["Hmm {subjek} naik {pct}%, mulai mikir-mikir buat lanjut.",
                "Agak berat sih kenaikannya, semoga ada promo.",
                "Kenaikan {pct}% kerasa banget buat kantong.",
                "Kayaknya bakal kurangin beli {subjek} dulu.",
                "Kualitasnya sama, harganya naik. Hmm."],
        "neu": ["{subjek} naik harga ya? Ada yang tau alasannya?",
                "Lihat dulu deh, sebanding gak sama kualitasnya.",
                "Semua juga naik sih sekarang...",
                "Baru tau {subjek} naik {pct}%. Masih nimbang."],
        "pos": ["Naik dikit gapapa, kualitas {subjek} masih oke.",
                "Masih worth it menurutku.",
                "Wajar sih naik, bahan baku juga naik.",
                "Tetap beli {subjek}, belum ada yang sebagus ini."],
        "vpos": ["Tetap setia sama {subjek}! Kualitasnya gak ada lawan.",
                 "Mau naik berapa pun, {subjek} tetap nomor satu buatku.",
                 "Yang ngeluh coba bandingin kualitasnya deh. {subjek} masih juara.",
                 "Rekomendasi banget {subjek}, harga sebanding kualitas."],
    },
)


# ---------------------------------------------------------- Peluncuran produk
def _produk_impact(p):
    return _clip((p["inovasi"] / 10 - 0.35) * 1.4 - (p["harga"] / 10 - 0.5) * 0.8)


def _produk_recs(s):
    r = []
    if s["final"]["aware"] < 0.6:
        r.append(f"Baru {s['final']['aware']:.0%} populasi yang tahu produk ini. Tambah jangkauan awal (iklan, seeding ke influencer) sebelum menilai minat.")
    m = s["seg"].get("mainstream")
    if m and m["op"] < 0.15:
        r.append("Mayoritas pragmatis belum yakin. Mereka butuh bukti sosial: testimoni, review independen, garansi.")
    if s["params"]["harga"] >= 7:
        r.append("Harga relatif mahal menahan adopsi. Uji 'Diskon peluncuran' untuk segmen mayoritas.")
    sk = s["seg"].get("skeptis")
    if sk and sk["neg"] > 0.2:
        r.append("Kelompok skeptis aktif mengkritik. Siapkan FAQ dan jawaban untuk keberatan utama sejak hari pertama.")
    return r


PRODUK = dict(
    key="produk", label="Peluncuran produk baru", subject_label="Nama produk", subject_default="Produk baru",
    competitor=True, competitor_default="produk lama",
    params=[
        {"key": "inovasi", "label": "Tingkat inovasi / keunikan (0-10)", "min": 0, "max": 10, "default": 7},
        {"key": "harga", "label": "Harga relatif (0 murah - 10 mahal)", "min": 0, "max": 10, "default": 5},
        dict(AWARENESS, default=20),
    ],
    impact=_produk_impact,
    controversy=lambda p: 0.25,
    neg_mult=lambda p: 0.8,
    pos_mult=lambda p: 1.4 - p["harga"] / 10 * 0.8,
    neg_label="Menolak & mengkritik", pos_label="Membeli / mencoba",
    segments=[
        _seg("early", "Early adopter", 0.13, 0.2, 1.2, 0.3, 0.3, 0.8, 0.3),
        _seg("mainstream", "Mayoritas pragmatis", 0.45, 0.0, 0.8, 0.5, 0.08, 0.5, 0.5),
        _seg("skeptis", "Skeptis / konservatif", 0.22, -0.25, 0.6, 0.7, 0.1, 0.4, 0.3),
        _seg("fans", "Fans brand", 0.15, 0.4, 0.7, 0.6, 0.15, 0.5, 0.8),
        _seg("influencer", "Reviewer & media", 0.05, 0.0, 1.0, 0.5, 0.5, 0.5, 0.5, hub=True),
    ],
    events=[
        {"name": "Review positif dari reviewer", "effect": 0.35, "target": "all", "aw": 0.2},
        {"name": "Bug / masalah produk viral", "effect": -0.4, "target": "all", "aw": 0.25},
        {"name": "Diskon peluncuran", "effect": 0.3, "target": "mainstream", "aw": 0.1},
        {"name": "Kompetitor rilis produk serupa", "effect": -0.2, "target": "all", "aw": 0.0},
        {"name": "Iklan besar-besaran", "effect": 0.1, "target": "all", "aw": 0.4},
    ],
    recs=_produk_recs,
    templates={
        "vneg": ["{subjek}? Cuma gimmick. Mending {kompetitor}.",
                 "Udah coba {subjek}, nyesel. Jangan beli.",
                 "Overhype banget {subjek}, gak ada yang baru.",
                 "Harga segitu buat {subjek}? Lewat."],
        "neg": ["Kurang yakin sama {subjek}, tunggu review dulu.",
                "{subjek} kayaknya belum matang deh.",
                "Fiturnya biasa aja, kenapa harus ganti dari {kompetitor}?",
                "Penasaran tapi harganya bikin ragu."],
        "neu": ["Ada yang udah coba {subjek}? Gimana?",
                "Baru liat iklan {subjek}. Menarik sih, tapi...",
                "{subjek} ini bedanya apa sama {kompetitor}?",
                "Nunggu harga turun dulu baru beli {subjek}."],
        "pos": ["{subjek} lumayan juga ternyata.",
                "Kayaknya bakal coba {subjek} minggu ini.",
                "Fitur {subjek} cukup beda, menarik.",
                "Review {subjek} kebanyakan bagus ya."],
        "vpos": ["{subjek} game changer! Wajib coba.",
                 "Udah beli {subjek}, puas banget. Rekomen!",
                 "Akhirnya ada {subjek}. Ini yang ditunggu-tunggu.",
                 "Pindah dari {kompetitor} ke {subjek}, gak nyesel."],
    },
)


# ---------------------------------------------------------------- Kebijakan
def _kebijakan_impact(p):
    return _clip(p["dampak"] / 10 * 0.8 + (p["komunikasi"] - 5) / 10 * 0.3 + (p["keadilan"] - 5) / 10 * 0.5)


def _kebijakan_recs(s):
    r = []
    if s["params"]["komunikasi"] <= 4:
        r.append("Komunikasi lemah memperbesar penolakan. Uji 'Sosialisasi besar-besaran' sebelum kebijakan berlaku.")
    p = s["seg"].get("pekerja")
    if p and p["op"] < -0.2:
        r.append("Pekerja & kelas menengah paling terdampak. Pertimbangkan kompensasi atau masa transisi untuk mereka.")
    if s["final"]["polar"] > 0.5:
        r.append("Opini terbelah tajam. Libatkan tokoh yang dipercaya kedua kubu, bukan hanya pendukung.")
    if s["final"]["neg_action"] > 0.1:
        r.append("Potensi protes nyata. Siapkan kanal aspirasi resmi agar keberatan tersalur tanpa eskalasi.")
    return r


KEBIJAKAN = dict(
    key="kebijakan", label="Kebijakan / aturan baru", subject_label="Nama kebijakan", subject_default="Kebijakan baru",
    competitor=False,
    params=[
        {"key": "dampak", "label": "Dampak ekonomi ke warga (-10 rugi - 10 untung)", "min": -10, "max": 10, "default": -3},
        {"key": "komunikasi", "label": "Kualitas komunikasi / sosialisasi (0-10)", "min": 0, "max": 10, "default": 4},
        {"key": "keadilan", "label": "Dirasa adil (0-10)", "min": 0, "max": 10, "default": 5},
        dict(AWARENESS, default=60),
    ],
    impact=_kebijakan_impact,
    controversy=lambda p: min(1.0, 0.3 + abs(p["dampak"]) / 20 + (10 - p["keadilan"]) / 30),
    neg_mult=lambda p: 0.7,
    pos_mult=lambda p: 0.6,
    neg_label="Ikut protes / petisi", pos_label="Mendukung terbuka",
    segments=[
        _seg("pendukung", "Pendukung pemerintah", 0.20, 0.45, 0.4, 0.75, 0.12, 0.4, 0.8),
        _seg("oposisi", "Oposisi", 0.20, -0.45, 0.5, 0.8, 0.18, 0.35, 0.1),
        _seg("pekerja", "Pekerja & kelas menengah", 0.30, 0.0, 1.2, 0.4, 0.1, 0.6, 0.4),
        _seg("pengusaha", "Pelaku usaha", 0.10, 0.05, 1.0, 0.5, 0.1, 0.5, 0.5),
        _seg("apatis", "Netral / apatis", 0.15, 0.0, 0.5, 0.5, 0.03, 0.7, 0.7),
        _seg("media", "Media & akademisi", 0.05, 0.0, 0.7, 0.5, 0.5, 0.5, 0.6, hub=True),
    ],
    events=[
        {"name": "Sosialisasi besar-besaran", "effect": 0.2, "target": "all", "aw": 0.3},
        {"name": "Kebijakan direvisi / dilunakkan", "effect": 0.35, "target": "all", "aw": 0.2},
        {"name": "Demo besar diberitakan", "effect": -0.25, "target": "all", "aw": 0.3},
        {"name": "Hoaks menyebar", "effect": -0.3, "target": "apatis", "aw": 0.2},
        {"name": "Tokoh publik mendukung", "effect": 0.25, "target": "all", "aw": 0.15},
        {"name": "Kasus penyalahgunaan terungkap", "effect": -0.4, "target": "all", "aw": 0.25},
    ],
    recs=_kebijakan_recs,
    templates={
        "vneg": ["{subjek} ini jelas merugikan rakyat kecil. Tolak!",
                 "Ayo tanda tangan petisi tolak {subjek}.",
                 "Yang bikin {subjek} pernah mikirin kita gak sih?",
                 "{subjek} = beban baru. Kami turun ke jalan."],
        "neg": ["{subjek} kok terburu-buru ya, kajiannya mana?",
                "Kurang setuju sama {subjek}, dampaknya ke kami berat.",
                "Semoga {subjek} ditinjau ulang.",
                "Sosialisasi {subjek} minim banget, bingung."],
        "neu": ["Ada yang paham isi {subjek} sebenarnya apa?",
                "Tunggu aturan turunan {subjek} dulu deh.",
                "Pro kontra {subjek} rame banget di TL.",
                "Baca-baca soal {subjek}, masih belum kebayang dampaknya."],
        "pos": ["{subjek} ada bagusnya juga kalau dijalankan benar.",
                "Setuju dengan tujuan {subjek}, tinggal eksekusinya.",
                "Menurutku {subjek} langkah yang perlu.",
                "Data menunjukkan {subjek} bisa membantu jangka panjang."],
        "vpos": ["Dukung penuh {subjek}! Sudah lama ditunggu.",
                 "{subjek} langkah berani dan tepat.",
                 "Yang nolak {subjek} coba baca dulu isinya deh.",
                 "Akhirnya ada {subjek}. Semoga konsisten."],
    },
)


# ---------------------------------------------------------- Kampanye marketing
def _kampanye_impact(p):
    return _clip((p["kreativitas"] / 10 - 0.4) * 0.6 + (p["relevansi"] / 10 - 0.4) * 0.8 - p["kontroversi"] / 10 * 0.3)


def _kampanye_recs(s):
    r = []
    if s["final"]["aware"] < 0.5:
        r.append(f"Jangkauan organik hanya {s['final']['aware']:.0%}. Kampanye perlu dorongan: iklan berbayar atau kolaborasi influencer.")
    if s["params"]["kontroversi"] >= 6:
        r.append("Kontroversi tinggi menaikkan jangkauan tapi juga memancing boikot. Siapkan respons krisis sebelum tayang.")
    t = s["seg"].get("target")
    if t and t["op"] < 0.2:
        r.append("Target audiens belum tersentuh. Pesan kurang relevan untuk mereka, uji naikkan relevansi.")
    sk = s["seg"].get("skeptis")
    if sk and sk["neg"] > 0.25:
        r.append("Haters aktif memboikot. Jangan diladeni frontal; respons dengan humor atau abaikan.")
    return r


KAMPANYE = dict(
    key="kampanye", label="Kampanye marketing", subject_label="Nama brand / kampanye", subject_default="Kampanye kami",
    competitor=False,
    params=[
        {"key": "kreativitas", "label": "Kreativitas (0-10)", "min": 0, "max": 10, "default": 6},
        {"key": "relevansi", "label": "Relevansi dengan target (0-10)", "min": 0, "max": 10, "default": 6},
        {"key": "kontroversi", "label": "Kontroversi (0-10)", "min": 0, "max": 10, "default": 3},
        dict(AWARENESS, default=15),
    ],
    impact=_kampanye_impact,
    controversy=lambda p: p["kontroversi"] / 10,
    neg_mult=lambda p: 0.4 + p["kontroversi"] / 10,
    pos_mult=lambda p: 0.5 + p["relevansi"] / 10,
    neg_label="Boikot / mengkritik", pos_label="Tertarik / membeli",
    segments=[
        _seg("target", "Target audiens", 0.35, 0.1, 1.2, 0.4, 0.12, 0.6, 0.4),
        _seg("umum", "Publik umum", 0.35, 0.0, 0.6, 0.5, 0.05, 0.6, 0.6),
        _seg("fans", "Fans brand", 0.12, 0.45, 0.7, 0.6, 0.2, 0.5, 0.9),
        _seg("skeptis", "Skeptis / haters", 0.13, -0.4, 0.8, 0.8, 0.2, 0.35, 0.1),
        _seg("influencer", "Influencer", 0.05, 0.05, 1.0, 0.5, 0.5, 0.5, 0.4, hub=True),
    ],
    events=[
        {"name": "Influencer besar repost", "effect": 0.3, "target": "all", "aw": 0.3},
        {"name": "Dituduh plagiat / kontroversi", "effect": -0.4, "target": "all", "aw": 0.25},
        {"name": "Brand merespons dengan humor", "effect": 0.25, "target": "all", "aw": 0.1},
        {"name": "Giveaway", "effect": 0.3, "target": "target", "aw": 0.2},
        {"name": "Iklan berbayar diperluas", "effect": 0.0, "target": "all", "aw": 0.4},
    ],
    recs=_kampanye_recs,
    templates={
        "vneg": ["Iklan {subjek} ini cringe parah. Unfollow.",
                 "Boikot {subjek}! Gak sensitif banget.",
                 "Siapa yang approve kampanye {subjek} ini sih?",
                 "{subjek} makin aneh aja. Gak bakal beli lagi."],
        "neg": ["Hmm kampanye {subjek} kurang ngena.",
                "Maksudnya {subjek} apa ya? Gak nangkep.",
                "{subjek} kebanyakan gimmick.",
                "Biasa aja sih iklan {subjek}."],
        "neu": ["Baru liat iklan {subjek} di mana-mana.",
                "Ada yang ikutan promo {subjek}?",
                "{subjek} lagi rame ya?",
                "Iklan {subjek} lumayan, tapi produknya gimana?"],
        "pos": ["Kampanye {subjek} kreatif juga.",
                "Suka konsep iklan {subjek} kali ini.",
                "Jadi pengen coba {subjek}.",
                "Iklan {subjek} relate banget."],
        "vpos": ["Iklan {subjek} the best tahun ini!",
                 "Langsung checkout {subjek}. Marketingnya juara.",
                 "Tim kreatif {subjek} pantas dikasih bonus.",
                 "Share ah, iklan {subjek} keren banget."],
    },
)


# ------------------------------------------------------------------ Umum
def _umum_recs(s):
    r = []
    if s["final"]["polar"] > 0.5:
        r.append("Opini terbelah tajam. Cari pesan yang bisa diterima kedua kubu.")
    if s["final"]["neg_action"] > 0.1:
        r.append("Penentang aktif cukup banyak. Siapkan respons untuk keberatan utama mereka.")
    if s["final"]["aware"] < 0.5:
        r.append("Isu belum menyebar luas. Kalau ingin dikenal, perlu dorongan jangkauan.")
    return r


UMUM = dict(
    key="umum", label="Isu umum (bebas)", subject_label="Nama isu / topik", subject_default="Isu ini",
    competitor=False,
    params=[
        {"key": "dampak", "label": "Dampak ke publik (-10 buruk - 10 baik)", "min": -10, "max": 10, "default": 0},
        {"key": "kontroversi", "label": "Kontroversi (0-10)", "min": 0, "max": 10, "default": 5},
        dict(AWARENESS, default=30),
    ],
    impact=lambda p: _clip(p["dampak"] / 10),
    controversy=lambda p: p["kontroversi"] / 10,
    neg_mult=lambda p: 0.6,
    pos_mult=lambda p: 0.6,
    neg_label="Menentang aktif", pos_label="Mendukung aktif",
    segments=[
        _seg("pendukung", "Cenderung mendukung", 0.25, 0.4, 0.6, 0.7, 0.12, 0.45, 0.6),
        _seg("penentang", "Cenderung menentang", 0.25, -0.4, 0.6, 0.7, 0.12, 0.45, 0.2),
        _seg("netral", "Mayoritas netral", 0.45, 0.0, 1.0, 0.4, 0.06, 0.7, 0.5),
        _seg("influencer", "Influencer & media", 0.05, 0.0, 0.8, 0.5, 0.5, 0.5, 0.5, hub=True),
    ],
    events=[
        {"name": "Berita positif", "effect": 0.3, "target": "all", "aw": 0.2},
        {"name": "Berita negatif", "effect": -0.3, "target": "all", "aw": 0.2},
        {"name": "Klarifikasi resmi", "effect": 0.15, "target": "all", "aw": 0.15},
    ],
    recs=_umum_recs,
    templates={
        "vneg": ["{subjek} ini gak bisa dibiarkan.", "Tolak keras {subjek}.", "{subjek} jelas salah besar."],
        "neg": ["Kurang setuju soal {subjek}.", "{subjek} banyak masalahnya.", "Ragu sama {subjek}."],
        "neu": ["Ada yang bisa jelasin {subjek}?", "Rame soal {subjek} ya.", "Masih nyimak soal {subjek}."],
        "pos": ["{subjek} ada benarnya.", "Cukup setuju soal {subjek}.", "{subjek} layak didukung."],
        "vpos": ["Dukung penuh {subjek}!", "{subjek} memang yang terbaik.", "Semua harus tahu soal {subjek}."],
    },
)


PRESETS = {p["key"]: p for p in (HARGA, PRODUK, KEBIJAKAN, KAMPANYE, UMUM)}


def public_presets():
    """Versi preset yang aman dikirim ke browser (tanpa fungsi)."""
    out = []
    for p in PRESETS.values():
        out.append({
            "key": p["key"], "label": p["label"],
            "subject_label": p["subject_label"], "subject_default": p["subject_default"],
            "competitor": p["competitor"], "competitor_default": p.get("competitor_default", ""),
            "params": p["params"], "events": p["events"],
            "segments": [{"key": s["key"], "label": s["label"]} for s in p["segments"]],
            "neg_label": p["neg_label"], "pos_label": p["pos_label"],
        })
    return out
