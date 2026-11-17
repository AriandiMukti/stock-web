/*
 * BDM Saku -- penampil data olahan BDM, offline.
 *
 * Datanya satu file (data.json) hasil website/ekspor_hp.py, isinya JSON yang
 * SAMA dengan endpoint *-data di web. Di aplikasi Android, "data.json"
 * dilayani dari penyimpanan internal oleh MainActivity; sinkron lewat WiFi
 * juga dikerjakan di sisi Java (window.Android), halaman ini cuma
 * menampilkan.
 *
 * Semua teks dari data (terutama komentar Ramai Dibahas yang ditulis orang
 * di internet) WAJIB lewat esc() sebelum masuk innerHTML.
 */
'use strict';

var D = null;           // paket data hasil ekspor
var DIGEST = {};        // ticker -> baris Ringkasan Watchlist
var BULAN = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];

// ---------------------------------------------------------------- bantuan

function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
}

function f(n, d) {
    if (n == null || n === '' || isNaN(n)) return '–';
    d = d || 0;
    return Number(n).toLocaleString('id-ID', { minimumFractionDigits: d, maximumFractionDigits: d });
}

function pct(n, d, kelas) {
    if (n == null || isNaN(n)) return '<span class="redup">–</span>';
    d = d == null ? 1 : d;
    var k = kelas === false ? '' : (n > 0 ? 'naik' : n < 0 ? 'turun' : '');
    return '<span class="mono ' + k + '">' + (n > 0 ? '+' : '') + f(n, d) + '%</span>';
}

function tgl(s) {
    if (!s) return '–';
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    return m ? (+m[3]) + ' ' + BULAN[+m[2] - 1] : esc(s);
}

function hariSejak(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || '');
    if (!m) return null;
    var a = new Date(+m[1], +m[2] - 1, +m[3]);
    var b = new Date(); b.setHours(0, 0, 0, 0);
    return Math.round((b - a) / 864e5);
}

function nilaiRp(milyar) {
    if (milyar == null) return '–';
    return milyar >= 1000 ? 'Rp' + f(milyar / 1000, 1) + ' T' : 'Rp' + f(milyar, milyar < 10 ? 1 : 0) + ' M';
}

function volume(v) {
    if (v == null) return '–';
    if (v >= 1e9) return f(v / 1e9, 1) + ' M';
    if (v >= 1e6) return f(v / 1e6, 1) + ' jt';
    return f(v);
}

/* Kode emiten jadi tautan ke detail kalau detailnya ikut diekspor. */
function kode(t) {
    return esc(t);
}
function hrefSaham(t) {
    return D && D.saham && D.saham[t] ? '#/saham/' + encodeURIComponent(t) : null;
}
function baris(t, sub, kanan, kananSub) {
    var h = hrefSaham(t);
    var isi = '<div class="kiri"><div class="kode">' + kode(t) + '</div>' +
        (sub ? '<div class="sub">' + sub + '</div>' : '') + '</div>' +
        '<div class="kanan">' + (kanan || '') + (kananSub ? '<div class="sub">' + kananSub + '</div>' : '') + '</div>';
    return h ? '<a class="baris" href="' + h + '">' + isi + '</a>' : '<div class="baris">' + isi + '</div>';
}

function lencana(teks, warna) {
    return '<span class="lencana ' + (warna || '') + '">' + esc(teks) + '</span>';
}

function kartu(judul, isi) {
    return '<section class="kartu">' + (judul ? '<h2>' + esc(judul) + '</h2>' : '') + isi + '</section>';
}

function tidakAda(menu) {
    var m = D.menu[menu];
    return !m || !m.available ? kartu(null, '<div class="catatan">Data tidak ada di ekspor ini' +
        (m && m.message ? ': ' + esc(m.message) : '') + '.</div>') : '';
}

/* Jurnal maju belum cukup = jangan disimpulkan apa pun dari angkanya. */
function catatanCukup(cukup) {
    return cukup ? '' : '<div class="catatan peringatan" style="margin-top:8px">Belum cukup data matang — angka ini belum boleh dibaca sebagai bukti.</div>';
}

// ---------------------------------------------------------------- muat data

function muat() {
    return fetch('data.json', { cache: 'no-store' }).then(function (r) {
        if (!r.ok) throw new Error('belum ada');
        return r.json();
    }).then(function (d) {
        D = d;
        DIGEST = {};
        ((d.menu.digest || {}).rows || []).forEach(function (r) { DIGEST[r.ticker] = r; });
    }).catch(function () { D = null; });
}

// ---------------------------------------------------------------- kepala & navigasi

function renderKepala(rute) {
    var el = document.getElementById('kepala');
    if (rute[0] === 'saham') {
        var hub = (D.saham[rute[1]] || {}).hub || {};
        var nama = ((hub.ownership || {}).name || '').replace(/^PT\.?\s*/i, '').replace(/\s*Tbk\.?$/i, '');
        el.innerHTML = '<button class="kembali" onclick="history.back()">‹</button>' +
            '<div class="judul">' + esc(rute[1]) + ' <span class="redup" style="font-weight:400;font-size:13px">' + esc(nama) + '</span></div>';
        return;
    }
    if (rute[0] === 'sinkron') {
        el.innerHTML = '<button class="kembali" onclick="history.back()">‹</button><div class="judul">Sinkron dari laptop</div>';
        return;
    }
    var umur = '';
    if (D) {
        var h = hariSejak(D.as_of);
        umur = '<div class="umur' + (h > 3 ? ' basi' : '') + '">data ' + tgl(D.as_of) +
            '<br>' + (h === 0 ? 'hari ini' : h + ' hari lalu') + '</div>';
    }
    el.innerHTML = '<div class="judul">BDM Saku</div>' + umur +
        '<a class="tbl-sinkron" href="#/sinkron">⟳ Sinkron</a>';
}

function renderNav(tab) {
    Array.prototype.forEach.call(document.querySelectorAll('#nav a'), function (a) {
        a.classList.toggle('aktif', a.getAttribute('data-tab') === tab);
    });
}

// ---------------------------------------------------------------- Ringkasan

function vRingkasan() {
    var m = D.menu, h = '';

    // APK baru ikut terunduh saat sinkron (MainActivity); pasangnya tetap atas izin pengguna.
    if (window.Android && Android.adaPembaruan && Android.adaPembaruan()) {
        h += '<section class="kartu" style="border-color:var(--up-dim);display:flex;align-items:center;gap:12px">' +
            '<div style="flex:1"><b>Versi baru BDM Saku</b><div class="catatan">Sudah terunduh dari laptop.</div></div>' +
            '<button class="tbl-utama" style="width:auto;padding:9px 16px" onclick="Android.pasangPembaruan()">Pasang</button></section>';
    }

    var rezim = (m.digest || {}).market_regime;
    if (rezim && rezim.available) {
        var warna = /anjlok|turun/i.test(rezim.key) ? 'merah' : /naik|reli/i.test(rezim.key) ? 'hijau' : '';
        h += kartu('Pasar', '<div style="display:flex;align-items:center;gap:10px">' + lencana(rezim.label, warna) +
            '<span class="catatan">' + f(rezim.pct_up, 1) + '% emiten naik dalam ' + rezim.window_days +
            ' hari · median ' + pct(rezim.median_pct) + '</span></div>');
    }

    h += kartu('Arsip Emiten', '<a href="#/musiman_saham">Musiman Saham</a> · <a href="#/perubahan_kepemilikan">Perubahan Kepemilikan</a>');
    h += kartu('Rotasi Sektor', '<a href="#/rotasi_sektor">Lihat kekuatan dan aktivitas tiap sektor →</a>');
    h += kartu('Agenda', '<a href="#/kalender">Kalender Pasar</a> · <a href="#/agenda_emiten">Agenda Emiten</a>');
    var k = m.kabar || {};
    var bg = k.berita_global;
    if (bg) {
        h += kartu('Berita global penting', '<div class="catatan">' + esc(bg.message) +
            ' · Snapshot Sync · ' + esc(bg.diperiksa || '') + '</div>' + (bg.items || []).map(function (n) {
            var link = /^https:\/\//i.test(n.url || '') ? n.url : '#';
            return '<div style="padding:10px 0;border-bottom:1px solid var(--line)"><div class="catatan">' + esc(n.kategori) +
                (n.kedaluwarsa ? ' · DATA LAMA' : '') + '</div><p>' + esc(n.ringkasan || n.judul) +
                '</p><div class="catatan">' + esc(n.dasar_ringkasan) + '</div><p><b>Konteks pemantauan (umum): </b>' + esc(n.konteks) + '</p><div class="catatan">' + esc(n.sumber) + ' · ' + esc(new Date(n.terbit).toLocaleString('id-ID', {timeZone: 'Asia/Jakarta'})) + ' WIB</div></div>';
        }).join(''));
    }

    if (k.available) {
        var seri = (k.seri || []).map(function (s) {
            return '<tr><td>' + esc(s.nama) + '</td><td class="' + (s.merah ? 'turun' : '') + '">' +
                (s.ret > 0 ? '+' : '') + f(s.ret, 2) + '%</td><td class="redup">' + (s.ambang == null ? '' : f(s.ambang, 2) + '%') + '</td><td>' +
                (s.merah ? lencana('MERAH', 'merah') : '') + '</td></tr>';
        }).join('');
        var kena = (k.kena || []).map(function (r) {
            return baris(r.stock, esc(r.komoditas) + ' jatuh semalam · lapis ' + esc(r.lapis), f(r.close));
        }).join('');
        h += kartu('Kabar semalam', '<table class="tabel"><tr><th>Pasar</th><th>Gerak</th><th>Ambang</th><th></th></tr>' +
            seri + '</table>' +
            (kena ? '<div class="catatan" style="margin:12px 0 6px">Lampu merah pagi ini — saham komoditasnya cenderung lanjut turun open→close:</div>' +
                '<div class="daftar" style="margin:0">' + kena + '</div>'
                : '<div class="catatan" style="margin-top:10px">Tidak ada lampu merah komoditas pagi ini.</div>') +
            '<div class="catatan" style="margin-top:8px">Dibangun ' + esc(k.dibangun) + '</div>');
    }

    var tb = m.tembus || {}, rp = m.rapat || {}, kc = m.kecondongan || {}, rd = m.radar || {}, rm = m.ramai || {};
    h += kartu('Hari ini', '<div class="angka-grid">' +
        '<a class="angka" href="#/sinyal/tembus"><div class="n naik">' + ((tb.baris || []).length) + '</div><div class="l">Tembus Basis aktif</div></a>' +
        '<a class="angka" href="#/sinyal/rapat"><div class="n">' + f((rp.n || {}).AMBIL) + '</div><div class="l">Rapat Agen: AMBIL</div></a>' +
        '<a class="angka" href="#/sinyal/kecondongan"><div class="n turun">' + f((kc.n_desil || {})[1]) + '</div><div class="l">Desil 1 (hindari)' +
        ((kc.masuk1 || []).length ? ' · ' + kc.masuk1.length + ' baru' : '') + '</div></a>' +
        '<a class="angka" href="#/sinyal/insider"><div class="n peringatan">' + f(rd.n_jual) + '</div><div class="l">Insider JUAL (peringatan)</div></a>' +
        '<a class="angka" href="#/ramai"><div class="n">' + f(rm.n_emiten) + '</div><div class="l">Emiten dibahas</div></a>' +
        '<a class="angka" href="#/watchlist"><div class="n">' + f((m.digest || {}).dengan_kejadian) + '</div><div class="l">Watchlist ada kejadian</div></a>' +
        '</div>');

    h += kartuStockLang(m.stocklang);

    // Watchlist yang arusnya berbalik -- yang paling perlu dilihat duluan.
    var waspada = ((m.digest || {}).rows || []).filter(function (r) {
        return r.flow && /breakdown|distribusi/i.test((r.flow.key || '') + ' ' + (r.flow.arah_arus || ''));
    });
    if (waspada.length) {
        h += kartu('Watchlist: arus berbalik', '<div class="daftar" style="margin:0">' + waspada.map(function (r) {
            return baris(r.ticker, esc(r.flow.label) + ' · ' + esc((r.watchlists || []).join(', ')), pct(r.flow.price_pct));
        }).join('') + '</div>');
    }

    h += '<div class="catatan" style="text-align:center">Ekspor ' + esc(D.dibuat) + ' · ' +
        Object.keys(D.saham || {}).length + ' emiten berdetail</div>';
    return h;
}

/* Laporan harian skrip StockLang berjurnal (website/stocklang_laporan.py).
   Ekspor lama tidak punya menu ini -> kartu tidak muncul. */
function kartuStockLang(sl) {
    if (!sl) return '';
    if (!sl.available) return kartu('StockLang', '<div class="catatan">' + esc(sl.message) + '</div>');
    var cukup = false;
    var isi = (sl.skrip || []).map(function (s) {
        if (s.status === 'error') {
            return '<div class="kepala-daftar">' + esc(s.nama) + ' ' + lencana('ERROR', 'merah') + '</div>' +
                '<div class="catatan" style="margin-bottom:10px">' + esc(s.pesan) + '</div>';
        }
        var hz = ['1', '5', '20'].map(function (k) {
            var x = (s.horizon || {})[k] || {};
            if (!x.matang) return '';
            if (x.matang >= 30) cukup = true;
            return '<tr' + (x.matang < 30 ? ' class="redup"' : '') + '><td>H+' + k + '</td><td>' + pct(x.rata) + '</td><td>' +
                f(x.matang) + '</td><td>' + f(x.win, 0) + '%</td><td>' + pct(x.lebih, 1) + '</td></tr>';
        }).join('');
        return '<div class="kepala-daftar">' + esc(s.nama) + ' · ' + (s.lolos.length ? s.lolos.length + ' lolos' : 'tidak ada yang lolos') + '</div>' +
            (s.lolos.length ? '<div class="daftar" style="margin:0 0 8px">' + s.lolos.map(function (t) {
                var p = (((D.saham[t] || {}).hub) || {}).price || {};
                return baris(t, null, f(p.close), pct(p.change_pct));
            }).join('') + '</div>' : '') +
            (hz ? '<table class="tabel" style="margin-bottom:12px"><tr><th>Jurnal</th><th>Rata</th><th>n</th><th>Win</th><th>vs semua</th></tr>' + hz + '</table>'
                : '<div class="catatan" style="margin-bottom:12px">Jurnal belum ada yang matang (' + f(s.hari) + ' hari tercatat).</div>');
    }).join('');
    return kartu('StockLang · ' + tgl(sl.as_of), isi + catatanCukup(cukup));
}

// ---------------------------------------------------------------- Sinyal

var SUB_SINYAL = [['tembus', 'Tembus Basis'], ['rapat', 'Rapat Agen'], ['kecondongan', 'Kecondongan'], ['insider', 'Insider']];

function vSinyal(sub) {
    sub = sub || 'tembus';
    var h = '<div class="segmen">' + SUB_SINYAL.map(function (s) {
        return '<a href="#/sinyal/' + s[0] + '" class="' + (s[0] === sub ? 'aktif' : '') + '">' + s[1] + '</a>';
    }).join('') + '</div>';
    return h + ({ tembus: sTembus, rapat: sRapat, kecondongan: sKecondongan, insider: sInsider }[sub] || sTembus)();
}

var LABEL_ATURAN = { basis: 'Tembus basis', puncak: 'Puncak 52 mgg', keduanya: 'Basis + puncak' };

function sTembus() {
    var t = D.menu.tembus;
    if (!t || !t.available) return tidakAda('tembus');
    var rows = (t.baris || []).map(function (r) {
        var aturan = r.basis && r.puncak ? 'keduanya' : r.aturan;
        return baris(r.stock,
            lencana(LABEL_ATURAN[aturan] || aturan, 'hijau') + ' ' + tgl(r.tanggal) + ' · vol ' + f(r.vol_x, 1) + '× · ' + nilaiRp(r.nilai_b),
            f(r.close_kini), pct(r.naik) + ' sejak sinyal');
    }).join('');
    var h = '<div class="daftar"><div class="kepala-daftar">Sinyal ≤ ' + ((t.config || {}).UMUR_MAX || 5) + ' hari · per ' + tgl(t.as_of) + '</div>' +
        (rows || '<div class="baris"><div class="kiri redup">Tidak ada sinyal aktif.</div></div>') + '</div>';
    h += kartu(null, '<div class="catatan">Aturan masuk yang diuji: beli di close hari setelah sinyal, keluar TS10. ' +
        'Win ~47% — untungnya dari ekor kanan, jadi kebanyakan sinyal memang kalah kecil.</div>');

    var j = t.jurnal;
    if (j && j.available) {
        var tb = (j.aturan || []).map(function (a) {
            return '<tr><td>' + esc(a.label) + ' H' + a.horizon + '</td><td>' + a.n_matang + '/' + a.n + '</td><td>' +
                (a.n_matang ? f(a.win, 0) + '%' : '–') + '</td><td>' + (a.n_matang ? pct(a.majemuk) : '–') + '</td></tr>';
        }).join('');
        var cukup = (j.aturan || []).some(function (a) { return a.cukup; });
        h += kartu('Jurnal maju', '<div class="catatan" style="margin-bottom:8px">Sejak ' + tgl((j.cakupan || {}).mulai) +
            ' · ' + f((j.cakupan || {}).n_hari) + ' hari bursa</div>' +
            '<table class="tabel"><tr><th>Aturan</th><th>Matang</th><th>Win</th><th>Majemuk</th></tr>' + tb + '</table>' + catatanCukup(cukup));
    }
    return h;
}

var rapatFilter = 'AMBIL';
function sRapat() {
    var r = D.menu.rapat;
    if (!r || !r.available) return tidakAda('rapat');
    var n = r.n || {};
    var h = '<div class="segmen">' + ['AMBIL', 'PANTAU', 'TOLAK'].map(function (k) {
        return '<button class="' + (k === rapatFilter ? 'aktif' : '') + '" onclick="rapatFilter=\'' + k + '\';render()">' +
            k + ' ' + f(n[k]) + '</button>';
    }).join('') + '</div>';

    var warna = { AMBIL: 'hijau', PANTAU: 'kuning', TOLAK: 'merah' };
    var rows = (r.rows || []).filter(function (x) { return x.keputusan === rapatFilter; }).map(function (x) {
        var rs = x.risiko || {};
        var poin = (x.pro || []).map(function (p) {
            return '<div class="poin pro">' + esc(p.teks) + ' <span class="redup">(' + esc(p.bobot) + ')</span></div>';
        }).concat((x.kontra || []).map(function (p) {
            return '<div class="poin kontra">' + esc(p.teks) + ' <span class="redup">(' + esc(p.bobot) + ')</span></div>';
        })).concat((x.lampu_pagi || []).map(function (p) {
            return '<div class="poin kontra">Lampu pagi: ' + esc(typeof p === 'string' ? p : p.teks || JSON.stringify(p)) + '</div>';
        })).join('');
        var h2 = hrefSaham(x.stock);
        return '<details class="buka"><summary>' +
            '<div class="baris"><div class="kiri"><div class="kode">' + esc(x.stock) + ' ' + lencana(x.keputusan, warna[x.keputusan]) + '</div>' +
            '<div class="sub">Support ' + f(x.support) + ' · jarak ' + f(x.jarak_sup, 1) + '% · desil ' + esc(x.desil) + '</div></div>' +
            '<div class="kanan">' + f(x.close) + '<div class="sub">' + pct(x.dari_puncak) + ' dr puncak</div></div></div></summary>' +
            '<div class="isi"><div>' + esc(x.alasan) + '</div>' + poin +
            (rs.stop ? '<div class="poin">Stop ' + f(rs.stop) + ' (' + f(rs.jarak_stop, 1) + '%, ' + esc(rs.dasar_stop) + ')' +
                (rs.porsi ? ' · porsi ' + esc(rs.porsi) : '') + '</div>' : '') +
            (rs.keluar ? '<div class="poin">' + esc(rs.keluar) + '</div>' : '') +
            (h2 ? '<div style="margin-top:8px"><a href="' + h2 + '">Lihat detail ' + esc(x.stock) + ' ›</a></div>' : '') +
            '</div></details>';
    }).join('');
    h += '<div class="daftar">' + (rows || '<div class="baris"><div class="kiri redup">Kosong.</div></div>') + '</div>';

    var j = r.jurnal;
    if (j && j.available) {
        var tb = (j.horizon || []).filter(function (x) { return x.n_matang; }).map(function (hz) {
            return (hz.kelompok || []).map(function (k) {
                return '<tr><td>H' + hz.horizon + ' ' + esc(k.nama) + '</td><td>' + f(k.n) + '</td><td>' + f(k.win, 0) +
                    '%</td><td>' + pct(k.majemuk) + '</td></tr>';
            }).join('');
        }).join('');
        h += kartu('Jurnal maju', '<div class="catatan" style="margin-bottom:8px">Sejak ' + tgl(j.mulai) + ' · ' + f(j.n_hari) +
            ' hari</div><table class="tabel"><tr><th>Kelompok</th><th>n</th><th>Win</th><th>Majemuk</th></tr>' + tb + '</table>' +
            catatanCukup(j.cukup && j.n_hari >= 40));
    }
    return h;
}

var kcSisi = 'bawah';
function sKecondongan() {
    var k = D.menu.kecondongan;
    if (!k || !k.available) return tidakAda('kecondongan');
    var baru = {};
    (k.masuk1 || []).concat(k.masuk10 || []).forEach(function (t) { baru[t] = 1; });
    var h = '<div class="segmen">' +
        '<button class="' + (kcSisi === 'bawah' ? 'aktif' : '') + '" onclick="kcSisi=\'bawah\';render()">Desil 1 · hindari</button>' +
        '<button class="' + (kcSisi === 'atas' ? 'aktif' : '') + '" onclick="kcSisi=\'atas\';render()">Desil 10</button></div>';
    var rows = (k[kcSisi] || []).map(function (r) {
        return baris(r.stock, 'skor ' + f(r.skor, 2) + ' · ' + nilaiRp(r.nilai_b) + (baru[r.stock] ? ' ' + lencana('BARU', 'biru') : ''),
            f(r.close), pct(r.dari_puncak) + ' dr puncak');
    }).join('');
    h += '<div class="daftar"><div class="kepala-daftar">Per ' + tgl(k.as_of) + ' · ' + f(k.n_layak) + ' emiten layak</div>' + rows + '</div>';
    h += kartu(null, '<div class="catatan">' + (kcSisi === 'bawah'
        ? 'Sisi yang kokoh di luar sampel: desil 1 tertinggal pasar. Pakai sebagai daftar hindari, bukan daftar jual-kosong.'
        : 'Desil 10 lemah: positif di validasi, ~nol di 2013–2019. Jangan dibaca sebagai daftar beli.') + '</div>');

    var j = k.jurnal;
    if (j && j.available) {
        var tb = (j.horizon || []).map(function (hz) {
            return '<tr><td>H' + hz.horizon + '</td><td>' + f(hz.n_tanggal) + '</td><td>' + pct(hz.d1) + '</td><td>' + pct(hz.d10) +
                '</td><td>' + (hz.ic == null ? '–' : f(hz.ic, 2)) + '</td></tr>';
        }).join('');
        h += kartu('Jurnal maju', '<table class="tabel"><tr><th></th><th>Tanggal</th><th>Desil 1</th><th>Desil 10</th><th>IC</th></tr>' + tb +
            '</table>' + catatanCukup((j.horizon || []).some(function (x) { return x.cukup; })));
    }
    return h;
}

function sInsider() {
    var r = D.menu.radar;
    if (!r || !r.available) return tidakAda('radar');
    var j = r.jurnal || {}, di = j.data_insider || {};
    var h = '';
    if (di.umur_hari != null) {
        h += kartu(null, '<div class="catatan' + (di.umur_hari > 7 ? ' peringatan' : '') + '">Data insider ditarik ' + tgl(di.tarik_terakhir) +
            ' (' + di.umur_hari + ' hari lalu). Laporan insider memang telat — jeda median ' + f(j.jeda_median) + ' hari.</div>');
    }
    var jual = (r.jual_peringatan || []).map(function (x) {
        return baris(x.ticker, f(x.n_insiders) + ' transaksi · terakhir ' + tgl(x.last_action_date) + ' · momentum ' + esc(x.momentum_bucket),
            '<span class="peringatan">' + f(x.sell_p, 0) + '%</span>', 'vs biasa ' + f(x.baseline_p, 0) + '%');
    }).join('');
    h += '<div class="daftar"><div class="kepala-daftar">Insider JUAL · peluang jatuh dalam 40 hari</div>' +
        (jual || '<div class="baris"><div class="kiri redup">Tidak ada.</div></div>') + '</div>';

    var beli = (r.beli || []).map(function (x) {
        return baris(x.ticker, esc((x.alasan || []).join(', ').replace(/_/g, ' ')) + ' · ' + tgl(x.last_action_date),
            f(x.harga), pct(x.dari_puncak) + ' dr puncak');
    }).join('');
    h += '<div class="daftar"><div class="kepala-daftar">Insider BELI dalam konteks</div>' +
        (beli || '<div class="baris"><div class="kiri redup">Tidak ada.</div></div>') + '</div>';
    h += kartu(null, '<div class="catatan">Insider BELI polos ≈ lempar koin; cuma berarti disilang Jatuh Dalam / Akumulasi Palsu. ' +
        'Insider JUAL dibaca sebagai peringatan dini, efeknya ~+11 poin setelah jeda tarik nyata.</div>');
    return h;
}

// ---------------------------------------------------------------- Ramai Dibahas

var ramaiCari = '';
function vRamai() {
    var r = D.menu.ramai;
    if (!r || !r.available) return tidakAda('ramai');
    var h = '';
    h += kartuSuasana(r);

    h += '<input class="cari" placeholder="Cari kode…" value="' + esc(ramaiCari) + '" ' +
        'oninput="ramaiCari=this.value.toUpperCase();gambarRamai()" autocapitalize="characters" style="margin-bottom:12px">';
    h += '<div class="daftar" id="ramai-daftar"></div>';
    h += kartu(null, '<div class="catatan">Bahan pemantauan, bukan sinyal. Buzz ≈ ukuran + gerak harga, dan condong ke saham yang sedang jatuh.</div>');
    setTimeout(gambarRamai, 0);
    return h;
}

function angkaBertanda(v) {
    if (v == null || isNaN(v)) return '<span class="redup">–</span>';
    return '<span class="' + (v > 0 ? 'naik' : v < 0 ? 'turun' : 'redup') + '">' + (v > 0 ? '+' : '') + f(v) + '</span>';
}

/* Sama dengan rdVonis di ramai_dibahas.html. */
function vonisSuasana(skor, pos, neg) {
    if (!(pos + neg)) return '<span class="redup">Belum ada yang berpendapat</span>';
    var porsi = Math.round(100 * Math.max(pos, neg) / (pos + neg));
    if (skor >= 10) return '<span class="naik">Mayoritas positif</span> <span class="redup">(' + porsi + '% yang berpendapat)</span>';
    if (skor <= -10) return '<span class="turun">Mayoritas negatif</span> <span class="redup">(' + porsi + '% yang berpendapat)</span>';
    return '<span class="redup">Seimbang</span>';
}

/* Kartu "Suasana Obrolan" -- tiruan versi web, ditumpuk untuk layar sempit. */
function kartuSuasana(r) {
    var su = r.suasana;
    if (!su) return '';
    var blok = ['Stockbit', 'Telegram'].map(function (k) {
        var s = su[k];
        if (!s || !s.n) {
            return '<div class="suasana-blok"><div class="lbl-kecil">' + k + '</div><div class="skor-besar redup">–</div>' +
                '<div class="catatan">Tidak ada post di jendela ini.</div></div>';
        }
        return '<div class="suasana-blok"><div class="lbl-kecil">' + k + ' · ' + f(s.n) + ' post</div>' +
            '<div class="skor-besar mono">' + angkaBertanda(s.skor) + '</div>' +
            '<div style="margin:2px 0 8px">' + vonisSuasana(s.skor, s.pos, s.neg) + '</div>' +
            '<div class="bar"><span style="width:' + (100 * s.pos / s.n) + '%;background:var(--up)"></span>' +
            '<span style="flex:1;background:var(--line)"></span>' +
            '<span style="width:' + (100 * s.neg / s.n) + '%;background:var(--down)"></span></div>' +
            '<div class="catatan" style="margin-top:6px"><span class="naik">' + f(s.pos) + ' positif (' + f(s.pos_pct, 0) + '%)</span> · ' +
            '<span class="turun">' + f(s.neg) + ' negatif (' + f(s.neg_pct, 0) + '%)</span> · ' + f(s.netral) + ' netral</div></div>';
    }).join('');
    var hari = (su.hari || []).map(function (x) {
        return '<span class="chip">' + esc(x.tgl) + ' · ' + f(x.n) + ' post · ' + angkaBertanda(x.skor) + '</span>';
    }).join('');
    return '<section class="kartu"><h2>Suasana obrolan ' + lencana('deskripsi, bukan sinyal', 'merah') + '</h2>' +
        '<div class="catatan" style="margin:-4px 0 10px">' + esc(String(r.sentimen_jendela || '').replace(/\b[A-Z][a-z]{2}\b/g, function (b) {
            return BULAN_EN[b] || b;
        })) + '</div><div>' + blok + '</div>' +
        (hari ? '<div class="chips">' + hari + '</div>' : '') +
        '<details class="cara"><summary>Cara membaca skor</summary><div class="catatan">' +
        'Tiap post dinilai dari kamus kata pasar (naik, ARA, cuan, serok, 🚀 vs turun, ARB, nyangkut, jebol, 😭); kata sesudah ' +
        '<i>gak/belum/jangan</i> dibalik. <b>Skor</b> = (positif − negatif) ÷ (positif + negatif) × 100: +100 semua yang ' +
        'berpendapat positif, −100 semua negatif. Post netral tidak ikut skor. Sarkasme dan pertanyaan ("kapan naik?") tidak terbaca. ' +
        'Riset 19 Okt: negativitas obrolan cuma mengikuti harga hari itu, tidak menebak IHSG besok.<br><br>' +
        'Jendelanya Senin–Jumat minggu berjalan (akhir pekan: minggu yang baru lewat). Stockbit cuma memberi 30 post terakhir per ' +
        'emiten, jadi hari yang tidak sempat ditarik hanya terwakili emiten yang sepi — lihat jumlah post per hari.' +
        '</div></details>' +
        '<div class="catatan" style="margin-top:8px">Ditarik ' + esc(r.ditarik) + '</div></section>';
}

function gambarRamai() {
    var el = document.getElementById('ramai-daftar');
    if (!el) return;
    var rows = (D.menu.ramai.baris || []).filter(function (x) {
        return !ramaiCari || (x.stock || '').indexOf(ramaiCari) === 0;
    }).slice(0, 60).map(function (x) {
        var komen = (x.contoh || []).map(function (c) {
            var w = c.sent > 0 ? 'naik' : c.sent < 0 ? 'turun' : 'redup';
            return '<div class="komen"><div class="meta"><span class="' + w + '">●</span> ' + esc(c.sumber) + ' · ' + esc(c.penulis) +
                ' · ' + esc(c.waktu) + (c.suka ? ' · ♥ ' + f(c.suka) : '') + '</div>' + esc(c.teks) + '</div>';
        }).join('');
        var h2 = hrefSaham(x.stock);
        var sk = x.skor > 0 ? 'naik' : x.skor < 0 ? 'turun' : '';
        return '<details class="buka"><summary><div class="baris"><div class="kiri"><div class="kode">' + esc(x.stock) +
            (x.lonjak >= 3 ? ' ' + lencana(f(x.lonjak, 1) + '×', 'kuning') : '') + '</div>' +
            '<div class="sub">' + f(x.total) + ' pesan · sentimen <span class="' + sk + '">' + (x.skor > 0 ? '+' : '') + f(x.skor) + '</span>' +
            ' · ' + f(x.pos) + '↑ ' + f(x.neg) + '↓</div></div>' +
            '<div class="kanan">' + f(x.close) + '<div class="sub">' + pct(x.r1) + ' · 5h ' + pct(x.r5) + '</div></div></div></summary>' +
            '<div class="isi">' + (komen || '<div class="redup">Tidak ada contoh pesan.</div>') +
            (h2 ? '<div style="margin-top:8px"><a href="' + h2 + '">Lihat detail ' + esc(x.stock) + ' ›</a></div>' : '') +
            '</div></details>';
    }).join('');
    el.innerHTML = rows || '<div class="baris"><div class="kiri redup">Tidak ada yang cocok.</div></div>';
}

// ---------------------------------------------------------------- Watchlist

var wlCari = '';
function vWatchlist() {
    var h = '<input class="cari" placeholder="Cari kode emiten…" value="' + esc(wlCari) + '" ' +
        'oninput="wlCari=this.value.toUpperCase();gambarCari()" autocapitalize="characters" style="margin-bottom:12px">' +
        '<div id="hasil-cari"></div><div id="wl-isi">';
    var groups = (D.menu.watchlist || {}).groups || [];
    groups.forEach(function (g) {
        h += '<div class="daftar"><div class="kepala-daftar">' + esc(g.label) + ' · ' + g.tickers.length + '</div>' +
            g.tickers.map(barisWatchlist).join('') + '</div>';
    });
    if (!groups.length) h += kartu(null, '<div class="catatan">Watchlist kosong di ekspor ini.</div>');
    h += '</div>';
    setTimeout(gambarCari, 0);
    return h;
}

function barisWatchlist(t) {
    var hub = (D.saham[t] || {}).hub || {}, p = hub.price || {}, dg = DIGEST[t] || {};
    var tanda = [];
    if (dg.flow) tanda.push(lencana(dg.flow.label, /breakdown|distribusi/i.test(dg.flow.key + dg.flow.arah_arus) ? 'merah' : 'hijau'));
    if (dg.screen) tanda.push(lencana(dg.screen.record ? dg.screen.record.label : dg.screen.key, 'biru'));
    if (dg.scanner) tanda.push(esc(dg.scanner.scanner_label) + ' ' + f(dg.scanner.score));
    if (dg.insider) tanda.push(lencana('insider', 'kuning'));
    return baris(t, tanda.join(' ') || '<span class="redup">tidak ada kejadian</span>', f(p.close), pct(p.change_pct));
}

function gambarCari() {
    var el = document.getElementById('hasil-cari'), wl = document.getElementById('wl-isi');
    if (!el) return;
    if (!wlCari) { el.innerHTML = ''; wl.style.display = ''; return; }
    var cocok = Object.keys(D.saham).filter(function (t) { return t.indexOf(wlCari) === 0; }).slice(0, 30);
    wl.style.display = 'none';
    el.innerHTML = '<div class="daftar">' + (cocok.map(barisWatchlist).join('') ||
        '<div class="baris"><div class="kiri redup">Tidak ada di ekspor. Detail cuma ikut untuk emiten yang muncul di menu/watchlist.</div></div>') + '</div>';
}

// ---------------------------------------------------------------- Detail saham

function dimana(t) {
    var m = D.menu, hasil = [];
    ((m.watchlist || {}).groups || []).forEach(function (g) { if (g.tickers.indexOf(t) >= 0) hasil.push(lencana(g.label, 'biru')); });
    if ((m.tembus.baris || []).some(function (r) { return r.stock === t; })) hasil.push(lencana('Tembus Basis', 'hijau'));
    (m.rapat.rows || []).forEach(function (r) {
        if (r.stock === t) hasil.push(lencana('Rapat: ' + r.keputusan, r.keputusan === 'AMBIL' ? 'hijau' : r.keputusan === 'TOLAK' ? 'merah' : 'kuning'));
    });
    if ((m.kecondongan.bawah || []).some(function (r) { return r.stock === t; })) hasil.push(lencana('Desil 1 · hindari', 'merah'));
    if ((m.kecondongan.atas || []).some(function (r) { return r.stock === t; })) hasil.push(lencana('Desil 10', ''));
    if ((m.radar.jual_peringatan || []).some(function (r) { return r.ticker === t; })) hasil.push(lencana('Insider JUAL', 'kuning'));
    if ((m.radar.beli || []).some(function (r) { return r.ticker === t; })) hasil.push(lencana('Insider BELI', 'hijau'));
    if ((m.kabar.kena || []).some(function (r) { return r.stock === t; })) hasil.push(lencana('Lampu merah pagi', 'merah'));
    if ((m.ramai.baris || []).some(function (r) { return r.stock === t; })) hasil.push(lencana('Ramai dibahas', ''));
    ((m.stocklang || {}).skrip || []).forEach(function (s) {
        if ((s.lolos || []).indexOf(t) >= 0) hasil.push(lencana('StockLang: ' + s.nama, 'biru'));
    });
    return hasil.join(' ');
}

var chartBar = 65;
function vSaham(t) {
    var s = D.saham[t];
    if (!s) return '<div class="kosong"><div class="ik">?</div>' + esc(t) + ' tidak ikut diekspor.</div>';
    var hub = s.hub || {}, p = hub.price || {}, h = '';

    h += '<section class="kartu"><div style="display:flex;align-items:baseline;gap:10px">' +
        '<div class="harga-besar">' + f(p.close || (s.chart || {}).lastClose) + '</div>' + pct(p.change_pct) +
        '<div style="flex:1"></div><div class="catatan">' + tgl(p.date) + '</div></div>' +
        '<div class="catatan" style="margin:4px 0 10px">Nilai ' + nilaiRp(p.value_b) + ' · volume ' + f(p.vol_mult, 1) + '× rata-rata</div>' +
        '<div>' + dimana(t) + '</div>';
    if (s.chart) {
        h += '<div class="segmen" style="margin:12px 0 6px">' + [[22, '1 bln'], [65, '3 bln'], [130, '6 bln']].map(function (b) {
            return '<button class="' + (b[0] === chartBar ? 'aktif' : '') + '" onclick="chartBar=' + b[0] + ';render()">' + b[1] + '</button>';
        }).join('') + '</div>' +
            '<div class="chart-info" id="chart-info"></div><div class="chart-wadah"><canvas id="chart"></canvas></div>' +
            '<div class="legenda"><span><i style="background:var(--info)"></i>harga modal bandar</span>' +
            '<span><i style="background:var(--warn)"></i>support/resistance</span>' +
            '<span><i style="background:var(--up)"></i>Top5 kumulatif</span><span><i style="background:var(--down)"></i>Ritel kumulatif</span></div>';
        setTimeout(function () { gambarChart(s.chart, (hub.modal_bandar || {}).harga_modal); }, 0);
    }
    h += '</section>';

    var sc = hub.current_score;
    if (sc) {
        h += kartu('Kartu keputusan · skor ' + f(sc.score), (sc.reasons || []).map(alasan).join('') +
            '<div class="catatan" style="margin-top:6px">Jendela ' + sc.window + ' hari · per ' + tgl(sc.as_of) + '</div>');
    }

    var cf = hub.current_flow, mb = hub.modal_bandar, ind = hub.independence, info = '';
    if (cf && cf.available) info += '<div class="poin ' + (cf.arah_arus === 'distribusi' ? 'kontra' : 'pro') + '"><b>' + esc(cf.label) +
        '</b> — ' + esc(cf.penjelasan) + '</div>';
    if (mb) info += '<div class="poin">Modal bandar ~' + f(mb.harga_modal) + ' · ' + esc(mb.posisi) + ' (' + f(mb.n_broker) + ' broker)</div>';
    if (ind && ind.available) info += '<div class="poin">' + esc(ind.label) + ' (korelasi ' + f(ind.correlation, 2) + ')</div>';
    if (hub.screen) {
        var rec = hub.screen.record || {};
        info += '<div class="poin">Screen <b>' + esc(hub.screen.label) + '</b> ' + f(hub.screen.streak_days) + ' hari berturut' +
            (rec.n ? ' · rekam jejak win ' + f(rec.win_rate, 0) + '%, rata2 ' + f(rec.mean, 1) + '%' : '') + '</div>';
    }
    if (hub.kering) info += '<div class="poin">Kering Screener K' + esc(hub.kering.K) + ' skor ' + f(hub.kering.skor, 2) + ' (' + tgl(hub.kering.date) + ')</div>';
    if (info) h += kartu('Arus & bandar', info);

    var sig = hub.signals || [];
    if (sig.length) {
        h += '<div class="daftar"><div class="kepala-daftar">Sinyal scanner berjalan</div>' + sig.map(function (x) {
            return '<details class="buka"><summary>' + baris(t, esc(x.scanner_label) + ' · ' + tgl(x.signal_date), 'skor ' + f(x.score)) +
                '</summary><div class="isi">' + (x.reasons || []).map(alasan).join('') +
                (x.flow || []).filter(function (fl) { return fl.available; }).map(function (fl) {
                    return '<div class="poin">H' + fl.horizon + ': ' + esc(fl.label) + ' ' + pct(fl.price_pct) + '</div>';
                }).join('') + '</div></details>';
        }).join('') + '</div>';
    }

    var ins = hub.insider || [];
    if (ins.length) {
        h += '<div class="daftar"><div class="kepala-daftar">Transaksi insider terbaru</div>' + ins.slice(0, 10).map(function (x) {
            var jual = /SELL/.test(x.action_type);
            return '<div class="baris"><div class="kiri"><div style="font-size:13px">' + esc(x.name) + '</div><div class="sub">' +
                tgl(x.date) + ' · ' + esc(x.source) + (x.is_controller ? ' · pengendali' : '') + '</div></div>' +
                '<div class="kanan"><span class="' + (jual ? 'turun' : 'naik') + '">' + esc(x.action_label) + '</span>' +
                '<div class="sub">' + (x.value_idr ? nilaiRp(x.value_idr / 1e9) : '') + ' @' + f(x.price_used) + '</div></div></div>';
        }).join('') + '</div>';
    }

    var ow = hub.ownership;
    if (ow && ow.available) {
        var komposisi = [['Asing', ow.pct_foreign, ow.delta_foreign, 'var(--info)'],
            ['Lokal non-ritel', ow.pct_local_non_retail, ow.delta_local_non_retail, 'var(--up)'],
            ['Ritel', ow.pct_retail, ow.delta_retail, 'var(--down)']];
        var bar = '<div class="bar" style="height:10px;margin:4px 0 8px">' + komposisi.map(function (k) {
            return '<span style="width:' + (k[1] || 0) + '%;background:' + k[3] + '"></span>';
        }).join('') + '</div>';
        var tb = komposisi.map(function (k) {
            return '<tr><td>' + k[0] + '</td><td>' + f(k[1], 1) + '%</td><td>' + pct(k[2], 2) + '</td></tr>';
        }).join('');
        var holders = (ow.holders || []).slice(0, 8).map(function (x) {
            return '<tr><td>' + esc(x.name) + '</td><td>' + f(x.pct, 2) + '%</td><td>' +
                (x.change_lot ? '<span class="' + (x.change_lot > 0 ? 'naik' : 'turun') + '">' + (x.change_lot > 0 ? '+' : '') + volume(x.change_lot) + '</span>' : '') +
                '</td></tr>';
        }).join('');
        h += kartu('Kepemilikan · ' + esc(ow.month_label), bar +
            '<table class="tabel"><tr><th></th><th>Porsi</th><th>Δ bulan</th></tr>' + tb + '</table>' +
            '<div class="catatan" style="margin:8px 0">Free float ' + f(ow.free_float, 1) + '%</div>' +
            (holders ? '<table class="tabel"><tr><th>Pemegang ≥1% (' + esc(ow.holder_month) + ')</th><th>%</th><th>Δ lot</th></tr>' + holders + '</table>' : ''));
    }
    return h;
}

function alasan(r) {
    var k = r.kind === 'baik' ? 'pro' : r.kind === 'buruk' ? 'kontra' : '';
    return '<div class="poin ' + k + '">' + esc(r.text) + '</div>';
}

// ---------------------------------------------------------------- chart (canvas, tanpa pustaka)

// Tanggal chart dari server berformat "23 Oct" (bulan Inggris).
var BULAN_EN = { Jan: 'Jan', Feb: 'Feb', Mar: 'Mar', Apr: 'Apr', May: 'Mei', Jun: 'Jun', Jul: 'Jul', Aug: 'Agu', Sep: 'Sep', Oct: 'Okt', Nov: 'Nov', Dec: 'Des' };
function tglChart(s) {
    return String(s).replace(/[A-Z][a-z]{2}/, function (b) { return BULAN_EN[b] || b; });
}

function gambarChart(c, modal) {
    var cv = document.getElementById('chart');
    if (!cv) return;
    var n = Math.min(chartBar, c.dates.length), a = c.dates.length - n;
    var sl = function (k) { return (c[k] || []).slice(a); };
    var o = sl('open'), hi = sl('high'), lo = sl('low'), cl = sl('close'), vol = sl('volume');
    var dt = sl('dates').map(tglChart), t5 = sl('top5'), rt = sl('ritel');

    var W = cv.parentNode.clientWidth, H = Math.round(Math.min(420, W * 0.95));
    var dpr = window.devicePixelRatio || 1;
    cv.width = W * dpr; cv.height = H * dpr; cv.style.height = H + 'px';
    var x = cv.getContext('2d');
    var css = getComputedStyle(document.documentElement);
    var warna = function (v) { return css.getPropertyValue(v).trim(); };

    var kiri = 8, kanan = 52, hp = H * 0.58, hv = H * 0.14, hf = H * 0.22, jeda = H * 0.02;
    var lebar = (W - kiri - kanan) / n;
    var xi = function (i) { return kiri + lebar * (i + 0.5); };

    var lmin = Math.min.apply(null, lo), lmax = Math.max.apply(null, hi);
    // Level/garis modal di luar rentang jauh tidak boleh menggepengkan lilin.
    var pmin = lmin - (lmax - lmin) * 0.05, pmax = lmax + (lmax - lmin) * 0.05;
    var yp = function (v) { return 4 + (pmax - v) / (pmax - pmin) * (hp - 8); };
    var vmax = Math.max.apply(null, vol) || 1;
    var y0v = hp + jeda, y0f = hp + hv + jeda * 2;

    function skala(seri) {
        var mn = Math.min.apply(null, seri), mx = Math.max.apply(null, seri), r = (mx - mn) || 1;
        return function (v) { return y0f + 4 + (mx - v) / r * (hf - 8); };
    }

    function gambar(sorot) {
        x.setTransform(dpr, 0, 0, dpr, 0, 0);
        x.clearRect(0, 0, W, H);
        x.font = '10px ' + warna('--font-mono');
        x.fillStyle = warna('--text-dim');
        x.strokeStyle = warna('--line-soft');
        x.lineWidth = 1;

        // grid harga + label kanan
        for (var g = 0; g <= 4; g++) {
            var v = pmin + (pmax - pmin) * g / 4, yy = yp(v);
            x.beginPath(); x.moveTo(kiri, yy); x.lineTo(W - kanan, yy); x.stroke();
            x.fillText(f(v), W - kanan + 4, yy + 3);
        }
        // support / resistance
        x.setLineDash([4, 4]); x.strokeStyle = warna('--warn');
        (c.levels || []).forEach(function (lv) {
            if (lv < pmin || lv > pmax) return;
            x.beginPath(); x.moveTo(kiri, yp(lv)); x.lineTo(W - kanan, yp(lv)); x.stroke();
        });
        x.setLineDash([]);
        // harga modal bandar (satu angka, kini) -- cuma digambar kalau masuk layar
        if (modal && modal >= pmin && modal <= pmax) {
            x.strokeStyle = warna('--info'); x.setLineDash([6, 3]);
            x.beginPath(); x.moveTo(kiri, yp(modal)); x.lineTo(W - kanan, yp(modal)); x.stroke();
            x.setLineDash([]);
        }
        // lilin + volume
        var bw = Math.max(1, lebar * 0.7);
        for (var i = 0; i < n; i++) {
            var up = cl[i] >= o[i];
            x.strokeStyle = x.fillStyle = up ? warna('--up') : warna('--down');
            x.beginPath(); x.moveTo(xi(i), yp(hi[i])); x.lineTo(xi(i), yp(lo[i])); x.stroke();
            var yt = yp(Math.max(o[i], cl[i])), yb = yp(Math.min(o[i], cl[i]));
            x.fillRect(xi(i) - bw / 2, yt, bw, Math.max(1, yb - yt));
            x.globalAlpha = 0.45;
            var tv = vol[i] / vmax * hv;
            x.fillRect(xi(i) - bw / 2, y0v + hv - tv, bw, tv);
            x.globalAlpha = 1;
        }
        // arus kumulatif, masing-masing diskalakan sendiri (bentuknya yang dibaca)
        [[t5, '--up'], [rt, '--down']].forEach(function (sr) {
            var ys = skala(sr[0]);
            x.strokeStyle = warna(sr[1]); x.lineWidth = 1.5; x.beginPath();
            sr[0].forEach(function (v, i) { if (i) x.lineTo(xi(i), ys(v)); else x.moveTo(xi(i), ys(v)); });
            x.stroke();
        });
        x.lineWidth = 1;
        x.fillStyle = warna('--text-dim');
        x.fillText(dt[0], kiri, H - 2);
        var akhir = dt[n - 1]; x.fillText(akhir, W - kanan - x.measureText(akhir).width, H - 2);

        var i2 = sorot == null ? n - 1 : sorot;
        if (sorot != null) {
            x.strokeStyle = warna('--text-mid'); x.setLineDash([2, 3]);
            x.beginPath(); x.moveTo(xi(i2), 0); x.lineTo(xi(i2), H - 12); x.stroke();
            x.setLineDash([]);
        }
        var ch = i2 > 0 ? (cl[i2] / cl[i2 - 1] - 1) * 100 : null;
        document.getElementById('chart-info').innerHTML = esc(dt[i2]) + '  O ' + f(o[i2]) + ' H ' + f(hi[i2]) + ' L ' + f(lo[i2]) +
            ' C ' + f(cl[i2]) + ' ' + (ch == null ? '' : pct(ch)) + '  Vol ' + volume(vol[i2]);
    }

    function sentuh(ev) {
        var r = cv.getBoundingClientRect();
        var px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
        gambar(Math.max(0, Math.min(n - 1, Math.floor((px - kiri) / lebar))));
    }
    cv.ontouchstart = cv.ontouchmove = sentuh;
    cv.onmousemove = sentuh;
    cv.ontouchend = cv.onmouseleave = function () { gambar(null); };
    gambar(null);
}

// ---------------------------------------------------------------- Sinkron

function vSinkron() {
    var alamat = simpanan('bdm_alamat'), kodeP = simpanan('bdm_kode');
    var ada = !!window.Android;
    return kartu(null,
        '<div class="catatan">Di laptop jalankan <b>website\\hp\\KIRIM_KE_HP.bat</b>, lalu pastikan HP di WiFi yang sama. ' +
        'Tidak butuh internet — data lewat jaringan WiFi lokal saja.</div>' +
        '<label class="lbl">Kode pasangan (6 angka, tampil di layar laptop)</label>' +
        '<input class="isian mono" id="in-kode" inputmode="numeric" maxlength="6" value="' + esc(kodeP) + '">' +
        '<label class="lbl">Alamat laptop — kosongkan untuk cari otomatis</label>' +
        '<input class="isian mono" id="in-alamat" placeholder="mis. 192.168.1.5" inputmode="decimal" value="' + esc(alamat) + '">' +
        '<div style="height:16px"></div>' +
        '<button class="tbl-utama" id="tbl-mulai" onclick="mulaiSinkron()"' + (ada ? '' : ' disabled') + '>Sinkron sekarang</button>' +
        (ada ? '' : '<div class="catatan peringatan" style="margin-top:8px">Sinkron cuma jalan di aplikasi Android.</div>') +
        '<div class="log-sinkron" id="log-sinkron"></div>');
}

function simpanan(k) { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } }
function simpan(k, v) { try { localStorage.setItem(k, v); } catch (e) { } }

function mulaiSinkron() {
    var kd = document.getElementById('in-kode').value.trim();
    var al = document.getElementById('in-alamat').value.trim();
    if (!/^\d{6}$/.test(kd)) { logSinkron('Kode harus 6 angka.'); return; }
    simpan('bdm_kode', kd);
    simpan('bdm_alamat', al);
    document.getElementById('tbl-mulai').disabled = true;
    document.getElementById('log-sinkron').textContent = '';
    window.Android.sinkron(al, kd);
}

function logSinkron(t) {
    var el = document.getElementById('log-sinkron');
    if (el) el.textContent += t + '\n';
}

/* Dipanggil MainActivity: {tahap: 'info'|'alamat'|'selesai'|'galat', pesan, alamat} */
window.bdmSinkron = function (ev) {
    if (ev.pesan) logSinkron(ev.pesan);
    if (ev.alamat) {
        simpan('bdm_alamat', ev.alamat);
        var el = document.getElementById('in-alamat'); if (el) el.value = ev.alamat;
    }
    if (ev.tahap === 'galat') {
        var b = document.getElementById('tbl-mulai'); if (b) b.disabled = false;
    }
    if (ev.tahap === 'selesai') {
        muat().then(function () { location.hash = '#/ringkasan'; render(); });
    }
};

// ---------------------------------------------------------------- rute

function render() {
    var rute = (location.hash.replace(/^#\/?/, '') || 'ringkasan').split('/').map(decodeURIComponent);
    var isi = document.getElementById('isi');
    document.getElementById('nav').style.display = rute[0] === 'saham' || rute[0] === 'sinkron' ? 'none' : '';

    if (!D && rute[0] !== 'sinkron') {
        renderKepala(['ringkasan']);
        renderNav('');
        isi.innerHTML = '<div class="kosong"><div class="ik">📭</div>Belum ada data di HP ini.<br><br>' +
            '<a class="tbl-sinkron" href="#/sinkron">⟳ Sinkron dari laptop</a></div>';
        return;
    }
    renderKepala(rute);
    renderNav(rute[0]);
    var v = {
        ringkasan: vRingkasan,
        sinyal: function () { return vSinyal(rute[1]); },
        musiman_saham: function () { return kartu('Musiman Saham', '<div id="historiHp"></div>'); },
        perubahan_kepemilikan: function () { return kartu('Perubahan Kepemilikan', '<div id="historiHp"></div>'); },
        rotasi_sektor: vRotasiSektor,
        kalender: function () { return vAgenda('kalender', 'Kalender Pasar'); },
        agenda_emiten: function () { return vAgenda('agenda_emiten', 'Agenda Emiten'); },
        ramai: vRamai,
        watchlist: vWatchlist,
        saham: function () { return vSaham(rute[1]); },
        sinkron: vSinkron,
    }[rute[0]] || vRingkasan;
    isi.innerHTML = v();
    var histori = document.getElementById('historiHp');
    if (histori) historiRender(histori, rute[0], D.menu[rute[0]]);
}

var rutePrev = null;
window.addEventListener('hashchange', function () {
    render();
    // Pindah halaman mulai dari atas; ganti filter di halaman yang sama tidak.
    var r = location.hash.split('/').slice(0, 2).join('/');
    if (r !== rutePrev) window.scrollTo(0, 0);
    rutePrev = r;
});
window.addEventListener('resize', function () {
    if (/^#\/saham\//.test(location.hash)) render();
});
muat().then(render);

var agendaJenis = '';
function vAgenda(key, title) {
    var d=D.menu[key]||{}, isEmiten=key==='agenda_emiten', groups={}, types={};
    (d.items||[]).forEach(function(x){var k=x.kategori||'Lainnya';types[k]=(types[k]||0)+1;});
    if(!types[agendaJenis]) agendaJenis='';
    var filter=isEmiten?'<label for="agendaJenis">Jenis agenda</label><select id="agendaJenis" style="width:100%;padding:10px;margin:10px 0" onchange="agendaJenis=this.value;render()"><option value="">Semua jenis</option>'+Object.keys(types).sort().map(function(k){return '<option value="'+esc(k)+'"'+(agendaJenis===k?' selected':'')+'>'+esc(k)+' ('+types[k]+' jadwal)</option>';}).join('')+'</select>':'';
    function rowHtml(x){return '<div style="padding:12px 0;border-bottom:1px solid var(--line)"><div class="catatan">'+esc(x.kategori)+' · '+esc(x.jenis_tanggal||'Jadwal')+(x.stale?' · DATA LAMA':'')+'</div><b>'+esc((x.ticker||'')+' '+x.judul)+'</b><p>'+esc(x.waktu?new Date(x.waktu).toLocaleString('id-ID',{timeZone:'Asia/Jakarta'})+' WIB':x.tanggal+' · jam tidak tersedia')+'</p><div class="catatan">'+esc(x.catatan||'')+'</div>'+((x.konsensus||x.sebelumnya)?'<p>Konsensus: '+esc(x.konsensus||'—')+' · Sebelumnya: '+esc(x.sebelumnya||'—')+'</p>':'')+'<small>'+esc(x.sumber)+'</small></div>';}
    var rows=(d.items||[]).filter(function(x){return !isEmiten||!agendaJenis||(x.kategori||'Lainnya')===agendaJenis;}), html='';
    if(isEmiten){
        rows.forEach(function(x){var k=x.kategori||'Lainnya';(groups[k]||(groups[k]=[])).push(x);});
        html=Object.keys(groups).sort().map(function(k){return '<section style="margin-top:20px"><h2>'+esc(k)+' ('+groups[k].length+' jadwal)</h2>'+groups[k].map(rowHtml).join('')+'</section>';}).join('');
    }else{html=rows.map(rowHtml).join('');}
    return kartu(title, '<a href="#/ringkasan">‹ Ringkasan</a><p class="catatan">'+esc(d.message||'Belum ada data. Jalankan Sync di laptop.')+'</p><p class="catatan">Snapshot: '+esc(d.diperiksa||'—')+'</p>'+(d.sources||[]).map(function(s){return '<span class="catatan">'+esc(s.nama)+': '+(s.ok?'tersambung':'gagal diperbarui')+' · </span>';}).join('')+filter+(html||'<p class="catatan">Tidak ada jadwal. Periksa status sumber di atas.</p>'));
}

var rotasiUrutHp='r5';
function vRotasiSektor(){
 return kartu('Rotasi Sektor','<a href="#/ringkasan">‹ Ringkasan</a><p>Urutkan berdasarkan</p><select aria-label="Urutan rotasi sektor" style="width:100%;padding:10px" onchange="rotasiUrutHp=this.value;render()">'+[['r5','Kinerja 5 hari'],['r1','Kinerja 1 hari'],['r20','Kinerja 20 hari'],['aktivitas','Aktivitas transaksi'],['perubahan_porsi','Kenaikan porsi transaksi']].map(function(x){return '<option value="'+x[0]+'"'+(rotasiUrutHp===x[0]?' selected':'')+'>'+x[1]+'</option>';}).join('')+'</select>'+rotasiHtml(D.menu.rotasi_sektor,rotasiUrutHp));
}
