"""
Satu dunia twin: hari demi hari, tick demi tick.

URUTAN SATU HARI
  1. Pagi: lingkungan bergerak -- faktor IHSG hari ini (potongan sejarah
     IHSG asli), nilai wajar tiap saham (beta x faktor + berita sendiri,
     berita membesar saat saham ramai), sentimen, selera risiko asing,
     beda tafsir antar-pemain nilai, lalu guncangan skenario hari itu.
     Kalau agen pemimpin aktif, di sini mereka berkonsultasi ke Claude.
  2. Papan harga hari itu: semua harga sah antara ARB dan ARA dari harga
     penutupan kemarin.
  3. K lelang batch: tick 0 = pra-pembukaan, tick K-1 = pra-penutupan, di
     antaranya sesi berjalan. Tiap tick: agen memutuskan, order dikliring
     per saham, kas & saham berpindah. Order agen yang belum terisi
     BERTAHAN di antrean sampai diganti / kedaluwarsa / harga menjauh, dan
     dibuang saat tutup (order harian).
  4. Tutup: OHLC, arus tiap kelompok, posisi bandar, antrean tersisa.

TIGA PELAJARAN YANG MEMBENTUK MESIN INI (semua terukur, lihat rapor)
  - Antrean harus diisi ORDER RITEL yang menunggu, bukan penyedia
    likuiditas buatan: hanya dengan begitu ritel jadi pihak yang "diangkat"
    di hari naik (data asli: arus ritel vs return hari yang sama -0,2..-0,55).
  - Berita publik harus terserap di hari yang sama: profesional menggeser
    acuan pra-pembukaannya ke berita semalam. Tanpa itu 15-20% berita baru
    terserap besoknya dan return harian bisa ditebak dari kemarin.
  - Ritel dua-arah di hari biasa (|netto|/bruto 4-28% di JSON broker), tapi
    seragam saat saham ramai atau ceritanya kencang (herding bergantung
    rezim) -- sumber FOMO, ekor gemuk, dan dinamika gorengan.

IHSG TWIN
Sisa pasar (yang tidak disimulasikan) ikut faktor IHSG; saham yang
disimulasikan ikut harganya sendiri, ditimbang kapitalisasi KSEI-nya.
Jadi kalau BBCA ambruk di twin, IHSG twin ikut tertarik sesuai bobot
BBCA -- tapi 7-8 saham tidak bisa "menggerakkan" sisa pasar.

ANGKA ACAK
Sumber terpisah: lingkungan (IHSG, berita), agen umum (ukuran tetap per
tick), tafsir & program (ukuran tetap per hari), dan satu generator per
agen khusus (bandar/penjual) -- yang terakhir supaya bandar yang muncul
karena skenario tidak menggeser urutan angka acak agen lain. Akibatnya
skenario kosong memberi dunia yang identik bit demi bit dengan baseline.
"""
import numpy as np

from . import aturan
from .agen import bangun_populasi, T, G, GRUP, TIPE_UMUM
from .buku import lelang, sisa_buku

KURVA_INTRADAY = np.array([1.6, 1.25, 1.05, 0.9, 0.8, 0.8, 0.9, 1.0, 1.15, 1.55])
N_BUKU = 10            # level antrean yang direkam per sisi
LEVEL_CEPAT = 5        # jumlah level kutipan pedagang cepat per sisi
GESER_BERITA = 0.9     # porsi berita publik semalam yang langsung tercermin di acuan pra-pembukaan
URGENSI = 3.0          # seberapa cepat pemain nilai datang saat harga jauh dari nilai wajar
SKALA_CELAH = 2.5      # salah harga sebesar SKALA_CELAH x volatilitas harian = celah 1
GESER_PERSEDIAAN = 1   # pedagang cepat menggeser kutipan kalau persediaannya menyimpang >25%
UMUR_ANTRE = 5         # order agen yang tidak terisi bertahan sekian lelang, lalu dibatalkan
JAUH_ANTRE = 12        # ...atau dibatalkan kalau harga sudah menjauh lebih dari sekian fraksi
PERHATIAN_INFO = 0.4   # tambahan intensitas berita per satuan keramaian saham


def _kurva(K):
    x = np.linspace(0, len(KURVA_INTRADAY) - 1, K)
    k = np.interp(x, np.arange(len(KURVA_INTRADAY)), KURVA_INTRADAY)
    return k / k.mean()


class Dunia:
    def __init__(self, prof, cfg, seed, events=None, kal=None, n_cadangan=0, rekam_agen=False):
        self.prof = prof
        self.cfg = cfg
        self.kodes = list(cfg['kodes'])
        self.S = S = len(self.kodes)
        self.K = int(cfg.get('tick', 10))
        self.burn = int(cfg.get('burn', 10))
        self.D = int(cfg.get('hari', 60))
        self.events = list(events or [])
        self.kal = kal or {}
        self.kurva = _kurva(self.K)
        self.rekam_agen = rekam_agen
        # agen pemimpin (Claude) -- opsional, lihat llm.py
        self.pakai_llm = bool(int(cfg.get('pakai_llm') or 0))
        self.k_llm = max(int(cfg.get('k_llm') or 10), 3)
        self.pemimpin = []
        self.log_pemimpin = []
        self.program_paksa = {}

        ps = [prof['saham'][k] for k in self.kodes]
        self.ps = ps
        self.P0 = np.array([p['harga'] for p in ps], dtype=float)
        self.sigma = np.array([max((p.get('fakta') or {}).get('vol_harian') or 0.025, 0.008) for p in ps])
        self.beta = np.array([p['beta'] for p in ps])
        self.adv = np.array([p['adv_lot'] for p in ps])
        self.sektor = [p.get('sektor', '-') for p in ps]
        ih = prof['ihsg']
        self.sigma_m = float(ih['vol_harian'])

        # -- bobot IHSG twin dari kapitalisasi KSEI
        mcap_total = (prof.get('pasar') or {}).get('mcap_total') or 0
        mcap = np.array([((p.get('pemilik') or {}).get('mcap') or 0.0) for p in ps])
        self.bobot_ihsg = mcap / mcap_total if mcap_total else np.zeros(S)
        self.bobot_sisa = 1.0 - self.bobot_ihsg.sum()
        self.ihsg0 = float(ih['level'])

        # -- generator angka acak
        self.rng_env = np.random.default_rng([seed, 11])
        self.rng_agen = np.random.default_rng([seed, 22])
        self.rng_nu = np.random.default_rng([seed, 44])
        self.seed = seed
        rng_pop = np.random.default_rng([seed, 33])

        self.pop, self.info = bangun_populasi(prof, self.kodes, cfg, rng_pop, n_cadangan)
        self.N = self.pop.n
        self.umum = np.flatnonzero(np.isin(self.pop.tipe, TIPE_UMUM))
        self.ritel_mask_umum = self.pop.grup[self.umum] == G['ritel']
        self.cepat = np.array(self.info['indeks']['cepat'], dtype=np.int64)
        self.cadangan = list(self.info['cadangan'])

        # pengali kalibrasi mikro
        mult = np.ones((len(GRUP), S))
        for g, per in (self.kal.get('mult') or {}).items():
            for k, v in per.items():
                if k in self.kodes and g in G:
                    mult[G[g], self.kodes.index(k)] = v
        self.nilai_order = self.info['nilai_order'] * mult
        derau_mult = self.kal.get('derau') or {}
        for g, v in derau_mult.items():
            if g in G:
                self.pop.derau[self.pop.grup == G[g]] *= v
        self.dalam_mult = np.array([(self.kal.get('dalam') or {}).get(k, 1.0) for k in self.kodes])
        self.k_fund = np.array([(self.kal.get('k_fund') or {}).get(k, 0.8) for k in self.kodes])

        # kedalaman kutipan pedagang cepat per level (lot), sebelum pengali
        dasar = []
        for p in ps:
            b = p.get('buku_nyata')
            if b:
                dasar.append(0.5 * 0.5 * (b['dalam_5_bid_lot'] + b['dalam_5_offer_lot']) / 5.0)
            else:
                dasar.append(0.5 * 0.12 * p['adv_lot'] / 5.0)
        self.dalam_dasar = np.array(dasar)
        saham_cepat = {}
        for j, v in self.info['cakupan_cepat'].items():
            for a in v:
                saham_cepat[int(a)] = int(j)
        self.cepat_saham = np.array([saham_cepat[int(a)] for a in self.cepat], dtype=np.int64)
        self.cepat_per_saham = np.maximum(np.bincount(self.cepat_saham, minlength=S), 1)
        self.inv0_cepat = self.pop.pos.copy()
        self.program = np.zeros_like(self.pop.nu)
        self.nu_sd = np.where(np.abs(self.pop.nu).sum(axis=1, keepdims=True) > 0,
                              np.std(self.pop.nu, axis=1, keepdims=True) + 1e-9, 0.0)

        # -- volatilitas idiosinkratik: sisa dari total setelah bagian pasar
        idio2 = self.sigma ** 2 - (self.beta * self.sigma_m) ** 2
        self.sigma_idio = np.sqrt(np.maximum(idio2, 0.25 * self.sigma ** 2))

        self._bangkitkan_lingkungan()
        if self.pakai_llm:
            self._pilih_pemimpin()

        # -- keadaan
        self.harga = self.P0.copy()
        self.tutup_kemarin = self.P0.copy()
        self.riwayat_tutup = [self.P0.copy() for _ in range(25)]
        self.V = self.P0 * np.exp(0.01 * self.rng_env.standard_normal(S))
        self.V_kemarin = self.V.copy()
        self.riwayat_V = [self.V.copy() for _ in range(25)]
        self.sent_saham = np.zeros(S)
        self.sent_pasar = 0.0
        self.R = 0.0                 # selera risiko asing (0 = netral)
        self.risiko_lokal = 0.0      # selera risiko institusi lokal
        self.buzz = np.zeros(S)
        self.gejolak = np.ones(S)    # EMA |return| / sigma, 1 = normal
        self.kerumunan = np.zeros(S)
        self.panik_mult = 1.0
        self.likuid = np.ones(S)
        self.F = 1.0                 # indeks faktor sisa pasar
        self.ihsg_riwayat = [self.ihsg0] * 21
        self.geser_berita = np.zeros(S, dtype=np.int64)
        self.antre = self._antre_kosong()
        self.tick_abs = 0
        self.efek = {}               # efek skenario yang sedang berlangsung
        # Modal/barang yang masuk SETELAH kekayaan awal dipotret (bandar &
        # pemegang pasokan dari skenario). Tanpa ini setoran mereka terbaca
        # sebagai "untung": bandar skenario sempat tercatat +21%.
        self.setoran = np.zeros(self.N)
        self.kekayaan_awal = None
        self.bandar = []
        self.penjual = []
        self.program_asing = []
        self.hari_ini = 0
        for i, j in enumerate(self.info['saham_bandar']):
            a = self.info['indeks']['bandar'][i]
            self._pasang_bandar(a, j, besar=1.0, fase='siaga', otomatis=True)

        # -- rekaman
        H = self.burn + self.D
        self.rek = {
            'open': np.zeros((H, S)), 'high': np.zeros((H, S)), 'low': np.zeros((H, S)),
            'close': np.zeros((H, S)), 'vol': np.zeros((H, S)), 'nilai': np.zeros((H, S)),
            'beli': np.zeros((H, len(GRUP), S)), 'jual': np.zeros((H, len(GRUP), S)),
            'beli_nilai': np.zeros((H, len(GRUP), S)), 'jual_nilai': np.zeros((H, len(GRUP), S)),
            'ihsg': np.zeros(H), 'V': np.zeros((H, S)), 'sent': np.zeros((H, S)),
            'ara': np.zeros((H, S), dtype=bool), 'arb': np.zeros((H, S), dtype=bool),
            'bid': np.zeros((H, S, N_BUKU)), 'offer': np.zeros((H, S, N_BUKU)),
            'bid_harga': np.zeros((H, S, N_BUKU)), 'offer_harga': np.zeros((H, S, N_BUKU)),
            'R': np.zeros(H), 'sent_pasar': np.zeros(H),
            'tick_harga': np.zeros((H, self.K, S)),
        }
        self.rek_bandar = []
        self.kekayaan_awal = None

    # ------------------------------------------------------------ lingkungan
    def _bangkitkan_lingkungan(self):
        """Faktor IHSG + berita, dibangkitkan SEKALI per seed dan identik di
        baseline maupun skenario.

        Faktor IHSG = SATU POTONGAN UTUH sejarah IHSG asli (2016-sekarang)
        yang dimulai di posisi acak, dibuang rata-ratanya (tanpa tren
        bawaan), lalu diskalakan ke volatilitas rezim yang dipilih. Potongan
        utuh, bukan blok-blok yang diacak: mengacak blok memutus rezim
        gejolak -- terukur ACF |m| turun dari 0,19 (IHSG asli) ke 0,06.
        Bentuknya (ekor, gejolak mengumpul, minggu-minggu panik) dari
        sejarah; besarnya dari rezim sekarang (2 tahun terakhir), atau
        0,7x / 1,6x untuk rezim tenang / bergejolak."""
        H = self.burn + self.D
        rng = self.rng_env
        ret = np.asarray(self.prof['ihsg']['ret'], dtype=float)
        ret = ret[np.isfinite(ret)]
        if len(ret) < H + 20:
            ret = np.tile(ret, int(np.ceil((H + 20) / max(len(ret), 1))) + 1)
        i = int(rng.integers(0, len(ret) - H))
        potong = ret[i:i + H].copy()
        potong = potong - potong.mean()
        skala_rezim = {'tenang': 0.7, 'campur': 1.0, 'gejolak': 1.6}.get(self.cfg.get('rezim', 'campur'), 1.0)
        sd = potong.std()
        self.m = potong / sd * self.sigma_m * skala_rezim if sd > 0 else potong
        self.m_asal = (self.prof['ihsg']['tanggal'][i] if i < len(self.prof['ihsg']['tanggal']) else None,
                       self.prof['ihsg']['tanggal'][min(i + H, len(self.prof['ihsg']['tanggal']) - 1)])
        # berita idiosinkratik: harian ekor-t (df 4) + lompatan jarang
        t4 = rng.standard_t(4, size=(H, self.S)) / np.sqrt(2.0)
        self.e_fund = t4
        # lompatan berita: jarang (1 per ~25 hari bursa), besarnya 1,5 + eksponensial
        # (rata-rata 1,2) kali volatilitas idiosinkratik, dibatasi 6x -- untuk BBCA
        # sekitar 2-5%, paling ekstrem ~9%. Dulu normal x3 tanpa batas, dan satu
        # undian +16% sehari di BBCA cukup untuk menyeret kalibrasi mikro.
        lompat = rng.random((H, self.S)) < (1.0 / 25.0)
        arah = np.where(rng.random((H, self.S)) < 0.5, -1.0, 1.0)
        besar = np.minimum(1.5 + rng.exponential(1.2, size=(H, self.S)), 6.0)
        self.lompatan = lompat * arah * besar
        self.derau_sent = 0.15 * rng.standard_normal(H)
        self.derau_R = 0.12 * rng.standard_normal(H)

    # -------------------------------------------------------- agen pemimpin
    def _pilih_pemimpin(self):
        """Satu dana asing dan satu institusi lokal terbesar jadi pemimpin:
        ukurannya dibesarkan (dana besar menggerakkan harga) dan niat
        programnya ditentukan Claude, bukan undian AR(1)."""
        pop = self.pop
        kaya = pop.kas + (pop.pos * self.P0[None, :] * aturan.LOT).sum(axis=1)
        for nama in ('asing', 'institusi'):
            idx = np.flatnonzero(pop.tipe == T[nama])
            if not len(idx):
                continue
            a = int(idx[np.argmax(kaya[idx])])
            pop.skala[a] *= 3.0
            pop.aktif[a] *= 1.5
            pop.w_prog[a] = 1.2
            self.pemimpin.append({'a': a, 'jenis': nama})

    def _ringkasan_pemimpin(self, p, d):
        pop = self.pop
        h = d - self.burn
        rt = self.riwayat_tutup
        ih = self.ihsg_riwayat
        berita = []
        for ev in self.events:
            if ev['hari'] <= h < ev['hari'] + ev['durasi'] or h == ev['hari'] + (ev.get('bantah_hari') or -999):
                from .skenario import JENIS
                berita.append('%s di %s (mulai hari %d)' % (JENIS[ev['jenis']]['label'], ', '.join(ev['target_kode']), ev['hari']))
        B = self.burn
        lima = slice(max(d - 5, 0), d)
        net = (self.rek['beli_nilai'][lima] - self.rek['jual_nilai'][lima]).sum(axis=0) / 1e9
        ring = {
            'hari_simulasi': h,
            'ihsg': {'level': round(ih[-1], 1), 'ret_5h_pct': round((ih[-1] / ih[-6] - 1) * 100, 2),
                     'ret_20h_pct': round((ih[-1] / ih[-21] - 1) * 100, 2)},
            'berita_aktif': berita,
            'kas_rp_miliar': round(float(pop.kas[p['a']]) / 1e9, 1),
        }
        if p['jenis'] == 'bandar':
            b = p['b']
            j, a = b['s'], b['a']
            inv = int(pop.pos[a, j])
            modal = pop.biaya[a, j] / (inv * aturan.LOT) if inv > 0 else None
            ring.update({
                'saham': self.kodes[j], 'fase_sekarang': b['fase'], 'hari_di_fase': b['hari_fase'],
                'harga': float(self.harga[j]),
                'ret_1h_pct': round((rt[-1][j] / rt[-2][j] - 1) * 100, 2),
                'ret_5h_pct': round((rt[-1][j] / rt[-6][j] - 1) * 100, 2),
                'barang_lot': inv, 'barang_hari_volume': round(inv / max(self.adv[j], 1), 2),
                'modal_rata': None if modal is None else round(modal, 1),
                'untung_rugi_pct': None if modal is None else round((self.harga[j] / modal - 1) * 100, 2),
                'sentimen_saham': round(float(self.sent_saham[j]), 2),
                'keramaian': round(float(self.buzz[j]), 2),
                'arus_ritel_5h_rp_miliar': round(float(net[G['ritel'], j]), 1),
                'arus_asing_5h_rp_miliar': round(float(net[G['asing'], j]), 1),
            })
            return ring
        a = p['a']
        saham = []
        for j, k in enumerate(self.kodes):
            pos = int(pop.pos[a, j])
            modal = pop.biaya[a, j] / (pos * aturan.LOT) if pos > 0 else None
            saham.append({
                'kode': k, 'sektor': self.sektor[j], 'harga': float(self.harga[j]),
                'ret_1h_pct': round((rt[-1][j] / rt[-2][j] - 1) * 100, 2),
                'ret_5h_pct': round((rt[-1][j] / rt[-6][j] - 1) * 100, 2),
                'ret_20h_pct': round((rt[-1][j] / rt[-21][j] - 1) * 100, 2),
                'perkiraan_nilai_wajar_vs_harga_pct': round((self.V[j] * np.exp(pop.nu[a, j]) / self.harga[j] - 1) * 100, 1),
                'arus_asing_5h_rp_miliar': round(float(net[G['asing'], j]), 1),
                'arus_ritel_5h_rp_miliar': round(float(net[G['ritel'], j]), 1),
                'sentimen_saham': round(float(self.sent_saham[j]), 2),
                'posisi_lot': pos,
                'untung_rugi_posisi_pct': None if modal is None else round((self.harga[j] / modal - 1) * 100, 2),
            })
        ring['saham'] = saham
        return ring

    def _konsultasi_pemimpin(self, d):
        from . import llm
        semua = list(self.pemimpin) + [{'a': b['a'], 'jenis': 'bandar', 'b': b}
                                       for b in self.bandar if b.get('dipimpin_llm')]
        if not semua:
            return
        daftar = [{'jenis': p['jenis'], 'kodes': self.kodes, 'ringkasan': self._ringkasan_pemimpin(p, d)}
                  for p in semua]
        keputusan = llm.putuskan_pemimpin(daftar)
        for p, kp in zip(semua, keputusan):
            catat = {'hari': d - self.burn, 'jenis': p['jenis'], 'agen': p['a']}
            if not kp or kp.get('galat'):
                catat['galat'] = (kp or {}).get('galat', 'tanpa jawaban')
                self.log_pemimpin.append(catat)
                continue
            catat['alasan'] = kp.get('alasan', '')
            if p['jenis'] == 'bandar':
                self._terapkan_langkah_bandar(p['b'], kp.get('langkah'))
                catat['keputusan'] = kp.get('langkah')
                catat['kode'] = self.kodes[p['b']['s']]
            else:
                nilai = np.zeros(self.S)
                for x in kp.get('sikap') or []:
                    if x.get('kode') in self.kodes:
                        nilai[self.kodes.index(x['kode'])] = 1.5 * llm.NILAI_SIKAP.get(x.get('sikap'), 0.0)
                self.program_paksa[p['a']] = nilai
                self.program[p['a']] = nilai
                catat['keputusan'] = {x.get('kode'): x.get('sikap') for x in kp.get('sikap') or []}
            self.log_pemimpin.append(catat)

    def _terapkan_langkah_bandar(self, b, langkah):
        inv = self.pop.pos[b['a'], b['s']]
        P = self.harga[b['s']]
        if langkah == 'tunggu' and b['fase'] != 'siaga':
            self._ganti_fase(b, 'siaga')
        elif langkah == 'akumulasi' and b['fase'] != 'akumulasi':
            self._ganti_fase(b, 'akumulasi')
            b['plafon'] = b['plafon_awal'] = P * 1.06
        elif langkah == 'markup' and b['fase'] != 'markup' and inv > 0:
            self._ganti_fase(b, 'markup')
            b['harga_awal_markup'] = P
        elif langkah == 'distribusi' and b['fase'] != 'distribusi' and inv > 0:
            self._ganti_fase(b, 'distribusi')
            b['puncak_inv'] = float(inv)
            b['puncak_harga'] = P
        elif langkah == 'buang' and b['fase'] != 'buang' and inv > 0:
            self._mulai_buang(b, inv)

    # --------------------------------------------------------------- bandar
    # Siklus bandar: SIAGA -> AKUMULASI -> MARKUP -> DISTRIBUSI -> BUANG -> SIAGA.
    #
    # Ukuran-ukurannya ditulis terang di sini karena tidak ada data yang bisa
    # mengkalibrasinya -- identitas bandar tidak terlihat di data broker (di
    # big cap broker lokal yang "kompak" ternyata Bahana/DX dkk.). Angkanya
    # dipilih supaya jejaknya masuk akal: akumulasi ~15-25% volume harian
    # selama 3-7 minggu, markup paling lama 2 minggu, distribusi paling lama
    # 5 minggu, buang 3-4 hari.
    def _pasang_bandar(self, a, j, besar=1.0, fase='akumulasi', otomatis=False, target_naik=None):
        pop = self.pop
        ps = self.ps[j]
        rng = np.random.default_rng([self.seed, 77, a])
        lama_akum = int(18 + rng.integers(0, 18))
        target_lot = float(besar * (0.15 + 0.10 * rng.random()) * ps['adv_lot'] * lama_akum)
        # modal: cukup untuk mengumpulkan target lalu mengangkat harga ~2x lagi
        modal = target_lot * self.harga[j] * aturan.LOT * 2.5
        pop.tipe[a] = T['bandar']
        pop.grup[a] = G['bandar']
        pop.aktif_slot[a] = True
        pop.kas[a] += modal
        if self.kekayaan_awal is not None:
            self.setoran[a] += modal
        pop.perhatian[a, :] = 0.0
        pop.perhatian[a, j] = 1.0
        b = {
            'a': int(a), 's': int(j), 'fase': fase, 'hari_fase': 0, 'rng': rng,
            'otomatis': otomatis, 'besar': float(besar),
            'target_lot': target_lot,
            'target_naik': float(target_naik if target_naik else 0.25 + 0.35 * rng.random()),
            'lama_akum': lama_akum,
            'plafon': self.harga[j] * 1.06 if fase == 'akumulasi' else None,
            'plafon_awal': self.harga[j] * 1.06,
            'puncak_inv': 0.0, 'puncak_harga': 0.0, 'istirahat': 0, 'jual_per_tick': 0.0,
            'dipimpin_llm': self.pakai_llm,
            'modal_awal': float(pop.kas[a] + pop.pos[a, j] * self.harga[j] * aturan.LOT),
        }
        self.bandar.append(b)
        return b

    def _ganti_fase(self, b, fase):
        b['fase'] = fase
        b['hari_fase'] = 0

    def _bandar_pagi(self, b):
        """Transisi fase bandar di awal hari."""
        pop, j = self.pop, b['s']
        a = b['a']
        inv = pop.pos[a, j]
        P = self.tutup_kemarin[j]
        modal_rata = pop.biaya[a, j] / (inv * aturan.LOT) if inv > 0 else P
        b['hari_fase'] += 1
        f = b['fase']
        if b.get('dipimpin_llm'):
            # langkah ditentukan Claude; yang tersisa cuma pengaman mekanis
            if f == 'buang' and inv <= 0:
                self._ganti_fase(b, 'siaga')
            elif f == 'markup' and pop.kas[a] < 0.03 * b['modal_awal']:
                self._ganti_fase(b, 'distribusi')
                b['puncak_inv'] = float(inv)
                b['puncak_harga'] = P
            elif f == 'markup':
                self.sent_saham[j] += 0.35 * b['besar']
            elif f == 'distribusi' and b['hari_fase'] <= 10:
                self.sent_saham[j] += 0.20 * b['besar']
            return
        if f == 'siaga':
            if b['istirahat'] > 0:
                b['istirahat'] -= 1
            elif b['otomatis'] and b['rng'].random() < 1.0 / 40.0:
                self._ganti_fase(b, 'akumulasi')
                b['plafon'] = b['plafon_awal'] = P * 1.06
        elif f == 'akumulasi':
            # plafon: paling tinggi 6% di atas harga awal akumulasi atau di atas
            # modal rata-rata (mana yang lebih besar) -- bandar mau membayar sedikit
            # lebih mahal kalau pasar ikut naik, tapi tidak mengejar
            b['plafon'] = max(b.get('plafon_awal') or P * 1.06, modal_rata * 1.06)
            cukup = inv >= 0.85 * b['target_lot']
            lewat = b['hari_fase'] > b['lama_akum']
            if cukup or (lewat and inv >= 0.4 * b['target_lot']):
                self._ganti_fase(b, 'markup')
                b['harga_awal_markup'] = P
            elif b['hari_fase'] > 1.5 * b['lama_akum']:
                self._mulai_buang(b, inv)                 # gagal mengumpulkan: mundur
        elif f == 'markup':
            # "cerita": markup hampir selalu dibarengi narasi (grup, media
            # sosial, rumor) -- sentimen saham ini didorong naik tiap hari
            self.sent_saham[j] += 0.35 * b['besar']
            awal = b.get('harga_awal_markup') or modal_rata
            if P >= awal * (1.0 + b['target_naik']) or b['hari_fase'] > 12 \
                    or pop.kas[a] < 0.03 * b['modal_awal']:
                self._ganti_fase(b, 'distribusi')
                b['puncak_inv'] = float(inv)
                b['puncak_harga'] = P
        elif f == 'distribusi':
            if b['hari_fase'] <= 10:
                self.sent_saham[j] += 0.20 * b['besar']
            b['puncak_harga'] = max(b['puncak_harga'], P)
            if inv <= 0.15 * max(b['puncak_inv'], 1) or b['hari_fase'] > 25 \
                    or P < modal_rata * 0.92:
                self._mulai_buang(b, inv)
        elif f == 'buang':
            if inv <= 0 or b['hari_fase'] > 8:
                self._ganti_fase(b, 'siaga')
                b['istirahat'] = int(20 + b['rng'].integers(0, 20))
                b['plafon'] = None

    def _mulai_buang(self, b, inv):
        self._ganti_fase(b, 'buang')
        # sisa barang dilepas rata dalam ~3 hari, bukan menyusut geometris
        b['jual_per_tick'] = max(float(inv) / (3.0 * self.K), 1.0)

    def _order_bandar(self, b, k, keluar):
        pop, j, a = self.pop, b['s'], b['a']
        rng = b['rng']
        u = rng.random(4)
        P = self.harga[j]
        inv = int(pop.pos[a, j])
        tick_vol = self.adv[j] / self.K
        acuan = self.ref_idx[j]
        f = b['fase']
        if f == 'akumulasi':
            sisa = max(b['target_lot'] - inv, 0.0)
            hari_sisa = max(b['lama_akum'] - b['hari_fase'] + 1, 3)
            q = sisa / hari_sisa / self.K * (0.6 + 0.8 * u[0])
            if b['plafon'] is not None and P > b['plafon']:
                # harga lewat plafon: berhenti membeli, sesekali pasang tembok offer
                # SATU fraksi di atas harga (penghalang, bukan untuk benar-benar
                # menjual -- paling banyak 1% barang)
                if inv > 0 and u[2] < 0.5:
                    keluar.append((a, j, -1, acuan + 1, min(0.01 * inv, 0.2 * tick_vol)))
            else:
                off = 0 if u[1] < 0.5 else -1
                keluar.append((a, j, 1, acuan + off, q))
        elif f == 'markup':
            # angkat satu fraksi; kalau ritel sudah mengejar sendiri, biarkan
            # mereka yang membayar kenaikannya
            if self.kerumunan[j] < 0.3:
                q = tick_vol * (0.2 + 0.4 * u[0]) * b['besar']
                keluar.append((a, j, 1, acuan + 1, q))
        elif f == 'distribusi':
            beli_agresif = self.agresif_beli_terakhir[j]
            if u[3] < 0.12 and b['hari_fase'] < 15:
                # cat tape: beli kecil yang agresif supaya grafik tetap "hidup"
                # dan pengejar tren datang -- lalu dijual ke mereka
                keluar.append((a, j, 1, acuan + 1, 0.3 * tick_vol))
            else:
                q = 0.3 * tick_vol * (0.5 + u[0]) + 0.8 * beli_agresif
                keluar.append((a, j, -1, acuan + (1 if u[1] < 0.5 else 0), min(q, inv)))
            if (P < 0.92 * b['puncak_harga'] and b['hari_fase'] <= 5 and u[2] < 0.4
                    and inv > 0.5 * b['puncak_inv']):
                # jaga harga sebentar: tembok bid KECIL supaya terlihat ada
                # penopang -- dulu 0,5x volume per lelang dan malah membuat
                # bandar terus membeli di fase yang seharusnya menjual
                keluar.append((a, j, 1, acuan - 2, 0.15 * tick_vol))
        elif f == 'buang':
            keluar.append((a, j, -1, acuan - 1, min(b['jual_per_tick'], inv)))

    # -------------------------------------------------------------- penjual
    def _pasang_penjual(self, j, besar, durasi):
        if not self.cadangan:
            return None
        a = self.cadangan.pop(0)
        pop = self.pop
        float_lot = (self.ps[j].get('pemilik') or {}).get('beredar_lot') or 150.0 * self.adv[j]
        lot = int(besar * float_lot)
        pop.tipe[a] = T['penjual']
        pop.grup[a] = G['penjual']
        pop.aktif_slot[a] = True
        pop.pos[a, j] += lot
        pop.biaya[a, j] += lot * self.harga[j] * aturan.LOT
        if self.kekayaan_awal is not None:
            self.setoran[a] += lot * self.harga[j] * aturan.LOT
        pop.perhatian[a, j] = 1.0
        p = {'a': a, 's': j, 'lot_awal': lot, 'sisa_hari': int(durasi),
             'rng': np.random.default_rng([self.seed, 88, a])}
        self.penjual.append(p)
        return p

    def _pasang_program_asing(self, j, rencana):
        """Agen 'program asing': mengeksekusi arus netto asing harian yang
        sudah ditentukan (rupiah per hari, + beli / - jual). Dipakai event MSCI
        mode putar ulang -- arus asingnya diputar apa adanya, agen lain bebas
        bereaksi. Saham yang dijual DIAMBIL dari pemegang asing yang sudah
        ada (tidak mencetak saham baru); kas untuk membeli disetor."""
        if not self.cadangan:
            return None
        a = self.cadangan.pop(0)
        pop = self.pop
        P = self.harga[j]
        jual_lot = int(sum(-v for v in rencana if v < 0) / (P * aturan.LOT) * 1.3)
        beli_rp = float(sum(v for v in rencana if v > 0) * 1.3)
        donor = np.flatnonzero((pop.tipe == T['asing']) & (pop.pos[:, j] > 0))
        if jual_lot > 0 and len(donor):
            tersedia = int(pop.pos[donor, j].sum())
            jual_lot = min(jual_lot, int(0.5 * tersedia))
            from .agen import _bagi_lot
            ambil = np.minimum(_bagi_lot(jual_lot, pop.pos[donor, j]), pop.pos[donor, j])
            modal = pop.biaya[donor, j] * ambil / np.maximum(pop.pos[donor, j], 1)
            pop.pos[donor, j] -= ambil
            pop.biaya[donor, j] -= modal
            pop.pos[a, j] += int(ambil.sum())
            pop.biaya[a, j] += float(modal.sum())
        pop.tipe[a] = T['penjual']
        pop.grup[a] = G['asing']
        pop.aktif_slot[a] = True
        pop.kas[a] += beli_rp
        if self.kekayaan_awal is not None:
            self.setoran[a] += beli_rp
        pop.perhatian[a, j] = 1.0
        p = {'a': a, 's': j, 'rencana': list(rencana), 'hari0': self.hari_ini}
        self.program_asing.append(p)
        return p

    def _order_program(self, p, keluar):
        t = self.hari_ini - p['hari0']
        if not 0 <= t < len(p['rencana']):
            return
        j, a = p['s'], p['a']
        nilai = p['rencana'][t] / self.K
        q = abs(nilai) / (self.harga[j] * aturan.LOT)
        if q < 1:
            return
        if nilai > 0:
            keluar.append((a, j, 1, self.ref_idx[j] + 1, q))
        else:
            keluar.append((a, j, -1, self.ref_idx[j] - 1, min(q, self.pop.pos[a, j])))

    def _order_penjual(self, p, keluar):
        if p['sisa_hari'] <= 0:
            return
        pop, j, a = self.pop, p['s'], p['a']
        inv = int(pop.pos[a, j])
        if inv <= 0:
            return
        u = p['rng'].random(2)
        q = p['lot_awal'] / (max(p['sisa_hari'], 1) * self.K) * (0.6 + 0.8 * u[0])
        q = max(q, inv / (max(p['sisa_hari'], 1) * self.K))
        keluar.append((a, j, -1, self.ref_idx[j] - (1 if u[1] < 0.5 else 0), min(q, inv)))

    # ------------------------------------------------------------ skenario
    def _skenario_pagi(self, d):
        from .skenario import terapkan
        hari_rekam = d - self.burn
        for ev in self.events:
            terapkan(self, ev, hari_rekam)

    # ------------------------------------------------------------- satu hari
    def _pagi(self, d):
        S = self.S
        self.hari_ini = d
        self.efek_m = 0.0
        self.R = 0.9 * self.R + self.derau_R[d]
        self.risiko_lokal = 0.9 * self.risiko_lokal + 0.5 * self.derau_R[d]
        self.panik_mult = 1.0
        self.likuid = np.ones(S)
        self.offset_R = 0.0
        self.offset_R_saham = np.zeros(S)   # selera asing per saham (event bertarget, MSCI)
        self.offset_lokal = 0.0
        self.offset_lokal_saham = np.zeros(S)   # selera institusi lokal per saham (indeks, dividen)
        self.offset_sent_pasar = 0.0
        self.offset_sent = np.zeros(S)
        self.kejut_V = np.zeros(S)
        self.drift_m = 0.0
        self.suspen = np.zeros(S, dtype=bool)   # saham disuspensi hari ini: tidak ada perdagangan
        self.buka_suspensi = {}                 # saham yang dibuka lagi hari ini: {j: V saat terakhir diperdagangkan}
        self._skenario_pagi(d)

        # beda tafsir nilai wajar berputar pelan (AR(1) harian) supaya agen
        # yang hari ini menganggap murah tidak menganggapnya murah selamanya
        pop = self.pop
        pop.nu = 0.95 * pop.nu + self.nu_sd * 0.312 * self.rng_nu.standard_normal(pop.nu.shape)
        acak_tafsir = self.rng_nu.standard_normal(pop.nu.shape)
        # program alokasi: AR(1) harian, persistensi 0,9 (paruh umur ~6,6 hari),
        # varians stasioner 1
        self.program = 0.9 * self.program + 0.436 * self.rng_nu.standard_normal(pop.nu.shape)
        for a_p, nilai in self.program_paksa.items():
            self.program[a_p] = nilai

        m = self.m[d] + self.efek_m + self.drift_m
        self.m_hari = m
        self.F *= np.exp(m)
        self.V_kemarin = self.V.copy()
        # Acuan "berita semalam" untuk pra-pembukaan: biasanya nilai wajar
        # kemarin, tapi saham yang baru dibuka dari suspensi menyerap SELURUH
        # perubahan nilai wajar sejak terakhir diperdagangkan.
        self.V_acuan = self.V_kemarin.copy()
        for j, v in self.buka_suspensi.items():
            self.V_acuan[j] = v
        # Saham yang sedang ramai menarik lebih banyak liputan & analisis:
        # aliran informasinya membesar sementara (umpan balik perhatian ->
        # informasi). Sumber gejolak mengumpul yang tidak diwarisi dari IHSG.
        intensitas = 1.0 + PERHATIAN_INFO * np.clip(self.buzz, 0.0, 3.0)
        dlogV = (self.beta * m + self.k_fund * self.sigma_idio * intensitas * self.e_fund[d]
                 + self.sigma_idio * self.lompatan[d] + self.kejut_V)
        self.V *= np.exp(dlogV)
        # Berita memperlebar beda tafsir: pemain nilai tidak sepakat seberapa
        # besar arti kabar hari ini, jadi mereka berdagang SALING BERLAWANAN --
        # volume naik walau harga tidak banyak bergerak. Ini salah satu
        # penjelasan baku kenapa volume melonjak di hari berita (data asli:
        # 1,6-2,4x median di hari |return| > 2 sigma).
        kejutan = np.minimum(np.abs(dlogV) / self.sigma, 5.0)
        pop.nu += (self.nu_sd > 0) * acak_tafsir * (0.25 * self.sigma * np.maximum(kejutan - 0.5, 0.0))[None, :]
        r_kemarin = np.log(self.riwayat_tutup[-1] / self.riwayat_tutup[-2])
        self.sent_saham = (0.8 * self.sent_saham + 0.4 * np.sign(self.lompatan[d]) * np.minimum(np.abs(self.lompatan[d]), 1.5)
                           + 0.1 * np.tanh(r_kemarin / self.sigma) + self.offset_sent)
        ih = self.ihsg_riwayat
        r_ihsg = np.log(ih[-1] / ih[-2])
        self.sent_pasar = (0.8 * self.sent_pasar + 0.4 * np.tanh(r_ihsg / self.sigma_m)
                           + self.derau_sent[d] + self.offset_sent_pasar)
        self.sent_saham = np.clip(self.sent_saham, -3, 3)
        self.sent_pasar = float(np.clip(self.sent_pasar, -3, 3))
        self.R_eff = self.R + self.offset_R
        self.lokal_eff = self.risiko_lokal + self.offset_lokal

        if self.pakai_llm and d >= self.burn and (d - self.burn) % self.k_llm == 0:
            self._konsultasi_pemimpin(d)

        # papan harga hari ini
        self.papan = []
        self.batas = np.zeros((S, 2))
        self.ref_idx = np.zeros(S, dtype=np.int64)
        for j in range(S):
            lo, hi = aturan.batas_harian(self.tutup_kemarin[j])
            papan = aturan.tangga(lo, hi)
            self.papan.append(papan)
            self.batas[j] = (lo, hi)
            self.ref_idx[j] = int(np.clip(np.searchsorted(papan, self.tutup_kemarin[j]), 0, len(papan) - 1))
        self.n_level = np.array([len(p) for p in self.papan], dtype=np.int64)
        maks = int(self.n_level.max())
        self.papan2d = np.zeros((S, maks))
        for j, p in enumerate(self.papan):
            self.papan2d[j, :len(p)] = p
            self.papan2d[j, len(p):] = p[-1]

        for b in self.bandar:
            self._bandar_pagi(b)
        for p in self.penjual:
            p['sisa_hari'] -= 1 if p.get('mulai') else 0
            p['mulai'] = True

        # order hari kemarin tidak dibawa (order harian BEI kedaluwarsa saat tutup)
        self.antre = self._antre_kosong()
        self.ikat_kas = np.zeros((self.N, S))
        self.hari_open = np.full(S, np.nan)
        self.hari_high = np.full(S, -np.inf)
        self.hari_low = np.full(S, np.inf)
        self.hari_vol = np.zeros(S)
        self.hari_nilai = np.zeros(S)
        self.agresif_beli_terakhir = np.zeros(S)

    @staticmethod
    def _antre_kosong():
        kosong = np.zeros(0, dtype=np.int64)
        return {'a': kosong, 's': kosong.copy(), 'si': kosong.copy(), 'lv': kosong.copy(),
                'q': kosong.copy(), 't': kosong.copy()}

    def _sinyal(self):
        """Sinyal per saham yang dilihat semua agen pada tick ini."""
        P = self.harga
        r_hari = np.log(P / self.tutup_kemarin)
        r5 = np.log(P / self.riwayat_tutup[-5])
        tren = 0.6 * np.tanh(r_hari / self.sigma) + 0.4 * np.tanh(r5 / (self.sigma * np.sqrt(5)))
        # gerakan yang TIDAK dijelaskan berita publik (perubahan nilai wajar):
        # yang dilawan ritel penampung. Melawan gerakan yang dibenarkan berita
        # membuat harga menyerap berita dicicil dua hari dan return harian
        # bisa ditebak dari kemarin (terukur: autokorelasi lag-1 +0,1..+0,2
        # hilang ke ~0 kalau ritel penampung dimatikan).
        e_hari = r_hari - np.log(self.V / self.V_acuan)
        e5 = r5 - np.log(self.V / self.riwayat_V[-5])
        tren_lebih = 0.6 * np.tanh(e_hari / self.sigma) + 0.4 * np.tanh(e5 / (self.sigma * np.sqrt(5)))
        self.tren_lebih = tren_lebih
        ih = self.ihsg_riwayat
        r20 = np.log(ih[-1] / ih[-21])
        makro = {
            G['ritel']: self.sent_pasar,
            G['institusi']: self.lokal_eff + self.offset_lokal_saham + 0.2 * np.tanh(r20 / 0.05),
            G['asing']: self.R_eff + self.offset_R_saham + 0.4 * np.tanh(r20 / 0.05),
        }
        buzz_now = self.buzz + 1.0 * np.clip(np.abs(r_hari) / self.sigma - 0.5, 0, 5)
        return r_hari, tren, makro, buzz_now

    def _order_umum(self, k, keluar_arr):
        pop = self.pop
        idx = self.umum
        n = len(idx)
        rng = self.rng_agen
        # ---- angka acak berukuran TETAP
        u_akt = rng.random(n)
        u_pilih = rng.random(n)
        eps = rng.standard_normal(n)
        z = rng.standard_normal(n)
        u_agr = rng.random(n)
        u_off = rng.random(n)

        r_hari, tren, makro, buzz_now = self._sinyal()
        pasar_buzz = float(np.mean(np.clip(buzz_now, 0, 4)))
        # urgensi pemain nilai: makin jauh harga dari nilai wajar di saham
        # yang mereka perhatikan, makin sering mereka datang ke pasar --
        # supaya berita besar tercermin di hari yang sama (ekor gemuk), bukan
        # dicicil berhari-hari sampai return hariannya kembali normal.
        celah0 = np.minimum(np.abs(np.log(self.V / self.harga)) / (SKALA_CELAH * self.sigma), 3.0)
        urgensi = (pop.perhatian[idx] @ celah0) * (pop.w_gap[idx] > 0.5)
        # perhatian ritel: keramaian saham YANG DIA PEGANG/PERHATIKAN membuatnya
        # lebih sering membuka aplikasi (attention-induced trading)
        ramai = pop.perhatian[idx] @ np.clip(buzz_now, 0, 4)
        p_akt = (pop.aktif[idx] * self.kurva[k] * float(self.likuid.mean())
                 * (1.0 + 0.25 * pop.buzz[idx] * pasar_buzz + 1.0 * pop.buzz[idx] * ramai)
                 * (1.0 + URGENSI * urgensi))
        jalan = (u_akt < p_akt) & pop.aktif_slot[idx]
        if not jalan.any():
            return
        a = idx[jalan]
        # pilih saham: perhatian x keramaian x likuiditas skenario
        w = pop.perhatian[a] * np.exp(np.minimum(pop.buzz[a, None] * buzz_now[None, :], 6.0)) * self.likuid[None, :]
        if self.suspen.any():
            w = w * ~self.suspen[None, :]
        cum = np.cumsum(w, axis=1)
        tot = cum[:, -1]
        ok = tot > 0
        a, cum, tot = a[ok], cum[ok], tot[ok]
        sel = jalan.copy()
        sel[jalan] = ok
        s = (cum < (u_pilih[sel] * tot)[:, None]).sum(axis=1)
        s = np.minimum(s, self.S - 1)

        g = pop.grup[a]
        P = self.harga[s]
        hold = pop.pos[a, s]
        modal_rata = np.where(hold > 0, pop.biaya[a, s] / np.maximum(hold * aturan.LOT, 1), P)
        u = P / modal_rata - 1.0
        # celah nilai LINEAR (tidak dijenuhkan): makin jauh harga dari nilai
        # wajar, makin besar order pemain nilai. Dengan tanh, salah harga 40%
        # dan 8% diperlakukan hampir sama dan harga bisa melayang jauh.
        celah = np.clip(np.log(self.V[s] * np.exp(pop.nu[a, s]) / P) / (SKALA_CELAH * self.sigma[s]), -6.0, 6.0)
        mak = np.zeros(len(a))
        for gg, val in makro.items():
            pilih = g == gg
            # sinyal makro bisa satu angka (seluruh pasar) atau per saham
            mak[pilih] = val[s[pilih]] if np.ndim(val) else val
        panik = np.clip(-r_hari[s] / aturan.ARB - 0.45, 0, 1) * 2.0 * self.panik_mult
        # Rezim kerumunan (herding): di hari biasa selera pribadi ritel
        # mendominasi (arus dua arah, sesuai JSON broker), tapi saat saham
        # sedang ramai atau ceritanya kencang, derau pribadi menyusut dan
        # ritel bergerak seragam -- sumber FOMO, ekor gemuk, dan gorengan.
        ritel_a = g == G['ritel']
        hype = (1.0 * np.clip(buzz_now[s] - 0.5, 0.0, 4.0)
                + 1.5 * np.clip(np.abs(self.sent_saham[s]) - 0.5, 0.0, 2.0))
        kerumunan_rezim = np.where(ritel_a, 1.0 / (1.0 + hype), 1.0)
        tren_a = np.where(pop.tipe[a] == T['ritel_kontra'],
                          0.5 * tren[s] + 0.5 * self.tren_lebih[s], tren[s])
        x = (pop.w_mom[a] * tren_a + pop.w_gap[a] * celah + pop.w_sent[a] * self.sent_saham[s]
             + pop.w_herd[a] * self.kerumunan[s] + pop.w_makro[a] * mak
             - pop.w_tp[a] * ((hold > 0) & (u >= pop.tp[a]))
             - pop.w_cl[a] * ((hold > 0) & (u <= -pop.cl[a]))
             - pop.w_panik[a] * panik
             # efek disposisi: makin untung makin ingin jual, rugi cenderung
             # ditahan / ditambah (data: arus ritel vs return 5 hari sebelumnya
             # negatif di big cap). Hanya bermakna kalau memegang barang.
             - pop.w_disp[a] * np.clip(u / 0.10, -1.0, 1.0) * (hold > 0)
             # program alokasi berhari-hari (dana asing / institusi): niat beli
             # atau jual yang bertahan, bukan keputusan baru tiap lelang
             + pop.w_prog[a] * self.program[a, s]
             + pop.derau[a] * kerumunan_rezim * eps[sel])
        amb = pop.ambang[a]
        beli = x > amb
        jual = (x < -amb) & (hold > 0)
        aksi = beli | jual
        if not aksi.any():
            return
        a, s, g, x, amb, P, hold = a[aksi], s[aksi], g[aksi], x[aksi], amb[aksi], P[aksi], hold[aksi]
        sel2 = np.flatnonzero(sel)[aksi]
        sisi = np.where(x > 0, 1, -1)
        kuat = np.clip(np.abs(x) / amb, 1.0, np.where(g == G['ritel'], 3.0, 8.0))
        nilai = self.nilai_order[g, s] * pop.skala[a] * kuat * np.exp(0.3 * z[sel2])
        q = np.maximum(np.round(nilai / (P * aturan.LOT)), 1.0)

        # agresivitas: menyeberang ke lawan, atau antre
        p_agr = np.clip(pop.agresif[a] + 0.25 * (kuat - 1.0), 0.0, 0.95)
        agresif = u_agr[sel2] < p_agr
        langkah = 1 + (u_off[sel2] * 3).astype(np.int64)            # 1..3 fraksi
        mundur = np.minimum((-np.log(np.maximum(1 - u_off[sel2], 1e-12)) / 0.6).astype(np.int64), 6)
        off = np.where(agresif, sisi * langkah, -sisi * mundur)
        # Di pra-pembukaan pemain PROFESIONAL (institusi, asing, juga pedagang
        # cepat) menggeser acuan harganya ke berita semalam. Ritel tidak: ia
        # memasang order relatif ke harga terakhir yang ia lihat, dan karena
        # itulah antreannya yang "diangkat" di hari kabar baik -- persis pola
        # data asli (arus ritel vs return hari yang sama -0,2 s/d -0,55).
        profesional = g != G['ritel']
        lvl = self.ref_idx[s] + np.where(profesional, self.geser_berita[s], 0) + off
        # ekstrem: pengejar tren antre di ARA, yang panik buang di ARB
        tipe = pop.tipe[a]
        kejar = (tipe == T['ritel_tren']) & (sisi > 0) & (kuat >= 2.5)
        buang = (tipe == T['ritel_ikut']) & (sisi < 0) & (kuat >= 2.5)
        lvl = np.where(kejar, self.n_level[s] - 1, lvl)
        lvl = np.where(buang, 0, lvl)
        lvl = np.clip(lvl, 0, self.n_level[s] - 1)

        # batas kas & barang. Order lama agen ini di saham yang SAMA akan
        # diganti, jadi yang mengikat cuma kas di antrean saham lain.
        harga_limit = self.papan2d[s, lvl]
        kas_bebas = pop.kas[a] - (self.ikat_kas.sum(axis=1)[a] - self.ikat_kas[a, s])
        maks_beli = np.floor(np.maximum(kas_bebas, 0.0) / (harga_limit * aturan.LOT * (1 + aturan.BIAYA_BELI)))
        q = np.where(sisi > 0, np.minimum(q, maks_beli), np.minimum(q, hold))
        ok = q >= 1
        if not ok.any():
            return
        keluar_arr.append((a[ok], s[ok], sisi[ok], lvl[ok], q[ok].astype(np.int64),
                           (agresif[ok]) & (pop.grup[a[ok]] == G['ritel'])))

    def _order_cepat(self, r_hari, keluar_arr):
        """Pedagang cepat memasang tangga bid/offer LEVEL_CEPAT level di kedua
        sisi harga terakhir, digeser oleh persediaannya sendiri dan ditarik
        saat harga bergejolak. Seluruhnya tervektorisasi (satu agen = satu
        saham)."""
        pop = self.pop
        a, j = self.cepat, self.cepat_saham
        n = len(a)
        u = self.rng_agen.random((n, LEVEL_CEPAT, 2))
        if n == 0:
            return
        q0 = self.dalam_dasar[j] * self.dalam_mult[j] / self.cepat_per_saham[j] * self.likuid[j]
        q0 = np.where(np.abs(r_hari[j]) > 2.5 * self.sigma[j], 0.4 * q0, q0)
        q0 = np.where(self.suspen[j], 0.0, q0)
        # spiral likuiditas: setelah beberapa hari bergejolak penyedia
        # likuiditas memasang antrean lebih tipis (sumber gejolak yang mengumpul)
        q0 = q0 / (1.0 + 0.8 * np.maximum(self.gejolak[j] - 1.0, 0.0))
        inv = pop.pos[a, j]
        inv0 = np.maximum(self.inv0_cepat[a, j], 1)
        dev = (inv - inv0) / inv0
        geser = np.where(dev > 0.25, -1, np.where(dev < -0.25, 1, 0)) * GESER_PERSEDIAAN
        lvl = np.arange(LEVEL_CEPAT)
        skala = 0.7 + 0.15 * lvl
        qb = np.round(q0[:, None] * skala[None, :] * (0.8 + 0.4 * u[:, :, 0]))
        qa = np.round(q0[:, None] * skala[None, :] * (0.8 + 0.4 * u[:, :, 1]))
        atas = (self.n_level[j] - 1)[:, None]
        ref = self.ref_idx[j][:, None] + self.geser_berita[j][:, None]
        lb = np.clip(ref - 1 - lvl[None, :] + geser[:, None], 0, atas)
        la = np.clip(ref + 1 + lvl[None, :] + geser[:, None], 0, atas)
        # batas barang & kas
        tot_a = qa.sum(axis=1)
        fa = np.where(tot_a > inv, inv / np.maximum(tot_a, 1), 1.0)
        qa = np.floor(qa * fa[:, None])
        biaya = (qb * self.papan2d[j[:, None], lb] * aturan.LOT).sum(axis=1) * (1 + aturan.BIAYA_BELI)
        fb = np.where(biaya > pop.kas[a], pop.kas[a] / np.maximum(biaya, 1), 1.0)
        qb = np.floor(qb * fb[:, None])
        A = np.concatenate([np.repeat(a, LEVEL_CEPAT)] * 2)
        Sx = np.concatenate([np.repeat(j, LEVEL_CEPAT)] * 2)
        Si = np.concatenate([np.ones(n * LEVEL_CEPAT, dtype=np.int64), -np.ones(n * LEVEL_CEPAT, dtype=np.int64)])
        L = np.concatenate([lb.ravel(), la.ravel()])
        Q = np.concatenate([qb.ravel(), qa.ravel()]).astype(np.int64)
        ok = Q >= 1
        keluar_arr.append((A[ok], Sx[ok], Si[ok], L[ok].astype(np.int64), Q[ok],
                           np.zeros(int(ok.sum()), dtype=bool)))

    def _tick(self, d, k):
        pop = self.pop
        S = self.S
        # Pedagang cepat membaca berita PUBLIK (faktor IHSG + pengumuman
        # emiten) sebelum pra-pembukaan dan menggeser kutipannya sebagian
        # besar ke arah perubahan nilai wajar semalam -- seperti market maker
        # sungguhan. Tanpa ini berita dicicil berhari-hari dan return harian
        # twin jadi bisa ditebak dari kemarin (terukur: 15-20% berita baru
        # terserap besoknya, autokorelasi lag-1 sampai +0,23).
        if k == 0:
            dV = np.log(self.V / self.V_acuan)
            fr = aturan.fraksi(self.harga) / self.harga
            self.geser_berita = np.round(GESER_BERITA * dV / fr).astype(np.int64)
        elif k == 1:
            self.geser_berita = np.zeros(S, dtype=np.int64)
        keluar_arr = []
        r_hari = np.log(self.harga / self.tutup_kemarin)
        self._order_umum(k, keluar_arr)
        # ---- antrean bertahan: order agen umum yang belum terisi dari lelang
        # sebelumnya. Dibuang kalau diganti order baru agen yang sama di saham
        # yang sama, sudah terlalu tua, atau harga sudah menjauh.
        an = self.antre
        if len(an['q']):
            jaga = (self.tick_abs - an['t']) < UMUR_ANTRE
            jaga &= np.abs(an['lv'] - self.ref_idx[an['s']]) <= JAUH_ANTRE
            if keluar_arr:
                baru = keluar_arr[0]
                kunci_baru = baru[0] * self.S + baru[1]
                jaga &= ~np.isin(an['a'] * self.S + an['s'], kunci_baru)
            for kunci in an:
                an[kunci] = an[kunci][jaga]
        n_baru_umum = len(keluar_arr[0][0]) if keluar_arr else 0
        if len(an['q']):
            keluar_arr.insert(0, (an['a'], an['s'], an['si'], an['lv'], an['q'],
                                  np.zeros(len(an['q']), dtype=bool)))
        n_antre_lama = len(an['q'])
        n_bertahan = n_antre_lama + n_baru_umum           # order yang boleh tetap di antrean
        umur = np.concatenate([an['t'], np.full(n_baru_umum, self.tick_abs, dtype=np.int64)])
        self._order_cepat(r_hari, keluar_arr)
        khusus = []
        for b in self.bandar:
            self._order_bandar(b, k, khusus)
        for p in self.penjual:
            self._order_penjual(p, khusus)
        for p in self.program_asing:
            self._order_program(p, khusus)
        if khusus:
            arr = np.array([(a, j, si, lv, q) for a, j, si, lv, q in khusus if q >= 1], dtype=float)
            if len(arr):
                lv = np.clip(arr[:, 3].astype(np.int64), 0, self.n_level[arr[:, 1].astype(np.int64)] - 1)
                q = np.floor(arr[:, 4]).astype(np.int64)
                a_ = arr[:, 0].astype(np.int64)
                s_ = arr[:, 1].astype(np.int64)
                si = arr[:, 2].astype(np.int64)
                # batas kas/barang agen khusus
                hl = self.papan2d[s_, lv]
                maks_beli = np.floor(pop.kas[a_] / (hl * aturan.LOT * (1 + aturan.BIAYA_BELI)))
                q = np.where(si > 0, np.minimum(q, maks_beli), np.minimum(q, pop.pos[a_, s_]))
                ok = q >= 1
                keluar_arr.append((a_[ok], s_[ok], si[ok], lv[ok], q[ok].astype(np.int64),
                                   np.zeros(int(ok.sum()), dtype=bool)))
        if not keluar_arr:
            self._catat_tick(d, k)
            self.tick_abs += 1
            return
        A = np.concatenate([x[0] for x in keluar_arr])
        Sx = np.concatenate([x[1] for x in keluar_arr])
        Si = np.concatenate([x[2] for x in keluar_arr])
        L = np.concatenate([x[3] for x in keluar_arr])
        Q = np.concatenate([x[4] for x in keluar_arr])
        AG = np.concatenate([x[5] for x in keluar_arr])

        isi = np.zeros(len(Q), dtype=np.int64)
        harga_isi = np.zeros(len(Q))
        self.agresif_beli_terakhir = np.zeros(S)
        kerumunan_baru = np.zeros(S)
        terakhir = k == self.K - 1
        for j in range(S):
            if self.suspen[j]:
                # disuspensi: tidak ada lelang; order khusus (bandar/penjual)
                # tidak terisi dan OHLC hari ini jatuh ke penutupan terakhir
                continue
            mj = Sx == j
            b = mj & (Si > 0)
            s_ = mj & (Si < 0)
            ib, is_ = np.flatnonzero(b), np.flatnonzero(s_)
            hasil = lelang(L[ib], Q[ib], L[is_], Q[is_], int(self.n_level[j]), int(self.ref_idx[j]))
            if hasil['idx'] is not None:
                p_idx = hasil['idx']
                P = self.papan[j][p_idx]
                isi[ib] = hasil['isi_b']
                isi[is_] = hasil['isi_s']
                harga_isi[ib] = P
                harga_isi[is_] = P
                self.harga[j] = P
                self.ref_idx[j] = p_idx
                v = hasil['vol']
                self.hari_vol[j] += v
                self.hari_nilai[j] += v * P * aturan.LOT
                if np.isnan(self.hari_open[j]):
                    self.hari_open[j] = P
                self.hari_high[j] = max(self.hari_high[j], P)
                self.hari_low[j] = min(self.hari_low[j], P)
            # agresivitas ritel (kerumunan) & beli agresif (untuk bandar distribusi)
            ag_b = Q[ib][AG[ib]].sum()
            ag_s = Q[is_][AG[is_]].sum()
            if ag_b + ag_s > 0:
                kerumunan_baru[j] = (ag_b - ag_s) / (ag_b + ag_s)
            self.agresif_beli_terakhir[j] = ag_b
            if terakhir:
                bid, offer = sisa_buku(L[ib], Q[ib], isi[ib], L[is_], Q[is_], isi[is_], int(self.n_level[j]))
                self._rekam_buku(d, j, bid, offer)
        self.kerumunan = 0.6 * self.kerumunan + 0.4 * kerumunan_baru

        # ---- antrean untuk lelang berikutnya: order agen umum yang belum habis
        sisa = Q[:n_bertahan] - isi[:n_bertahan]
        tinggal = sisa > 0
        self.antre = {'a': A[:n_bertahan][tinggal], 's': Sx[:n_bertahan][tinggal],
                      'si': Si[:n_bertahan][tinggal], 'lv': L[:n_bertahan][tinggal],
                      'q': sisa[tinggal].astype(np.int64), 't': umur[tinggal]}

        # ---- penyelesaian
        terisi = isi > 0
        if terisi.any():
            A, Sx, Si, isi_, Ph = A[terisi], Sx[terisi], Si[terisi], isi[terisi], harga_isi[terisi]
            nilai = isi_ * Ph * aturan.LOT
            beli = Si > 0
            # biaya posisi untuk penjualan: rata-rata SEBELUM tick ini
            pos_sebelum = pop.pos[A, Sx]
            modal_per_lot = np.where(pos_sebelum > 0, pop.biaya[A, Sx] / np.maximum(pos_sebelum, 1), 0.0)
            np.add.at(pop.pos, (A[beli], Sx[beli]), isi_[beli])
            np.add.at(pop.biaya, (A[beli], Sx[beli]), nilai[beli])
            np.add.at(pop.kas, A[beli], -nilai[beli] * (1 + aturan.BIAYA_BELI))
            jual = ~beli
            np.add.at(pop.pos, (A[jual], Sx[jual]), -isi_[jual])
            np.add.at(pop.biaya, (A[jual], Sx[jual]), -modal_per_lot[jual] * isi_[jual])
            np.add.at(pop.kas, A[jual], nilai[jual] * (1 - aturan.BIAYA_JUAL))
            pop.biaya[pop.pos <= 0] = 0.0
            g = pop.grup[A]
            np.add.at(self.rek['beli'][d], (g[beli], Sx[beli]), isi_[beli])
            np.add.at(self.rek['jual'][d], (g[jual], Sx[jual]), isi_[jual])
            np.add.at(self.rek['beli_nilai'][d], (g[beli], Sx[beli]), nilai[beli])
            np.add.at(self.rek['jual_nilai'][d], (g[jual], Sx[jual]), nilai[jual])

        # kas & barang yang terikat di antrean (untuk batas order lelang berikutnya)
        an = self.antre
        if len(an['q']):
            # jual yang bertahan tidak boleh melebihi barang yang tersisa
            jual_an = an['si'] < 0
            if jual_an.any():
                an['q'][jual_an] = np.minimum(an['q'][jual_an], pop.pos[an['a'][jual_an], an['s'][jual_an]])
            buang = an['q'] < 1
            if buang.any():
                for kunci in an:
                    an[kunci] = an[kunci][~buang]
        self.ikat_kas = np.zeros((self.N, S))
        if len(an['q']):
            beli_an = an['si'] > 0
            np.add.at(self.ikat_kas, (an['a'][beli_an], an['s'][beli_an]),
                      an['q'][beli_an] * self.papan2d[an['s'][beli_an], an['lv'][beli_an]]
                      * aturan.LOT * (1 + aturan.BIAYA_BELI))
        self._catat_tick(d, k)
        self.tick_abs += 1

    def _catat_tick(self, d, k):
        self.rek['tick_harga'][d, k] = self.harga

    def _rekam_buku(self, d, j, bid, offer):
        papan = self.papan[j]
        ib = np.flatnonzero(bid > 0)[::-1][:N_BUKU]
        io = np.flatnonzero(offer > 0)[:N_BUKU]
        self.rek['bid'][d, j, :len(ib)] = bid[ib]
        self.rek['bid_harga'][d, j, :len(ib)] = papan[ib]
        self.rek['offer'][d, j, :len(io)] = offer[io]
        self.rek['offer_harga'][d, j, :len(io)] = papan[io]

    def _malam(self, d):
        S = self.S
        P = self.harga.copy()
        r = self.rek
        r['open'][d] = np.where(np.isnan(self.hari_open), self.tutup_kemarin, self.hari_open)
        r['high'][d] = np.where(np.isfinite(self.hari_high), self.hari_high, self.tutup_kemarin)
        r['low'][d] = np.where(np.isfinite(self.hari_low), self.hari_low, self.tutup_kemarin)
        r['close'][d] = P
        r['vol'][d] = self.hari_vol
        r['nilai'][d] = self.hari_nilai
        r['ara'][d] = P >= self.batas[:, 1]
        r['arb'][d] = (P <= self.batas[:, 0]) & (P < self.tutup_kemarin)
        r['V'][d] = self.V
        r['sent'][d] = self.sent_saham
        r['R'][d] = self.R_eff
        r['sent_pasar'][d] = self.sent_pasar
        ihsg = self.ihsg0 * (self.bobot_sisa * self.F + (self.bobot_ihsg * P / self.P0).sum())
        r['ihsg'][d] = ihsg
        self.ihsg_riwayat.append(ihsg)
        self.ihsg_riwayat = self.ihsg_riwayat[-30:]

        ret = np.log(P / self.tutup_kemarin)
        lonjak = np.clip(np.abs(ret) / self.sigma - 1.0, -1, 4) + np.clip(np.log(np.maximum(self.hari_vol, 1) / self.adv), -1, 2)
        self.buzz = 0.6 * self.buzz + 0.4 * np.maximum(lonjak, 0)
        self.gejolak = 0.75 * self.gejolak + 0.25 * np.abs(ret) / (0.8 * self.sigma)
        self.tutup_kemarin = P
        self.riwayat_tutup.append(P)
        self.riwayat_tutup = self.riwayat_tutup[-25:]
        self.riwayat_V.append(self.V.copy())
        self.riwayat_V = self.riwayat_V[-25:]

        pop = self.pop
        for b in self.bandar:
            a, j = b['a'], b['s']
            inv = pop.pos[a, j]
            self.rek_bandar.append({
                'hari': d - self.burn, 'kode': self.kodes[j], 'agen': int(a), 'fase': b['fase'],
                'inv': float(inv),
                'modal_rata': float(pop.biaya[a, j] / (inv * aturan.LOT)) if inv > 0 else None,
                'kas': float(pop.kas[a]), 'otomatis': b['otomatis'],
            })
        if d == self.burn - 1 or (self.burn == 0 and d == 0 and self.kekayaan_awal is None):
            self.kekayaan_awal = self.kekayaan()

    def kekayaan(self):
        pop = self.pop
        return pop.kas + (pop.pos * self.harga[None, :] * aturan.LOT).sum(axis=1)

    # ---------------------------------------------------------------- jalan
    def jalan(self, berhenti=None):
        H = self.burn + self.D
        if self.burn == 0:
            self.kekayaan_awal = self.kekayaan()
        for d in range(H):
            self._pagi(d)
            for k in range(self.K):
                self._tick(d, k)
            self._malam(d)
            if berhenti is not None and d % 5 == 0 and berhenti():
                return False
        return True
